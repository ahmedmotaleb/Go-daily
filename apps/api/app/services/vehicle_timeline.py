"""Vehicle daily timeline (U24): everything recorded about one vehicle on one day.

Items come straight from their records, in time order: assignment changes,
shift start/end, operation changes, GPS gaps (from the shift track), loops
and legs, school runs, fuel, expenses, collections, close-outs and cash
handed over, maintenance and review cases. Each kind is included only when
the caller may see it (the route passes the allowed kinds), and items with
no time of day (revenue dated by day, maintenance) are listed at the top.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.time import local_day_bounds_utc
from app.models.assignment import DriverVehicleAssignment
from app.models.cash import CashCollection, ShiftCloseout
from app.models.exceptions import ExceptionStatus, OperationalException
from app.models.finance import Expense, FuelTransaction, RecordStatus, RevenueEntry
from app.models.maintenance import MaintenanceRecord
from app.models.route_events import EventStatus, RouteEvent, RouteEventType, SchoolRun
from app.models.shift import SessionStatus, Shift, ShiftStatus
from app.services import tracking
from app.services.reports import REVENUE_KIND_AR, SCHOOL_STATUS_AR

STATUS_AR = {
    RecordStatus.SUBMITTED: "بانتظار المراجعة",
    RecordStatus.APPROVED: "معتمد",
    RecordStatus.REJECTED: "مرفوض",
    RecordStatus.VOIDED: "ملغي",
}
CASE_STATUS_AR = {
    ExceptionStatus.OPEN: "مفتوحة",
    ExceptionStatus.UNDER_REVIEW: "قيد المراجعة",
    ExceptionStatus.ESCALATED: "مُصعّدة",
    ExceptionStatus.EXPLAINED: "تم التوضيح",
    ExceptionStatus.CORRECTED: "تم التصحيح",
    ExceptionStatus.DISMISSED: "مستبعدة",
}
ROUTE_EVENT_AR = {
    RouteEventType.LOOP_COMPLETED: "دورة مكتملة",
    RouteEventType.LEG_COMPLETED: "اتجاه مكتمل",
    RouteEventType.LEG_INCOMPLETE: "اتجاه غير مكتمل",
}


class Section(StrEnum):
    """What a caller may see; the route maps permissions to sections."""

    ASSIGNMENTS = "ASSIGNMENTS"
    SHIFTS = "SHIFTS"
    TRACKING = "TRACKING"
    FUEL = "FUEL"
    EXPENSES = "EXPENSES"
    REVENUE = "REVENUE"
    CASH = "CASH"
    MAINTENANCE = "MAINTENANCE"
    REVIEW = "REVIEW"


@dataclass
class Item:
    at: datetime | None
    kind: str
    title: str
    detail: str | None = None
    amount: Decimal | None = None
    status: str | None = None
    until: datetime | None = None
    link: str | None = None


def _assignments(db: Session, vid: uuid.UUID, start: datetime, end: datetime) -> list[Item]:
    out = []
    rows = db.scalars(
        select(DriverVehicleAssignment).where(
            DriverVehicleAssignment.vehicle_id == vid,
            or_(
                DriverVehicleAssignment.starts_at.between(start, end),
                DriverVehicleAssignment.ends_at.between(start, end),
            ),
        )
    ).all()
    for a in rows:
        role = "أساسي" if a.role.value == "PRIMARY" else "بديل"
        if start <= a.starts_at < end:
            out.append(Item(a.starts_at, "ASSIGNMENT", f"تكليف {a.driver.full_name} ({role})"))
        if a.ends_at and start <= a.ends_at < end:
            out.append(Item(a.ends_at, "ASSIGNMENT", f"انتهاء تكليف {a.driver.full_name}"))
    return out


def _shifts(
    db: Session, shifts: list[Shift], start: datetime, end: datetime, tracked: bool
) -> list[Item]:
    out: list[Item] = []
    for s in shifts:
        link = f"/shifts/{s.id}"
        if s.started_at and start <= s.started_at < end:
            out.append(
                Item(
                    s.started_at,
                    "SHIFT_START",
                    f"بدء وردية — {s.driver.full_name}",
                    f"عداد البداية {s.start_odometer_km} كم"
                    if s.start_odometer_km is not None
                    else None,
                    link=link,
                )
            )
        if s.ended_at and start <= s.ended_at < end:
            out.append(
                Item(
                    s.ended_at,
                    "SHIFT_END",
                    "انتهاء الوردية",
                    f"عداد الإنهاء {s.end_odometer_km} كم"
                    if s.end_odometer_km is not None
                    else None,
                    link=link,
                )
            )
        for x in s.sessions:
            if x.status is SessionStatus.CANCELLED:
                continue
            name = x.operation_type.name_ar + (f" — {x.route.name}" if x.route else "")
            if start <= x.started_at < end:
                out.append(Item(x.started_at, "OPERATION", f"بدء تشغيل: {name}", link=link))
            if x.ended_at and start <= x.ended_at < end:
                out.append(Item(x.ended_at, "OPERATION", f"انتهاء تشغيل: {name}", link=link))
        if tracked:
            for g in tracking.shift_track(db, s.id).gaps:
                if start <= g.start < end:
                    out.append(
                        Item(
                            g.start,
                            "GPS_GAP",
                            f"انقطاع تتبع {round(g.seconds / 60)} دقيقة",
                            "لا يعني بالضرورة وجود مشكلة",
                            until=g.end,
                            link=link,
                        )
                    )
    return out


def _route_and_school(
    db: Session, vid: uuid.UUID, day: date, start: datetime, end: datetime
) -> list[Item]:
    out = [
        Item(e.occurred_at, "ROUTE", ROUTE_EVENT_AR[e.event_type])
        for e in db.scalars(
            select(RouteEvent).where(
                RouteEvent.vehicle_id == vid,
                RouteEvent.status == EventStatus.ACTIVE,
                RouteEvent.event_type.in_(list(ROUTE_EVENT_AR)),
                RouteEvent.occurred_at >= start,
                RouteEvent.occurred_at < end,
            )
        ).all()
    ]
    for r in db.scalars(
        select(SchoolRun).where(SchoolRun.vehicle_id == vid, SchoolRun.service_date == day)
    ).all():
        out.append(
            Item(
                r.actual_start_at or r.scheduled_start_at,
                "SCHOOL_RUN",
                f"دورة مدرسة{f' — {r.label}' if r.label else ''}",
                status=SCHOOL_STATUS_AR.get(r.status.value, r.status.value),
                until=r.actual_end_at or r.scheduled_end_at,
            )
        )
    return out


def _money(
    db: Session, vid: uuid.UUID, day: date, start: datetime, end: datetime, sections: set[Section]
) -> list[Item]:
    out: list[Item] = []
    if Section.FUEL in sections:
        for f in db.scalars(
            select(FuelTransaction).where(
                FuelTransaction.vehicle_id == vid,
                FuelTransaction.occurred_at >= start,
                FuelTransaction.occurred_at < end,
            )
        ).all():
            out.append(
                Item(
                    f.occurred_at,
                    "FUEL",
                    f"{f.fuel_type.name_ar} {f.quantity.normalize()}",
                    amount=f.total_amount,
                    status=STATUS_AR[f.status],
                    link=f"/finance/fuel/{f.id}",
                )
            )
    if Section.EXPENSES in sections:
        for e in db.scalars(
            select(Expense).where(
                Expense.vehicle_id == vid, Expense.occurred_at >= start, Expense.occurred_at < end
            )
        ).all():
            out.append(
                Item(
                    e.occurred_at,
                    "EXPENSE",
                    e.category.name_ar,
                    e.notes,
                    e.amount,
                    STATUS_AR[e.status],
                    link=f"/finance/expenses/{e.id}",
                )
            )
    if Section.REVENUE in sections:
        for r in db.scalars(
            select(RevenueEntry).where(
                RevenueEntry.vehicle_id == vid, RevenueEntry.occurred_on == day
            )
        ).all():
            out.append(
                Item(
                    None,
                    "REVENUE",
                    REVENUE_KIND_AR.get(r.kind.value, r.kind.value),
                    amount=r.amount,
                    status=STATUS_AR[r.status],
                    link=f"/finance/revenue/{r.id}",
                )
            )
    if Section.CASH in sections:
        closeouts = db.scalars(
            select(ShiftCloseout).where(
                ShiftCloseout.vehicle_id == vid, ShiftCloseout.service_date == day
            )
        ).all()
        for c in closeouts:
            out.append(
                Item(
                    c.submitted_at,
                    "CLOSEOUT",
                    "تقفيل الوردية",
                    f"تحصيل {c.collection_amount} ج.م",
                    c.collection_amount,
                    "ملغي" if c.voided_at else None,
                    link=f"/cash?date={day}",
                )
            )
        if closeouts:
            for x in db.scalars(
                select(CashCollection).where(
                    CashCollection.closeout_id.in_([c.id for c in closeouts]),
                    CashCollection.voided_at.is_(None),
                )
            ).all():
                out.append(Item(x.collected_at, "CASH", "تحصيل نقدية من السائق", x.note, x.amount))
    return out


def timeline(db: Session, vehicle_id: uuid.UUID, day: date, sections: set[Section]) -> list[Item]:
    start, end = local_day_bounds_utc(day)
    items: list[Item] = []
    if Section.ASSIGNMENTS in sections:
        items += _assignments(db, vehicle_id, start, end)
    if Section.SHIFTS in sections:
        shifts = list(
            db.scalars(
                select(Shift).where(
                    Shift.vehicle_id == vehicle_id,
                    Shift.status.in_((ShiftStatus.ACTIVE, ShiftStatus.COMPLETED)),
                    Shift.started_at < end,
                    or_(Shift.ended_at.is_(None), Shift.ended_at >= start),
                )
            ).all()
        )
        items += _shifts(db, shifts, start, end, Section.TRACKING in sections)
        items += _route_and_school(db, vehicle_id, day, start, end)
    items += _money(db, vehicle_id, day, start, end, sections)
    if Section.MAINTENANCE in sections:
        for m in db.scalars(
            select(MaintenanceRecord).where(
                MaintenanceRecord.vehicle_id == vehicle_id, MaintenanceRecord.performed_on == day
            )
        ).all():
            items.append(
                Item(
                    m.downtime_start,
                    "MAINTENANCE",
                    m.type.name_ar,
                    m.description,
                    m.parts_cost + m.labor_cost + m.other_cost,
                    until=m.downtime_end,
                    link=f"/maintenance/records/{m.id}",
                )
            )
    if Section.REVIEW in sections:
        for c in db.scalars(
            select(OperationalException).where(
                OperationalException.vehicle_id == vehicle_id,
                OperationalException.occurred_at >= start,
                OperationalException.occurred_at < end,
            )
        ).all():
            items.append(
                Item(
                    c.occurred_at,
                    "REVIEW",
                    c.summary,
                    status=CASE_STATUS_AR[c.status],
                    link=f"/exceptions/{c.id}",
                )
            )
    # Day-level items first, then by time.
    return sorted(items, key=lambda i: (i.at is not None, i.at or start))


__all__ = ["Item", "Section", "timeline"]
