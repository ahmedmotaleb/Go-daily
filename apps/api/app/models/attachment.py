"""File attachments (receipts, statements, invoices, vehicle documents).

Metadata lives here; the bytes live in object storage under a server-made
key. Attachments are never hard-deleted from the database: a deletion
records who, when and why, and evidence on approved financial records
cannot be deleted at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base, UUIDPrimaryKeyMixin, enum_column_type


class AttachmentKind(StrEnum):
    FUEL_RECEIPT = "FUEL_RECEIPT"
    EXPENSE_RECEIPT = "EXPENSE_RECEIPT"
    REVENUE_DOCUMENT = "REVENUE_DOCUMENT"
    PLATFORM_STATEMENT = "PLATFORM_STATEMENT"
    MAINTENANCE_INVOICE = "MAINTENANCE_INVOICE"
    VEHICLE_DOCUMENT = "VEHICLE_DOCUMENT"
    OTHER = "OTHER"


class AttachmentOwner(StrEnum):
    FUEL_TRANSACTION = "fuel_transaction"
    EXPENSE = "expense"
    REVENUE_ENTRY = "revenue_entry"
    RIDE_HAILING_STATEMENT = "ride_hailing_statement"
    MAINTENANCE_RECORD = "maintenance_record"
    VEHICLE = "vehicle"


class Attachment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "attachments"

    owner_type: Mapped[AttachmentOwner] = mapped_column(
        enum_column_type(AttachmentOwner, "attachment_owner")
    )
    owner_id: Mapped[uuid.UUID]
    kind: Mapped[AttachmentKind] = mapped_column(
        enum_column_type(AttachmentKind, "attachment_kind")
    )
    storage_backend: Mapped[str] = mapped_column(String(20))
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    original_filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    deleted_at: Mapped[datetime | None]
    deleted_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    delete_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="size_positive"),
        Index("ix_attachments_owner", "owner_type", "owner_id"),
        Index("ix_attachments_sha256", "sha256"),
    )
