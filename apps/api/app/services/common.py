"""Small helpers shared by services."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.schemas.common import PageParams
from app.services import audit


def apply_changes(obj: object, fields: Mapping[str, Any], audited: Iterable[str]) -> dict[str, Any]:
    """Assign fields and return the audit diff of the audited attributes."""
    audited = tuple(audited)
    before = audit.snapshot(obj, audited)
    for key, value in fields.items():
        setattr(obj, key, value)
    return audit.diff(before, audit.snapshot(obj, audited))


def paginate[T](db: Session, stmt: Select[T], params: PageParams) -> tuple[list[T], int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.offset(params.offset).limit(params.page_size)).unique().all()
    return list(rows), total


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_pattern(q: str) -> str:
    return f"%{escape_like(q.strip())}%"
