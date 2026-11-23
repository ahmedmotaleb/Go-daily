"""Passenger counts (U11): recorded by people, with source and confidence.

Staff record counts from the driver's report or a supervisor's count. The
TICKETING and HARDWARE sources are reserved for approved integrations and
cannot be entered by hand. Counts are never inferred and never edited: a
wrong count is voided with a reason.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, field_error
from app.core.time import utcnow
from app.models.passengers import CountConfidence, CountSource, PassengerCount
from app.models.route_events import LegDirection
from app.models.shift import OperationSession, Shift, ShiftStatus
from app.models.user import User
from app.services import audit

MANUAL_SOURCES = (CountSource.DRIVER, CountSource.SUPERVISOR)
GRACE = timedelta(minutes=15)


def _shift(db: Session, shift_id: uuid.UUID) -> Shift:
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise NotFoundError("الوردية غير موجودة")
    return shift


def record(
    db: Session,
    *,
    actor: User,
    shift_id: uuid.UUID,
    passengers: int,
    source: CountSource,
    confidence: CountConfidence,
    counted_at: datetime | None,
    session_id: uuid.UUID | None,
    direction: LegDirection | None,
    note: str | None,
) -> PassengerCount:
    shift = _shift(db, shift_id)
    if shift.status not in (ShiftStatus.ACTIVE, ShiftStatus.COMPLETED) or shift.started_at is None:
        raise ConflictError("العد يُسجل لوردية بدأت فقط", code="invalid_shift_state")
    if source not in MANUAL_SOURCES:
        raise field_error(
            "source", "هذا المصدر لنظام تذاكر أو جهاز عد معتمد فقط", code="integration_source"
        )
    at = counted_at or utcnow()
    end = shift.ended_at or utcnow()
    if not (shift.started_at - GRACE <= at <= end + GRACE):
        raise field_error("counted_at", "وقت العد خارج الوردية", code="outside_shift")
    route_id = None
    if session_id is not None:
        session = db.get(OperationSession, session_id)
        if session is None or session.shift_id != shift.id:
            raise field_error("session_id", "التشغيل لا يتبع هذه الوردية")
        route_id = session.route_id
    count = PassengerCount(
        shift_id=shift.id,
        session_id=session_id,
        vehicle_id=shift.vehicle_id,
        route_id=route_id,
        direction=direction,
        counted_at=at,
        passengers=passengers,
        source=source,
        confidence=confidence,
        note=note,
        recorded_by_id=actor.id,
    )
    db.add(count)
    db.flush()
    audit.record(
        db,
        action="passenger_count.recorded",
        actor=actor,
        entity_type="passenger_count",
        entity_id=count.id,
        details={
            "shift_id": shift.id,
            "passengers": passengers,
            "source": source.value,
            "confidence": confidence.value,
        },
    )
    db.commit()
    return count


def for_shift(db: Session, shift_id: uuid.UUID) -> list[PassengerCount]:
    _shift(db, shift_id)
    return list(
        db.scalars(
            select(PassengerCount)
            .where(PassengerCount.shift_id == shift_id)
            .order_by(PassengerCount.counted_at)
        ).all()
    )


def void(db: Session, *, actor: User, count_id: uuid.UUID, reason: str) -> PassengerCount:
    count = db.get(PassengerCount, count_id)
    if count is None:
        raise NotFoundError("العد غير موجود")
    if count.voided_at is not None:
        raise ConflictError("العد ملغي بالفعل", code="already_voided")
    count.voided_at = utcnow()
    count.voided_by_id = actor.id
    count.void_reason = reason
    audit.record(
        db,
        action="passenger_count.voided",
        actor=actor,
        entity_type="passenger_count",
        entity_id=count.id,
        reason=reason,
    )
    db.commit()
    return count


__all__ = ["MANUAL_SOURCES", "for_shift", "record", "void"]
