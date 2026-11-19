"""Attachments: private upload, listing, download, deletion (Task 24).

Access follows the owning record: reading needs that record's read
permission, uploading and deleting need its write permission.
"""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, UploadFile, status
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbSession
from app.api.finance_presenters import load_users
from app.core.config import get_settings
from app.core.errors import PermissionDenied, field_error
from app.core.permissions import STAFF_ROLES, Permission, has_permission
from app.models.attachment import Attachment, AttachmentKind, AttachmentOwner
from app.models.user import User
from app.schemas.attachment import AttachmentDelete, AttachmentOut, DuplicateRef, UploadResult
from app.schemas.finance import UserRef
from app.services import attachments as attachments_service

router = APIRouter(prefix="/attachments", tags=["attachments"])


def _require(user: User, permission: Permission) -> None:
    if user.role not in STAFF_ROLES or not has_permission(user.role, permission):
        raise PermissionDenied(details={"missing": [permission.value]})


def _outs(db: DbSession, rows: list[Attachment]) -> list[AttachmentOut]:
    users = load_users(db, (a.uploaded_by_id for a in rows))
    out = []
    for a in rows:
        uploader = users.get(a.uploaded_by_id) if a.uploaded_by_id else None
        out.append(
            AttachmentOut(
                id=a.id,
                owner_type=a.owner_type,
                owner_id=a.owner_id,
                kind=a.kind,
                original_filename=a.original_filename,
                content_type=a.content_type,
                size_bytes=a.size_bytes,
                sha256=a.sha256,
                uploaded_by=UserRef(id=uploader.id, full_name=uploader.full_name)
                if uploader
                else None,
                created_at=a.created_at,
                deleted_at=a.deleted_at,
                delete_reason=a.delete_reason,
            )
        )
    return out


async def read_limited(file: UploadFile) -> bytes:
    """Read at most the configured size (+1 byte to detect oversize uploads)."""
    limit = get_settings().attachment_max_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise field_error("file", "حجم الملف أكبر من المسموح", code="file_too_large")
    return data


@router.post("", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile,
    owner_type: Annotated[AttachmentOwner, Form()],
    owner_id: Annotated[uuid.UUID, Form()],
    kind: Annotated[AttachmentKind | None, Form()] = None,
) -> UploadResult:
    _require(user, attachments_service.rule_for(owner_type).write)
    data = await read_limited(file)
    attachment, duplicates = attachments_service.upload(
        db,
        actor=user,
        owner_type=owner_type,
        owner_id=owner_id,
        data=data,
        filename=file.filename,
        kind=kind,
    )
    return UploadResult(
        attachment=_outs(db, [attachment])[0],
        duplicates=[
            DuplicateRef(attachment_id=d.id, owner_type=d.owner_type, owner_id=d.owner_id)
            for d in duplicates
        ],
    )


@router.get("", response_model=list[AttachmentOut])
def list_attachments(
    user: CurrentUser,
    db: DbSession,
    owner_type: AttachmentOwner,
    owner_id: uuid.UUID,
) -> list[AttachmentOut]:
    _require(user, attachments_service.rule_for(owner_type).read)
    attachments_service.load_owner(db, owner_type, owner_id)
    return _outs(db, attachments_service.list_for(db, owner_type, owner_id))


@router.get("/{attachment_id}/content")
def attachment_content(attachment_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    attachment = attachments_service.get(db, attachment_id)
    _require(user, attachments_service.rule_for(attachment.owner_type).read)
    data = attachments_service.read_content(attachment)
    filename = quote(attachment.original_filename)
    return Response(
        content=data,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        },
    )


@router.post("/{attachment_id}/delete", response_model=AttachmentOut)
def delete_attachment(
    attachment_id: uuid.UUID, body: AttachmentDelete, user: CurrentUser, db: DbSession
) -> AttachmentOut:
    attachment = attachments_service.get(db, attachment_id)
    _require(user, attachments_service.rule_for(attachment.owner_type).write)
    deleted = attachments_service.delete(
        db, actor=user, attachment_id=attachment_id, reason=body.reason
    )
    return _outs(db, [deleted])[0]
