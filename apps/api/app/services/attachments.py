"""Attachment upload, listing, download and deletion policy (Task 24)."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailed, field_error
from app.core.permissions import Permission
from app.core.storage import ALLOWED_TYPES, Storage, StorageError, get_storage, sniff_content_type
from app.core.time import utcnow
from app.models.attachment import Attachment, AttachmentKind, AttachmentOwner
from app.models.finance import (
    Expense,
    FuelTransaction,
    RecordStatus,
    RevenueEntry,
    RideHailingStatement,
)
from app.models.fleet import Vehicle
from app.models.user import User
from app.services import audit


@dataclass(frozen=True)
class OwnerRule:
    model: type[Any]
    read: Permission
    write: Permission
    default_kind: AttachmentKind


def owner_rules() -> dict[AttachmentOwner, OwnerRule]:
    # Imported lazily: maintenance depends on this module for its own attachments.
    from app.models.maintenance import MaintenanceRecord  # noqa: PLC0415

    return {
        AttachmentOwner.FUEL_TRANSACTION: OwnerRule(
            FuelTransaction,
            Permission.FUEL_READ,
            Permission.FUEL_WRITE,
            AttachmentKind.FUEL_RECEIPT,
        ),
        AttachmentOwner.EXPENSE: OwnerRule(
            Expense,
            Permission.EXPENSES_READ,
            Permission.EXPENSES_WRITE,
            AttachmentKind.EXPENSE_RECEIPT,
        ),
        AttachmentOwner.REVENUE_ENTRY: OwnerRule(
            RevenueEntry,
            Permission.REVENUE_READ,
            Permission.REVENUE_WRITE,
            AttachmentKind.REVENUE_DOCUMENT,
        ),
        AttachmentOwner.RIDE_HAILING_STATEMENT: OwnerRule(
            RideHailingStatement,
            Permission.REVENUE_READ,
            Permission.REVENUE_WRITE,
            AttachmentKind.PLATFORM_STATEMENT,
        ),
        AttachmentOwner.MAINTENANCE_RECORD: OwnerRule(
            MaintenanceRecord,
            Permission.MAINTENANCE_READ,
            Permission.MAINTENANCE_WRITE,
            AttachmentKind.MAINTENANCE_INVOICE,
        ),
        AttachmentOwner.VEHICLE: OwnerRule(
            Vehicle,
            Permission.VEHICLES_READ,
            Permission.VEHICLES_WRITE,
            AttachmentKind.VEHICLE_DOCUMENT,
        ),
    }


def rule_for(owner_type: AttachmentOwner) -> OwnerRule:
    return owner_rules()[owner_type]


def load_owner(db: Session, owner_type: AttachmentOwner, owner_id: uuid.UUID) -> Any:
    owner = db.get(rule_for(owner_type).model, owner_id)
    if owner is None:
        raise NotFoundError("السجل المرتبط غير موجود")
    return owner


def _locked(owner: Any) -> bool:
    """Evidence on approved or voided financial records is immutable."""
    status = getattr(owner, "status", None)
    return status in (RecordStatus.APPROVED, RecordStatus.VOIDED)


def safe_filename(name: str | None, extension: str) -> str:
    base = unicodedata.normalize("NFC", (name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
    base = re.sub(r"[\x00-\x1f\x7f\"<>|:*?]", "", base).strip(" .")
    stem = base.rsplit(".", 1)[0][:150] if base else ""
    return f"{stem or 'attachment'}{extension}"


def upload(
    db: Session,
    *,
    actor: User,
    owner_type: AttachmentOwner,
    owner_id: uuid.UUID,
    data: bytes,
    filename: str | None,
    kind: AttachmentKind | None = None,
    storage: Storage | None = None,
) -> tuple[Attachment, list[Attachment]]:
    """Store a file and its metadata; returns it and earlier files with the same bytes."""
    owner = load_owner(db, owner_type, owner_id)
    if _locked(owner):
        raise ConflictError(
            "لا يمكن إضافة مرفقات لسجل معتمد أو ملغي؛ استخدم التصحيح", code="record_locked"
        )
    if not data:
        raise field_error("file", "الملف فارغ")
    if len(data) > get_settings().attachment_max_bytes:
        raise field_error("file", "حجم الملف أكبر من المسموح", code="file_too_large")
    content_type = sniff_content_type(data)
    if content_type is None:
        raise field_error(
            "file", "نوع الملف غير مسموح؛ المسموح صور JPG/PNG/WebP أو PDF", code="file_type"
        )
    extension = ALLOWED_TYPES[content_type]
    digest = hashlib.sha256(data).hexdigest()
    now = utcnow()
    key = f"{owner_type.value}/{now:%Y/%m}/{uuid.uuid4().hex}{extension}"
    store = storage or get_storage()
    try:
        store.put(key, data, content_type)
    except StorageError as exc:
        raise ValidationFailed("تعذر حفظ الملف", code="storage_error") from exc

    duplicates = list(
        db.scalars(
            select(Attachment).where(Attachment.sha256 == digest, Attachment.deleted_at.is_(None))
        ).all()
    )
    attachment = Attachment(
        owner_type=owner_type,
        owner_id=owner_id,
        kind=kind or rule_for(owner_type).default_kind,
        storage_backend=store.name,
        storage_key=key,
        original_filename=safe_filename(filename, extension),
        content_type=content_type,
        size_bytes=len(data),
        sha256=digest,
        uploaded_by_id=actor.id,
    )
    db.add(attachment)
    db.flush()
    audit.record(
        db,
        action="attachment.uploaded",
        actor=actor,
        entity_type=owner_type.value,
        entity_id=owner_id,
        details={
            "attachment_id": attachment.id,
            "kind": attachment.kind.value,
            "content_type": content_type,
            "size_bytes": len(data),
            "duplicate_of": [str(d.id) for d in duplicates],
        },
    )
    db.commit()
    return attachment, duplicates


def list_for(
    db: Session, owner_type: AttachmentOwner, owner_id: uuid.UUID, *, include_deleted: bool = True
) -> list[Attachment]:
    stmt = select(Attachment).where(
        Attachment.owner_type == owner_type, Attachment.owner_id == owner_id
    )
    if not include_deleted:
        stmt = stmt.where(Attachment.deleted_at.is_(None))
    return list(db.scalars(stmt.order_by(Attachment.created_at)).all())


def get(db: Session, attachment_id: uuid.UUID) -> Attachment:
    attachment = db.get(Attachment, attachment_id)
    if attachment is None:
        raise NotFoundError("المرفق غير موجود")
    return attachment


def read_content(attachment: Attachment, storage: Storage | None = None) -> bytes:
    if attachment.deleted_at is not None:
        raise NotFoundError("المرفق محذوف")
    try:
        return (storage or get_storage()).get(attachment.storage_key)
    except StorageError as exc:
        raise NotFoundError("ملف المرفق غير متاح") from exc


def delete(db: Session, *, actor: User, attachment_id: uuid.UUID, reason: str) -> Attachment:
    """Soft delete with a reason. The stored object is kept for the audit trail."""
    attachment = get(db, attachment_id)
    if attachment.deleted_at is not None:
        raise ConflictError("المرفق محذوف بالفعل", code="invalid_state")
    owner = load_owner(db, attachment.owner_type, attachment.owner_id)
    if _locked(owner):
        raise ConflictError("مرفقات السجلات المعتمدة جزء من الإثبات ولا تُحذف", code="record_locked")
    attachment.deleted_at = utcnow()
    attachment.deleted_by_id = actor.id
    attachment.delete_reason = reason
    audit.record(
        db,
        action="attachment.deleted",
        actor=actor,
        entity_type=attachment.owner_type.value,
        entity_id=attachment.owner_id,
        details={"attachment_id": attachment.id, "filename": attachment.original_filename},
        reason=reason,
    )
    db.commit()
    return attachment
