"""Security event dashboard (U36): settings managers only."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission
from app.models.user import User
from app.services import security_events

router = APIRouter(prefix="/security", tags=["security"])

Admin = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]


class CountedOut(BaseModel):
    label: str
    count: int


class HourOut(BaseModel):
    hour: datetime
    count: int


class EventOut(BaseModel):
    at: datetime
    action: str
    label: str
    user: str | None
    ip: str | None


class WarningOut(BaseModel):
    code: str
    message: str


class SecurityEventsOut(BaseModel):
    hours: int
    counts: dict[str, int]
    hourly_failures: list[HourOut]
    spike: bool
    top_accounts: list[CountedOut]
    top_addresses: list[CountedOut]
    unknown_number_attempts: int
    recent: list[EventOut]
    warnings: list[WarningOut]


@router.get("/events", response_model=SecurityEventsOut)
def events(_: Admin, db: DbSession, hours: int = Query(24, ge=1, le=168)) -> SecurityEventsOut:
    s = security_events.summary(db, hours)
    return SecurityEventsOut(
        hours=s.hours,
        counts=s.counts,
        hourly_failures=[HourOut(hour=h, count=n) for h, n in s.hourly_failures],
        spike=s.spike,
        top_accounts=[CountedOut(label=c.label, count=c.count) for c in s.top_accounts],
        top_addresses=[CountedOut(label=c.label, count=c.count) for c in s.top_addresses],
        unknown_number_attempts=s.unknown_number_attempts,
        recent=[EventOut(**e.__dict__) for e in s.recent],
        warnings=[WarningOut(code=w.code, message=w.message) for w in s.warnings],
    )
