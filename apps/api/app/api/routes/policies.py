"""Versioned company policies (U47): read for reviewers, change with settings:manage."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, require_permissions
from app.core.config import get_settings
from app.core.permissions import Permission
from app.models.audit import AuditLog
from app.models.user import User
from app.services import policies

router = APIRouter(prefix="/policies", tags=["policies"])

Reader = Annotated[User, Depends(require_permissions(Permission.EXCEPTIONS_READ))]
Manager = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]


class PolicyValueOut(BaseModel):
    key: str
    group: str
    title: str
    unit: str
    value: float
    default: float
    minimum: float
    maximum: float
    integer: bool
    overridden: bool


class PolicyHistoryOut(BaseModel):
    version: int
    created_at: datetime
    created_by: str | None
    reason: str
    changes: dict[str, Any]


class PoliciesOut(BaseModel):
    version: int
    values: list[PolicyValueOut]
    history: list[PolicyHistoryOut]


class PolicyUpdateIn(BaseModel):
    # key -> new value, or null to go back to the default.
    changes: dict[str, float | None] = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=500)


def _out(db: DbSession) -> PoliciesOut:
    defaults = get_settings()
    latest = policies.current(db)
    overrides = latest.values if latest else {}
    effective = policies.effective_settings(db)
    versions = policies.history(db)
    changes = {
        a.entity_id: dict(a.changes or {})
        for a in db.scalars(
            select(AuditLog).where(
                AuditLog.action == "policy.updated",
                AuditLog.entity_id.in_([str(v.id) for v in versions]),
            )
        ).all()
    }
    ids = {v.created_by_id for v in versions if v.created_by_id}
    names = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(ids))).all()}
    return PoliciesOut(
        version=latest.version if latest else 0,
        values=[
            PolicyValueOut(
                key=k.key,
                group=k.group,
                title=k.title,
                unit=k.unit,
                value=float(getattr(effective, k.key)),
                default=float(getattr(defaults, k.key)),
                minimum=k.minimum,
                maximum=k.maximum,
                integer=k.integer,
                overridden=k.key in overrides,
            )
            for k in policies.CATALOG
        ],
        history=[
            PolicyHistoryOut(
                version=v.version,
                created_at=v.created_at,
                created_by=names.get(v.created_by_id) if v.created_by_id else None,
                reason=v.reason,
                changes=changes.get(str(v.id), {}),
            )
            for v in versions
        ],
    )


@router.get("", response_model=PoliciesOut)
def get_policies(_: Reader, db: DbSession) -> PoliciesOut:
    return _out(db)


@router.post("", response_model=PoliciesOut)
def update_policies(body: PolicyUpdateIn, actor: Manager, db: DbSession) -> PoliciesOut:
    policies.update(db, actor=actor, changes=dict(body.changes), reason=body.reason)
    return _out(db)
