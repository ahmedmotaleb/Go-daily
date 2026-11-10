"""Pilot command center and daily close (U50/U51)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission
from app.core.time import local_today
from app.models.user import User
from app.services import pilot

router = APIRouter(prefix="/pilot", tags=["pilot"])

# The view joins live tracking, money and cash, so it needs all three.
Reader = Annotated[
    User,
    Depends(
        require_permissions(Permission.TRACKING_READ, Permission.REVENUE_READ, Permission.CASH_READ)
    ),
]


class CheckOut(BaseModel):
    code: str
    label: str
    state: pilot.CheckState
    detail: str


class ShiftLineOut(BaseModel):
    shift_id: uuid.UUID
    driver_name: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    operations: list[str]
    gps_km: float
    odometer_km: int | None
    gps_grade: str
    odometer_status: str
    loops: int
    legs: int


class CaseRef(BaseModel):
    id: uuid.UUID
    summary: str


class PilotDayOut(BaseModel):
    vehicle_id: uuid.UUID
    vehicle_code: str
    plate_number: str
    day: date
    drivers: list[str]
    day_off: bool
    shifts: list[ShiftLineOut]
    tracking_state: str | None
    last_received_at: datetime | None
    fuel: Decimal
    expenses: Decimal
    revenue: Decimal
    closeout_net: Decimal
    collected: Decimal
    remaining: Decimal
    open_cases: list[CaseRef]
    checks: list[CheckOut]
    verdict: pilot.Verdict
    verdict_ar: str


def _out(d: pilot.PilotDay) -> PilotDayOut:
    return PilotDayOut(
        vehicle_id=d.vehicle_id,
        vehicle_code=d.vehicle_code,
        plate_number=d.plate_number,
        day=d.day,
        drivers=d.drivers,
        day_off=d.day_off,
        shifts=[ShiftLineOut(**s.__dict__) for s in d.shifts],
        tracking_state=d.tracking_state,
        last_received_at=d.last_received_at,
        fuel=d.fuel,
        expenses=d.expenses,
        revenue=d.revenue,
        closeout_net=d.closeout_net,
        collected=d.collected,
        remaining=d.remaining,
        open_cases=[CaseRef(id=i, summary=s) for i, s in d.open_cases],
        checks=[CheckOut(**c.__dict__) for c in d.checks],
        verdict=d.verdict,
        verdict_ar=d.verdict_ar,
    )


@router.get("", response_model=list[PilotDayOut])
def pilot_day(_: Reader, db: DbSession, day: date | None = None) -> list[PilotDayOut]:
    """One card per pilot vehicle for the day (Cairo), with its daily close."""
    on = day or local_today()
    return [_out(pilot.day(db, v, on)) for v in pilot.pilot_vehicles(db)]
