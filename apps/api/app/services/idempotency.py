"""Idempotency-Key handling for retry-sensitive writes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ValidationFailed
from app.core.time import utcnow
from app.models.idempotency import IdempotencyRecord
from app.models.user import User

RETENTION = timedelta(days=7)
MAX_KEY_LENGTH = 100


def _hash(body: Any) -> str:
    return hashlib.sha256(
        json.dumps(jsonable_encoder(body), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def upload_fingerprint(data: bytes, filename: str | None) -> dict[str, Any]:
    """What identifies a file upload for Idempotency-Key: its content and name.

    The same key with a different file is a conflict, not a replay.
    """
    return {"sha256": hashlib.sha256(data).hexdigest(), "filename": filename}


# status_code of a claimed key whose action has not stored its response yet.
PENDING = 0


def run_idempotent[T](
    db: Session,
    *,
    user: User,
    key: str | None,
    method: str,
    path: str,
    body: Any,
    status_code: int,
    action: Callable[[], T],
) -> tuple[T | Any, bool]:
    """Run `action` once per (user, key). Returns (result, replayed).

    The key is required (every driver-app write sends one) and is claimed
    before the action, in the same transaction the action commits, so two
    concurrent retries can never both run it: the second waits on the unique
    index, then finds the claim (security audit M9). If the action committed
    but its response was not stored yet, a retry gets request_in_progress
    instead of running it again.
    """
    if not key:
        raise ValidationFailed(
            "مفتاح التكرار (Idempotency-Key) مطلوب", code="idempotency_key_required"
        )
    if len(key) > MAX_KEY_LENGTH or not key.isprintable():
        raise ValidationFailed("مفتاح التكرار غير صالح", code="invalid_idempotency_key")
    request_hash = _hash(body)
    claimed = db.scalar(
        insert(IdempotencyRecord)
        .values(
            user_id=user.id,
            key=key,
            method=method,
            path=path,
            request_hash=request_hash,
            status_code=PENDING,
            response_body={},
        )
        .on_conflict_do_nothing(index_elements=["user_id", "key"])
        .returning(IdempotencyRecord.id)
    )
    if claimed is None:
        existing = db.scalars(
            select(IdempotencyRecord)
            .where(IdempotencyRecord.user_id == user.id, IdempotencyRecord.key == key)
            .execution_options(populate_existing=True)
        ).one()
        if existing.request_hash != request_hash or existing.path != path:
            raise ConflictError(
                "تم استخدام مفتاح التكرار لطلب مختلف", code="idempotency_key_reused"
            )
        if existing.status_code == PENDING:
            raise ConflictError(
                "الطلب نفسه قيد التنفيذ أو نُفذ دون حفظ نتيجته؛ حدّث البيانات من التطبيق",
                code="request_in_progress",
            )
        return existing.response_body, True

    try:
        result = action()
    except Exception:
        # Nothing the action committed? Then the claim goes with the rollback and
        # a retry may run again; if it did commit, the claim stays (no rerun).
        db.rollback()
        raise
    db.execute(
        update(IdempotencyRecord)
        .where(IdempotencyRecord.id == claimed)
        .values(status_code=status_code, response_body=jsonable_encoder(result))
    )
    db.commit()
    return result, False


def prune(db: Session) -> int:
    result = db.execute(
        delete(IdempotencyRecord).where(IdempotencyRecord.created_at < utcnow() - RETENTION)
    )
    db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
