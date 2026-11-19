"""Read models for the cash board («تحصيل نقدية السائقين») and «حسابي مع الإدارة»."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_day_bounds_utc, local_today, to_local_date
from app.models.cash import CashCollection, DriverDayOff, ShiftCloseout
from app.models.driver import Driver
from app.models.shift import Shift, ShiftStatus
from app.schemas.cash import (
    AccountDay,
    BoardRow,
    CashAccountOut,
    CashBoardOut,
    CloseoutLine,
    CloseoutOut,
    CollectionOut,
    DayOffOut,
)
from app.schemas.shift import PersonRef, VehicleRef
from app.services import cash, day_offs
from app.services import finance_common as fc

ZERO = Decimal("0")
STATUS_ORDER = {"WAITING": 0, "PARTIAL": 1, "COLLECTED": 2, "NOTHING_DUE": 3}
KIND_ORDER = {"CLOSEOUT": 0, "ENDED_NOT_CLOSED": 1, "OPEN_SHIFT": 2, "DAY_OFF": 3}


def collection_out(c: CashCollection) -> CollectionOut:
    return CollectionOut(
        id=c.id,
        driver_id=c.driver_id,
        closeout_id=c.closeout_id,
        amount=c.amount,
        collected_at=c.collected_at,
        note=c.note,
        collected_by=(
            PersonRef(id=c.collected_by.id, full_name=c.collected_by.full_name)
            if c.collected_by
            else None
        ),
        voided_at=c.voided_at,
        void_reason=c.void_reason,
    )


def day_off_out(off: DriverDayOff) -> DayOffOut:
    return DayOffOut(
        id=off.id,
        driver=PersonRef(id=off.driver.id, full_name=off.driver.full_name),
        day=off.day,
        note=off.note,
        source=off.source,
        created_at=off.created_at,
    )


def _vehicle_ref(shift: Shift) -> VehicleRef:
    return VehicleRef(
        id=shift.vehicle.id,
        internal_code=shift.vehicle.internal_code,
        plate_number=shift.vehicle.plate_number,
    )


def closeout_out(
    db: Session,
    c: ShiftCloseout,
    view: cash.DriverView,
    receipts: list[uuid.UUID] | None = None,
) -> CloseoutOut:
    shift = db.get(Shift, c.shift_id)
    assert shift is not None  # noqa: S101 - foreign key
    figures = view.figures.get(c.id)
    position = view.positions.get(c.id) or cash.Position(status="NOTHING_DUE")
    if figures is None:  # voided close-outs are outside the running account
        figures = cash.Figures(lines=[], deductions=ZERO, net=ZERO, collection_booked=False)
    return CloseoutOut(
        id=c.id,
        shift_id=c.shift_id,
        driver=PersonRef(id=c.driver.id, full_name=c.driver.full_name),
        vehicle=_vehicle_ref(shift),
        service_date=c.service_date,
        submitted_at=c.submitted_at,
        source=c.source,
        operation_label=cash.operation_label(shift),
        start_odometer_km=shift.start_odometer_km,
        end_odometer_km=c.end_odometer_km,
        start_odometer_photo_id=shift.start_odometer_photo_id,
        collection_amount=c.collection_amount,
        collection_booked=figures.collection_booked,
        lines=[
            CloseoutLine(
                key=ln.key,
                label=ln.label,
                quantity=ln.quantity,
                unit=ln.unit,
                amount=ln.amount,
                record_status=ln.record_status,
                deducted=ln.deducted,
            )
            for ln in figures.lines
        ],
        maintenance_kind=c.maintenance_kind,
        maintenance_note=c.maintenance_note,
        notes=c.notes,
        receipt_attachment_ids=receipts or [],
        deductions=figures.deductions,
        net_amount=figures.net,
        carried_before=position.carried_before,
        total_due=position.total_due,
        collected=position.collected,
        remaining=position.remaining,
        status=position.status,
        collections=[collection_out(x) for x in view.collections.get(c.id, [])],
        voided_at=c.voided_at,
        void_reason=c.void_reason,
    )


def closeout_detail(db: Session, closeout_id: uuid.UUID) -> CloseoutOut:
    c = cash.get_closeout(db, closeout_id)
    view = cash.driver_views(db, {c.driver_id})[c.driver_id]
    return closeout_out(db, c, view, cash.receipt_ids(db, [c.id]).get(c.id))


def board(db: Session, day: date) -> CashBoardOut:
    closeouts = cash.closeouts_on(db, day)
    offs = day_offs.for_day(db, day)
    open_shifts = cash.shifts_without_closeout(db, day)
    drivers = (
        {c.driver_id for c in closeouts}
        | {o.driver_id for o in offs}
        | {s.driver_id for s in open_shifts}
    )
    views = cash.driver_views(db, drivers)
    receipts = cash.receipt_ids(db, [c.id for c in closeouts])
    rows: list[BoardRow] = []
    for c in closeouts:
        out = closeout_out(db, c, views[c.driver_id], receipts.get(c.id))
        rows.append(
            BoardRow(
                kind="CLOSEOUT",
                driver=out.driver,
                vehicle=out.vehicle,
                operation_label=out.operation_label,
                closeout=out,
                shift_id=c.shift_id,
                outstanding=views[c.driver_id].outstanding,
            )
        )
    for s in open_shifts:
        rows.append(
            BoardRow(
                kind="OPEN_SHIFT" if s.status is ShiftStatus.ACTIVE else "ENDED_NOT_CLOSED",
                driver=PersonRef(id=s.driver.id, full_name=s.driver.full_name),
                vehicle=_vehicle_ref(s),
                operation_label=cash.operation_label(s),
                shift_id=s.id,
                started_at=s.started_at,
                outstanding=views[s.driver_id].outstanding,
            )
        )
    for o in offs:
        rows.append(
            BoardRow(
                kind="DAY_OFF",
                driver=PersonRef(id=o.driver.id, full_name=o.driver.full_name),
                vehicle=None,
                operation_label=None,
                day_off=day_off_out(o),
                outstanding=views[o.driver_id].outstanding,
            )
        )
    rows.sort(
        key=lambda r: (
            KIND_ORDER[r.kind],
            STATUS_ORDER.get(r.closeout.status, 9) if r.closeout else 0,
            r.driver.full_name,
        )
    )
    start, end = local_day_bounds_utc(day)
    return CashBoardOut(
        day=day,
        net_due=fc.money(sum((r.closeout.net_amount for r in rows if r.closeout), ZERO)),
        closeouts=len(closeouts),
        collected=cash.collected_between(db, start, end),
        open_balance=fc.money(sum((max(v.outstanding, ZERO) for v in views.values()), ZERO)),
        day_offs=len(offs),
        open_shifts=len(open_shifts),
        rows=rows,
    )


def account(db: Session, driver_id: uuid.UUID, days: int = 14) -> CashAccountOut:
    driver = db.get(Driver, driver_id)
    assert driver is not None  # noqa: S101 - callers resolve the driver
    date_from, date_to = cash.account_window(days)
    view = cash.driver_views(db, {driver_id})[driver_id]
    closeouts = list(
        db.scalars(
            select(ShiftCloseout)
            .where(
                ShiftCloseout.driver_id == driver_id,
                ShiftCloseout.voided_at.is_(None),
                ShiftCloseout.service_date >= date_from,
                ShiftCloseout.service_date <= date_to,
            )
            .order_by(ShiftCloseout.service_date.desc(), ShiftCloseout.submitted_at.desc())
        ).all()
    )
    receipts = cash.receipt_ids(db, [c.id for c in closeouts])
    items: list[AccountDay] = [
        AccountDay(
            day=c.service_date,
            kind="CLOSEOUT",
            closeout=closeout_out(db, c, view, receipts.get(c.id)),
        )
        for c in closeouts
    ]
    offs = day_offs.for_driver(db, driver_id, date_from, date_to)
    items += [AccountDay(day=o.day, kind="DAY_OFF", day_off=day_off_out(o)) for o in offs]
    start = local_day_bounds_utc(date_from)[0]
    end = local_day_bounds_utc(date_to)[1]
    in_window = [x for xs in view.collections.values() for x in xs if start <= x.collected_at < end]
    items += [
        AccountDay(
            day=to_local_date(x.collected_at), kind="COLLECTION", collection=collection_out(x)
        )
        for x in in_window
        if x.closeout_id is None
    ]
    items.sort(key=lambda d: d.day, reverse=True)
    today = local_today()
    today_offs = [o for o in offs if o.day == today]
    today_closeout = next((i.closeout for i in items if i.closeout and i.day == today), None)
    return CashAccountOut(
        driver=PersonRef(id=driver.id, full_name=driver.full_name),
        outstanding=view.outstanding,
        date_from=date_from,
        date_to=date_to,
        due_total=fc.money(sum((view.figures[c.id].net for c in closeouts), ZERO)),
        collected_total=fc.money(sum((x.amount for x in in_window), ZERO)),
        day_off_days=len(offs),
        days=items,
        today_day_off=day_off_out(today_offs[0]) if today_offs else None,
        today_closeout=today_closeout,
    )


__all__ = ["account", "board", "closeout_detail", "closeout_out", "collection_out", "day_off_out"]
