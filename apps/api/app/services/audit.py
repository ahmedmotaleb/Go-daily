"""Audit trail helpers.

`record()` adds an audit row to the current session; the calling service
commits it together with the change it describes, so an audited change and
its audit record succeed or fail together.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.core.request_context import get_request_context
from app.models.audit import AuditLog
from app.models.user import User

# Values of these fields are never written to the audit log; only the fact
# that they changed is recorded.
REDACTED_FIELDS = frozenset({"password_hash", "password", "national_id", "token", "token_hash"})


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [to_jsonable(v) for v in value]
    return str(value)


def snapshot(obj: object, fields: Iterable[str]) -> dict[str, Any]:
    """JSON-safe dict of selected attributes (sensitive values redacted)."""
    out: dict[str, Any] = {}
    for f in fields:
        value = getattr(obj, f, None)
        out[f] = "[REDACTED]" if f in REDACTED_FIELDS and value is not None else to_jsonable(value)
    return out


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    """{field: {"old": x, "new": y}} for fields whose value changed."""
    changes: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old != new:
            if key in REDACTED_FIELDS:
                changes[key] = {"changed": True}
            else:
                changes[key] = {"old": old, "new": new}
    return changes


def record(
    db: Session,
    *,
    action: str,
    actor: User | None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | str | None = None,
    changes: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
    reason: str | None = None,
) -> AuditLog:
    ctx = get_request_context()
    entry = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_role=actor.role.value if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        changes=to_jsonable(dict(changes)) if changes else None,
        details=to_jsonable(dict(details)) if details else None,
        reason=reason,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        request_id=request_id_var.get(),
    )
    db.add(entry)
    return entry
