"""Operations control center (U23): one row per vehicle in a shift right now.

Each row joins what is recorded about the running shift: driver, current
operation, the latest received position and how fresh it is, shift start,
completed loops/legs, today's school runs, today's collection and fuel for
the vehicle, and open review cases. Nothing is estimated: a vehicle with no
received position shows none, and money is only filled for users allowed to
see it (the route decides).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import local_day_bounds_utc, local_today
from app.models.exceptions import ExceptionStatus, OperationalException
from app.models.finance import FuelTransaction, RecordStatus, RevenueEntry
from app.models.route_events import SchoolRun, SchoolRunStatus
from app.models.shift import Shift
from app.services import finance_common as fc
from app.services import route_events, tracking

ZERO = Decimal("0")
LIVE = (RecordStatus.SUBMITTED, RecordStatus.APPROVED)
OPEN_CASES = (ExceptionStatus.OPEN, ExceptionStatus.UNDER_REVIEW, ExceptionStatus.ESCALATED)
DONE_RUNS = (SchoolRunStatus.COMPLETED, SchoolRunStatus.COMPLETED_LATE)


@dataclass
class ControlRow:
    vehicle_id: uuid.UUID
    vehicle_code: str
    plate_number: str
    driver_id: uuid.UUID
    driver_name: str
    shift_id: uuid.UUID
    shift_started_at: datetime | None
    operation: str | None
    tracking_state: str
    latitude: float | None
    longitude: float | None
    last_received_at: datetime | None
    speed_kmh: float | None
    loops: int = 0
    legs: int = 0
    school_done: int = 0
    school_planned: int = 0
    school_attention: int = 0
    collection_today: Decimal | None = None
    fuel_today: Decimal | None = None
    open_cases: int = 0
    case_titles: list[str] = field(default_factory=list)


def _money_by_vehicle(
    db: Session, vehicle_ids: list[uuid.UUID], today: date
) -> tuple[dict[uuid.UUID, Decimal], dict[uuid.UUID, Decimal]]:
    start, end = local_day_bounds_utc(today)
    collection: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for vid, total in db.execute(
        select(RevenueEntry.vehicle_id, func.sum(RevenueEntry.amount))
        .where(
            RevenueEntry.vehicle_id.in_(vehicle_ids),
            RevenueEntry.status.in_(LIVE),
            RevenueEntry.occurred_on == today,
        )
        .group_by(RevenueEntry.vehicle_id)
    ).all():
        collection[vid] = fc.money(Decimal(total))
    fuel: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for vid, total in db.execute(
        select(FuelTransaction.vehicle_id, func.sum(FuelTransaction.total_amount))
        .where(
            FuelTransaction.vehicle_id.in_(vehicle_ids),
            FuelTransaction.status.in_(LIVE),
            FuelTransaction.occurred_at >= start,
            FuelTransaction.occurred_at < end,
        )
        .group_by(FuelTransaction.vehicle_id)
    ).all():
        fuel[vid] = fc.money(Decimal(total))
    return collection, fuel


def rows(db: Session, *, with_money: bool, with_fuel: bool, with_cases: bool) -> list[ControlRow]:
    live = tracking.live_positions(db)
    today = local_today()
    vehicle_ids = [p.vehicle_id for p in live]
    shifts = {
        s.id: s for s in db.scalars(select(Shift).where(Shift.id.in_([p.shift_id for p in live])))
    }
    session_ids = [x.id for s in shifts.values() for x in s.sessions]
    counts = route_events.counts(db, session_ids)
    runs = db.scalars(
        select(SchoolRun).where(
            SchoolRun.service_date == today, SchoolRun.vehicle_id.in_(vehicle_ids)
        )
    ).all()
    collection, fuel = _money_by_vehicle(db, vehicle_ids, today) if vehicle_ids else ({}, {})
    cases: dict[uuid.UUID, list[str]] = defaultdict(list)
    if with_cases and vehicle_ids:
        for vid, title in db.execute(
            select(OperationalException.vehicle_id, OperationalException.summary)
            .where(
                OperationalException.vehicle_id.in_(vehicle_ids),
                OperationalException.status.in_(OPEN_CASES),
            )
            .order_by(OperationalException.occurred_at.desc())
        ).all():
            if vid is not None:
                cases[vid].append(title)

    out: list[ControlRow] = []
    for p in live:
        shift = shifts.get(p.shift_id)
        row = ControlRow(
            vehicle_id=p.vehicle_id,
            vehicle_code=p.vehicle_code,
            plate_number=p.plate_number,
            driver_id=p.driver_id,
            driver_name=p.driver_name,
            shift_id=p.shift_id,
            shift_started_at=shift.started_at if shift else None,
            operation=p.current_operation,
            tracking_state=p.state,
            latitude=p.latitude,
            longitude=p.longitude,
            last_received_at=p.last_received_at,
            speed_kmh=p.speed_kmh,
        )
        if shift:
            for s in shift.sessions:
                c = counts.get(s.id, {})
                row.loops += c.get("loops", 0)
                row.legs += c.get("legs", 0)
        mine = [
            r
            for r in runs
            if r.vehicle_id == p.vehicle_id and r.status is not SchoolRunStatus.CANCELLED
        ]
        row.school_planned = len(mine)
        row.school_done = sum(1 for r in mine if r.status in DONE_RUNS)
        row.school_attention = sum(
            1
            for r in mine
            if r.status
            in (
                SchoolRunStatus.INCOMPLETE,
                SchoolRunStatus.COMPLETED_UNVERIFIED,
                SchoolRunStatus.MISSED,
            )
        )
        if with_money:
            row.collection_today = collection.get(p.vehicle_id, ZERO)
        if with_fuel:
            row.fuel_today = fuel.get(p.vehicle_id, ZERO)
        if with_cases:
            row.case_titles = cases.get(p.vehicle_id, [])[:3]
            row.open_cases = len(cases.get(p.vehicle_id, []))
        out.append(row)
    order = {"OFFLINE": 0, "STALE": 1, "ONLINE": 2}
    return sorted(
        out, key=lambda r: (-r.open_cases, order.get(r.tracking_state, 3), r.vehicle_code)
    )


__all__ = ["ControlRow", "rows"]
