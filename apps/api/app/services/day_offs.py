"""Driver day-offs («تسجيل اليوم إجازة»).

A day-off says the driver will not work that day: no shift can start, so
no location is collected and no transactions are expected. It is visible
to management on the cash board. Registering twice returns the same
record; cancelling keeps the row (with who and when) for history.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.time import local_day_bounds_utc, utcnow
from app.models.cash import DriverDayOff
from app.models.driver import Driver
from app.models.finance import RecordSource
from app.models.shift import Shift, ShiftStatus
from app.models.user import User
from app.services import audit

ENTITY = "driver_day_off"


def live(db: Session, driver_id: uuid.UUID, day: date) -> DriverDayOff | None:
    return db.scalar(
        select(DriverDayOff).where(
            DriverDayOff.driver_id == driver_id,
            DriverDayOff.day == day,
            DriverDayOff.cancelled_at.is_(None),
        )
    )


def for_day(db: Session, day: date) -> list[DriverDayOff]:
    return list(
        db.scalars(
            select(DriverDayOff)
            .where(DriverDayOff.day == day, DriverDayOff.cancelled_at.is_(None))
            .order_by(DriverDayOff.created_at)
        ).all()
    )


def for_driver(db: Session, driver_id: uuid.UUID, start: date, end: date) -> list[DriverDayOff]:
    return list(
        db.scalars(
            select(DriverDayOff).where(
                DriverDayOff.driver_id == driver_id,
                DriverDayOff.day >= start,
                DriverDayOff.day <= end,
                DriverDayOff.cancelled_at.is_(None),
            )
        ).all()
    )


def _ensure_no_work(db: Session, driver_id: uuid.UUID, day: date) -> None:
    active = db.scalar(
        select(Shift.id).where(Shift.driver_id == driver_id, Shift.status == ShiftStatus.ACTIVE)
    )
    if active is not None:
        raise ConflictError("توجد وردية نشطة؛ أنهِ الوردية أولًا", code="active_shift")
    start, end = local_day_bounds_utc(day)
    worked = db.scalar(
        select(Shift.id).where(
            Shift.driver_id == driver_id,
            Shift.status.in_((ShiftStatus.ACTIVE, ShiftStatus.COMPLETED)),
            Shift.started_at >= start,
            Shift.started_at < end,
        )
    )
    if worked is not None:
        raise ConflictError(
            "توجد وردية في هذا اليوم بالفعل؛ لا يمكن تسجيله إجازة", code="shift_that_day"
        )


def register(
    db: Session,
    *,
    actor: User,
    driver_id: uuid.UUID,
    day: date,
    note: str | None,
    source: RecordSource,
) -> DriverDayOff:
    if db.get(Driver, driver_id) is None:
        raise NotFoundError("السائق غير موجود")
    existing = live(db, driver_id, day)
    if existing is not None:
        return existing
    _ensure_no_work(db, driver_id, day)
    off = DriverDayOff(
        driver_id=driver_id,
        day=day,
        note=(note or "").strip() or None,
        source=source,
        created_by_id=actor.id,
    )
    try:
        with db.begin_nested():
            db.add(off)
            db.flush()
    except IntegrityError:  # registered concurrently: return that one
        again = live(db, driver_id, day)
        if again is None:
            raise
        return again
    audit.record(
        db,
        action=f"{ENTITY}.registered",
        actor=actor,
        entity_type="driver",
        entity_id=driver_id,
        details={"day_off_id": off.id, "day": day.isoformat(), "source": source.value},
    )
    db.commit()
    return off


def cancel(
    db: Session, *, actor: User, driver_id: uuid.UUID, day: date, reason: str | None
) -> DriverDayOff:
    off = live(db, driver_id, day)
    if off is None:
        raise NotFoundError("لا توجد إجازة مسجّلة في هذا اليوم")
    return _cancel(db, actor=actor, off=off, reason=reason)


def cancel_by_id(
    db: Session, *, actor: User, day_off_id: uuid.UUID, reason: str | None
) -> DriverDayOff:
    off = db.get(DriverDayOff, day_off_id)
    if off is None or off.cancelled_at is not None:
        raise NotFoundError("الإجازة غير موجودة أو ملغاة")
    return _cancel(db, actor=actor, off=off, reason=reason)


def _cancel(db: Session, *, actor: User, off: DriverDayOff, reason: str | None) -> DriverDayOff:
    off.cancelled_at = utcnow()
    off.cancelled_by_id = actor.id
    off.cancel_reason = (reason or "").strip() or None
    audit.record(
        db,
        action=f"{ENTITY}.cancelled",
        actor=actor,
        entity_type="driver",
        entity_id=off.driver_id,
        reason=off.cancel_reason,
        details={"day_off_id": off.id, "day": off.day.isoformat()},
    )
    db.commit()
    return off


__all__ = ["cancel", "cancel_by_id", "for_day", "for_driver", "live", "register"]
