"""Audit trail browsing (read-only)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogOut
from app.schemas.common import Page, PageParams, page_params

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=Page[AuditLogOut])
def list_audit_logs(
    _: Annotated[User, Depends(require_permissions(Permission.AUDIT_READ))],
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    entity_type: Annotated[str | None, Query(max_length=60)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    actor_user_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=80)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Page[AuditLogOut]:
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    if since:
        stmt = stmt.where(AuditLog.occurred_at >= since)
    if until:
        stmt = stmt.where(AuditLog.occurred_at < until)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AuditLog.occurred_at.desc(), AuditLog.id)
        .offset(params.offset)
        .limit(params.page_size)
    ).all()
    return Page(
        items=[AuditLogOut.model_validate(r) for r in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )
