"""Persist route/geofence events for operation sessions and admin corrections."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.time import utcnow
from app.models.route_events import (
    EventSource,
    EventStatus,
    LegDirection,
    RouteEvent,
    RouteEventType,
)
from app.models.shift import OperationSession, SessionStatus
from app.models.tracking import GpsPoint, PointQuality
from app.models.user import User
from app.services import audit
from app.services.geofence import Geofence, detect_route_events
from app.services.track_analysis import TrackPoint

logger = logging.getLogger(__name__)
SUPERSEDED = "superseded_by_recompute"


def _dedupe_key(
    session_id: uuid.UUID, event_type: RouteEventType, stop_id: uuid.UUID | None, at: datetime
) -> str:
    return f"{session_id}:{event_type.value}:{stop_id or '-'}:{int(at.timestamp())}"


def detect_for_session(db: Session, session: OperationSession) -> dict[str, int]:
    """Recompute AUTO events for a session (no commit; caller commits)."""
    route = session.route
    if route is None:
        return {"events": 0}
    fences = [
        Geofence(s.id, s.kind, float(s.latitude), float(s.longitude), float(s.radius_m))
        for s in route.stops
        if s.latitude is not None and s.longitude is not None
    ]
    if not fences:
        return {"events": 0}
    end = session.ended_at or utcnow()
    points = [
        TrackPoint(p.recorded_at, p.latitude, p.longitude, p.accuracy_m, p.speed_mps)
        for p in db.scalars(
            select(GpsPoint)
            .where(
                GpsPoint.shift_id == session.shift_id,
                GpsPoint.quality == PointQuality.VALID,
                GpsPoint.recorded_at >= session.started_at,
                GpsPoint.recorded_at <= end,
            )
            .order_by(GpsPoint.recorded_at)
        ).all()
    ]
    detected = detect_route_events(points, fences, pattern=route.trip_pattern)
    keys = []
    rows = []
    for e in detected:
        key = _dedupe_key(session.id, e.event_type, e.stop_id, e.occurred_at)
        keys.append(key)
        rows.append(
            {
                "id": uuid.uuid4(),
                "shift_id": session.shift_id,
                "session_id": session.id,
                "route_id": route.id,
                "stop_id": e.stop_id,
                "vehicle_id": session.shift.vehicle_id,
                "event_type": e.event_type,
                "direction": e.direction,
                "occurred_at": e.occurred_at,
                "sequence_no": e.sequence_no,
                "source": EventSource.AUTO,
                "status": EventStatus.ACTIVE,
                "dedupe_key": key,
            }
        )
    if rows:
        db.execute(
            insert(RouteEvent).values(rows).on_conflict_do_nothing(index_elements=["dedupe_key"])
        )
        # Sequence numbers may shift when late points arrive; keep them current.
        for row in rows:
            db.execute(
                update(RouteEvent)
                .where(
                    RouteEvent.dedupe_key == row["dedupe_key"],
                    RouteEvent.source == EventSource.AUTO,
                )
                .values(sequence_no=row["sequence_no"], direction=row["direction"])
            )
        # An event superseded earlier but produced again (late points) is restored;
        # events voided by an admin stay voided.
        db.execute(
            update(RouteEvent)
            .where(RouteEvent.dedupe_key.in_(keys), RouteEvent.void_reason == SUPERSEDED)
            .values(status=EventStatus.ACTIVE, void_reason=None)
        )
    stale = db.scalars(
        select(RouteEvent).where(
            RouteEvent.session_id == session.id,
            RouteEvent.source == EventSource.AUTO,
            RouteEvent.status == EventStatus.ACTIVE,
            RouteEvent.dedupe_key.not_in(keys) if keys else RouteEvent.id.is_not(None),
        )
    ).all()
    for ev in stale:
        ev.status = EventStatus.VOIDED
        ev.void_reason = SUPERSEDED
    db.flush()
    return {"events": len(rows), "voided": len(stale)}


def detect_safely(db: Session, session_ids: list[uuid.UUID]) -> None:
    """Run detection without ever failing the caller (e.g. GPS ingestion)."""
    for session_id in session_ids:
        session = db.get(OperationSession, session_id)
        if session is None or session.route_id is None:
            continue
        try:
            with db.begin_nested():
                detect_for_session(db, session)
        except Exception:
            logger.exception("route_event_detection_failed", extra={"session_id": str(session_id)})


def sessions_for_points(
    db: Session, shift_id: uuid.UUID, start: datetime, end: datetime
) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(OperationSession.id).where(
                OperationSession.shift_id == shift_id,
                OperationSession.route_id.is_not(None),
                OperationSession.status != SessionStatus.CANCELLED,
                OperationSession.started_at <= end,
                (OperationSession.ended_at.is_(None)) | (OperationSession.ended_at >= start),
            )
        ).all()
    )


def list_events(db: Session, session_id: uuid.UUID) -> list[RouteEvent]:
    return list(
        db.scalars(
            select(RouteEvent)
            .where(RouteEvent.session_id == session_id)
            .order_by(RouteEvent.occurred_at, RouteEvent.created_at)
        ).all()
    )


def counts(db: Session, session_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    out: dict[uuid.UUID, dict[str, int]] = {sid: {"loops": 0, "legs": 0} for sid in session_ids}
    if not session_ids:
        return out
    rows = db.execute(
        select(RouteEvent.session_id, RouteEvent.event_type, func.count())
        .where(
            RouteEvent.session_id.in_(session_ids),
            RouteEvent.status == EventStatus.ACTIVE,
            RouteEvent.event_type.in_(
                [RouteEventType.LOOP_COMPLETED, RouteEventType.LEG_COMPLETED]
            ),
        )
        .group_by(RouteEvent.session_id, RouteEvent.event_type)
    ).all()
    for sid, etype, n in rows:
        out[sid]["loops" if etype is RouteEventType.LOOP_COMPLETED else "legs"] = n
    return out


def get_session(db: Session, session_id: uuid.UUID) -> OperationSession:
    session = db.get(OperationSession, session_id)
    if session is None:
        raise NotFoundError("التشغيل غير موجود")
    return session


def recompute(db: Session, *, actor: User, session_id: uuid.UUID) -> dict[str, int]:
    session = get_session(db, session_id)
    if session.route_id is None:
        raise ValidationFailed("هذا التشغيل بدون مسار", code="session_without_route")
    result = detect_for_session(db, session)
    audit.record(
        db,
        action="route_events.recomputed",
        actor=actor,
        entity_type="shift",
        entity_id=session.shift_id,
        details={"session_id": session.id, **result},
    )
    db.commit()
    return result


def add_manual_event(
    db: Session,
    *,
    actor: User,
    session_id: uuid.UUID,
    event_type: RouteEventType,
    occurred_at: datetime,
    direction: LegDirection | None,
    reason: str,
) -> RouteEvent:
    session = get_session(db, session_id)
    if session.route_id is None:
        raise ValidationFailed("هذا التشغيل بدون مسار", code="session_without_route")
    end = session.ended_at or utcnow()
    if not (session.started_at <= occurred_at <= end):
        raise ValidationFailed("الوقت خارج فترة التشغيل", code="time_outside_session")
    event = RouteEvent(
        shift_id=session.shift_id,
        session_id=session.id,
        route_id=session.route_id,
        vehicle_id=session.shift.vehicle_id,
        event_type=event_type,
        direction=direction,
        occurred_at=occurred_at,
        source=EventSource.MANUAL,
        status=EventStatus.ACTIVE,
        dedupe_key=f"manual:{uuid.uuid4()}",
        reason=reason,
        created_by_id=actor.id,
    )
    db.add(event)
    db.flush()
    audit.record(
        db,
        action="route_event.manual_added",
        actor=actor,
        entity_type="shift",
        entity_id=session.shift_id,
        details={"session_id": session.id, "event_id": event.id, "event_type": event_type.value},
        reason=reason,
    )
    db.commit()
    return event


def void_event(db: Session, *, actor: User, event_id: uuid.UUID, reason: str) -> RouteEvent:
    event = db.get(RouteEvent, event_id)
    if event is None:
        raise NotFoundError("الحدث غير موجود")
    if event.status is EventStatus.VOIDED:
        raise ConflictError("الحدث ملغى بالفعل", code="event_already_voided")
    event.status = EventStatus.VOIDED
    event.void_reason = reason
    event.voided_by_id = actor.id
    audit.record(
        db,
        action="route_event.voided",
        actor=actor,
        entity_type="shift",
        entity_id=event.shift_id,
        details={
            "event_id": event.id,
            "event_type": event.event_type.value,
            "source": event.source.value,
        },
        reason=reason,
    )
    db.commit()
    return event
