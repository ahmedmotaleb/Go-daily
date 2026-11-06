"""Attachment schemas (Task 24)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.attachment import AttachmentKind, AttachmentOwner
from app.schemas.finance import Reason, UserRef


class AttachmentOut(BaseModel):
    id: uuid.UUID
    owner_type: AttachmentOwner
    owner_id: uuid.UUID
    kind: AttachmentKind
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by: UserRef | None
    created_at: datetime
    deleted_at: datetime | None
    delete_reason: str | None


class DuplicateRef(BaseModel):
    attachment_id: uuid.UUID
    owner_type: AttachmentOwner
    owner_id: uuid.UUID


class UploadResult(BaseModel):
    attachment: AttachmentOut
    # Earlier files with identical bytes (possible duplicate receipt).
    duplicates: list[DuplicateRef]


class AttachmentDelete(BaseModel):
    reason: Reason
