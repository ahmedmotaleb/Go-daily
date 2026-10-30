"""Idempotency-Key handling for retry-sensitive writes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select
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
    """Run `action` once per (user, key). Returns (result, replayed)."""
    if not key:
        return action(), False
    if len(key) > MAX_KEY_LENGTH or not key.isprintable():
        raise ValidationFailed("مفتاح التكرار غير صالح", code="invalid_idempotency_key")
    request_hash = _hash(body)
    existing = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user.id, IdempotencyRecord.key == key
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash or existing.path != path:
            raise ConflictError(
                "تم استخدام مفتاح التكرار لطلب مختلف", code="idempotency_key_reused"
            )
        return existing.response_body, True

    result = action()
    db.execute(
        insert(IdempotencyRecord)
        .values(
            user_id=user.id,
            key=key,
            method=method,
            path=path,
            request_hash=request_hash,
            status_code=status_code,
            response_body=jsonable_encoder(result),
        )
        .on_conflict_do_nothing(index_elements=["user_id", "key"])
    )
    db.commit()
    return result, False


def prune(db: Session) -> int:
    result = db.execute(
        delete(IdempotencyRecord).where(IdempotencyRecord.created_at < utcnow() - RETENTION)
    )
    db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
