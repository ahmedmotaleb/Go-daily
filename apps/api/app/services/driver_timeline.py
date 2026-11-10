"""Driver daily timeline (U25): everything recorded about one driver on one day.

The driver's counterpart of the vehicle timeline (U24), following the
driver across vehicles: assignment changes, day-off, shifts with their
operations and GPS gaps, loops and legs, fuel, expenses, revenue,
close-outs and cash handed over, account entries (advances, deductions,
settlements, payments) and review cases. Each kind is included only when
the caller may see it (the route maps permissions to sections); account
entries need settlement access, so operations staff never see a driver's
money.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.time import local_day_bounds_utc
from app.models.assignment import DriverVehicleAssignment
from app.models.cash import CashCollection, DriverDayOff, ShiftCloseout
from app.models.exceptions import OperationalException
from app.models.finance import (
    DriverLedgerEntry,
    Expense,
    FuelTransaction,
    LedgerEntryType,
    RevenueEntry,
)
from app.models.route_events import EventStatus, RouteEvent
from app.models.shift import Shift, ShiftStatus
from app.services.reports import REVENUE_KIND_AR
from app.services.vehicle_timeline import (
    CASE_STATUS_AR,
    ROUTE_EVENT_AR,
    STATUS_AR,
    Item,
    Section,
    _shifts,
)

LEDGER_AR = {
    LedgerEntryType.EARNING: "استحقاق من تسوية",
    LedgerEntryType.BONUS: "مكافأة",
    LedgerEntryType.REIMBURSEMENT: "تعويض مصروف دفعه السائق",
    LedgerEntryType.CASH_HANDOVER: "تسليم نقدية",
    LedgerEntryType.ADVANCE: "سلفة",
    LedgerEntryType.DEDUCTION: "خصم",
    LedgerEntryType.PAYMENT: "دفعة للسائق",
    LedgerEntryType.CASH_COLLECTED: "نقدية مع السائق",
    LedgerEntryType.ADJUSTMENT: "تسوية يدوية",
}


def _assignments(db: Session, did: uuid.UUID, start: datetime, end: datetime) -> list[Item]:
    out = []
    for a in db.scalars(
        select(DriverVehicleAssignment).where(
            DriverVehicleAssignment.driver_id == did,
            or_(
                DriverVehicleAssignment.starts_at.between(start, end),
                DriverVehicleAssignment.ends_at.between(start, end),
            ),
        )
    ).all():
        link = f"/vehicles/{a.vehicle_id}"
        if start <= a.starts_at < end:
            out.append(
                Item(a.starts_at, "ASSIGNMENT", f"تكليف على {a.vehicle.internal_code}", link=link)
            )
        if a.ends_at and start <= a.ends_at < end:
            out.append(
                Item(
                    a.ends_at,
                    "ASSIGNMENT",
                    f"انتهاء التكليف على {a.vehicle.internal_code}",
                    link=link,
                )
            )
    return out


def _money(
    db: Session, did: uuid.UUID, day: date, start: datetime, end: datetime, sections: set[Section]
) -> list[Item]:
    out: list[Item] = []
    if Section.FUEL in sections:
        for f in db.scalars(
            select(FuelTransaction).where(
                FuelTransaction.driver_id == did,
                FuelTransaction.occurred_at >= start,
                FuelTransaction.occurred_at < end,
            )
        ).all():
            out.append(
                Item(
                    f.occurred_at,
                    "FUEL",
                    f"{f.fuel_type.name_ar} {f.quantity.normalize()} — {f.vehicle.internal_code}",
                    amount=f.total_amount,
                    status=STATUS_AR[f.status],
                    link=f"/finance/fuel/{f.id}",
                )
            )
    if Section.EXPENSES in sections:
        for e in db.scalars(
            select(Expense).where(
                Expense.driver_id == did, Expense.occurred_at >= start, Expense.occurred_at < end
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
                RevenueEntry.driver_id == did, RevenueEntry.occurred_on == day
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
        out += _cash(db, did, day)
    return out


def _cash(db: Session, did: uuid.UUID, day: date) -> list[Item]:
    out: list[Item] = []
    closeouts = db.scalars(
        select(ShiftCloseout).where(
            ShiftCloseout.driver_id == did, ShiftCloseout.service_date == day
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
    start, end = local_day_bounds_utc(day)
    for x in db.scalars(
        select(CashCollection).where(
            CashCollection.driver_id == did,
            CashCollection.collected_at >= start,
            CashCollection.collected_at < end,
            CashCollection.voided_at.is_(None),
        )
    ).all():
        out.append(Item(x.collected_at, "CASH", "تسليم نقدية للإدارة", x.note, x.amount))
    return out


# Mirror the close-out and the cash handed over, already listed with cash access.
CASH_MIRRORS = (LedgerEntryType.CASH_COLLECTED, LedgerEntryType.CASH_HANDOVER)


def _ledger(db: Session, did: uuid.UUID, day: date, *, skip_cash: bool) -> list[Item]:
    return [
        Item(
            None,
            "LEDGER",
            LEDGER_AR.get(e.entry_type, e.entry_type.value),
            e.description,
            e.amount,
            "ملغي" if e.voided_at else None,
            link=f"/drivers/{did}",
        )
        for e in db.scalars(
            select(DriverLedgerEntry).where(
                DriverLedgerEntry.driver_id == did, DriverLedgerEntry.occurred_on == day
            )
        ).all()
        if not (skip_cash and e.entry_type in CASH_MIRRORS)
    ]


def timeline(
    db: Session, driver_id: uuid.UUID, day: date, sections: set[Section], *, ledger: bool
) -> list[Item]:
    start, end = local_day_bounds_utc(day)
    items: list[Item] = []
    if Section.ASSIGNMENTS in sections:
        items += _assignments(db, driver_id, start, end)
    if Section.SHIFTS in sections:
        off = db.scalar(
            select(DriverDayOff).where(
                DriverDayOff.driver_id == driver_id,
                DriverDayOff.day == day,
                DriverDayOff.cancelled_at.is_(None),
            )
        )
        if off is not None:
            items.append(Item(None, "DAY_OFF", "يوم إجازة", off.note))
        shifts = list(
            db.scalars(
                select(Shift).where(
                    Shift.driver_id == driver_id,
                    Shift.status.in_((ShiftStatus.ACTIVE, ShiftStatus.COMPLETED)),
                    Shift.started_at < end,
                    or_(Shift.ended_at.is_(None), Shift.ended_at >= start),
                )
            ).all()
        )
        items += _shifts(db, shifts, start, end, Section.TRACKING in sections)
        session_ids = [x.id for s in shifts for x in s.sessions]
        if session_ids:
            items += [
                Item(e.occurred_at, "ROUTE", ROUTE_EVENT_AR[e.event_type])
                for e in db.scalars(
                    select(RouteEvent).where(
                        RouteEvent.session_id.in_(session_ids),
                        RouteEvent.status == EventStatus.ACTIVE,
                        RouteEvent.event_type.in_(list(ROUTE_EVENT_AR)),
                    )
                ).all()
                if start <= e.occurred_at < end
            ]
    items += _money(db, driver_id, day, start, end, sections)
    if ledger:
        items += _ledger(db, driver_id, day, skip_cash=Section.CASH in sections)
    if Section.REVIEW in sections:
        for c in db.scalars(
            select(OperationalException).where(
                OperationalException.driver_id == driver_id,
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
    return sorted(items, key=lambda i: (i.at is not None, i.at or start))


__all__ = ["LEDGER_AR", "timeline"]
