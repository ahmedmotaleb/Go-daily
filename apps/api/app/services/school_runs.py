"""Scheduled school duties and their completion evidence."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.geo import point_to_polyline_m
from app.core.time import utcnow
from app.models.driver import Driver
from app.models.fleet import Vehicle
from app.models.operations import OperationKind, RouteDefinition
from app.models.route_events import (
    EventStatus,
    RouteEvent,
    RouteEventType,
    SchoolRun,
    SchoolRunStatus,
)
from app.models.shift import OperationSession, SessionStatus
from app.models.tracking import GpsPoint, PointQuality
from app.models.user import User
from app.schemas.common import PageParams
from app.services import audit
from app.services.common import paginate
from app.services.track_analysis import TrackPoint, find_gaps

LINK_TOLERANCE = timedelta(minutes=60)
MISSED_GRACE = timedelta(minutes=60)
OPEN_STATUSES = (SchoolRunStatus.SCHEDULED, SchoolRunStatus.IN_PROGRESS)
RUN_AUDITED = (
    "status",
    "vehicle_id",
    "driver_id",
    "scheduled_start_at",
    "scheduled_end_at",
    "actual_start_at",
    "actual_end_at",
    "status_reason",
    "notes",
    "session_id",
)


def _local(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=get_settings().tz)


def _school_route(db: Session, route_id: uuid.UUID) -> RouteDefinition:
    route = db.get(RouteDefinition, route_id)
    if route is None or route.operation_type.kind is not OperationKind.SCHOOL_ROUTE:
        raise ValidationFailed("اختر مسار مدرسة", code="not_a_school_route")
    if not route.is_active:
        raise ValidationFailed("المسار غير نشط", code="invalid_route")
    return route


def get_run(db: Session, run_id: uuid.UUID) -> SchoolRun:
    run = db.get(SchoolRun, run_id)
    if run is None:
        raise NotFoundError("الدورة غير موجودة")
    return run


def refresh_missed(db: Session) -> int:
    """Mark scheduled runs whose window (plus grace) passed with no session as MISSED."""
    result = db.execute(
        update(SchoolRun)
        .where(
            SchoolRun.status == SchoolRunStatus.SCHEDULED,
            SchoolRun.session_id.is_(None),
            SchoolRun.scheduled_end_at < utcnow() - MISSED_GRACE,
        )
        .values(status=SchoolRunStatus.MISSED, status_reason="no_operation_recorded")
    )
    if result.rowcount:  # type: ignore[attr-defined]
        db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def list_runs(
    db: Session,
    params: PageParams,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    route_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    status: SchoolRunStatus | None = None,
) -> tuple[list[SchoolRun], int]:
    refresh_missed(db)
    stmt = select(SchoolRun)
    if date_from:
        stmt = stmt.where(SchoolRun.service_date >= date_from)
    if date_to:
        stmt = stmt.where(SchoolRun.service_date <= date_to)
    if route_id:
        stmt = stmt.where(SchoolRun.route_id == route_id)
    if vehicle_id:
        stmt = stmt.where(SchoolRun.vehicle_id == vehicle_id)
    if status:
        stmt = stmt.where(SchoolRun.status == status)
    return paginate(db, stmt.order_by(SchoolRun.scheduled_start_at, SchoolRun.id), params)


def _check_assignees(db: Session, vehicle_id: uuid.UUID, driver_id: uuid.UUID | None) -> None:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or not vehicle.is_active:
        raise ValidationFailed("المركبة غير صحيحة أو موقوفة", code="vehicle_not_active")
    if driver_id is not None and db.get(Driver, driver_id) is None:
        raise ValidationFailed("السائق غير موجود", code="driver_not_found")


def generate_runs(
    db: Session,
    *,
    actor: User,
    route_id: uuid.UUID,
    date_from: date,
    date_to: date,
    start_time: time,
    end_time: time,
    vehicle_id: uuid.UUID,
    driver_id: uuid.UUID | None,
    label: str | None,
    weekdays: list[int] | None,
) -> list[SchoolRun]:
    route = _school_route(db, route_id)
    _check_assignees(db, vehicle_id, driver_id)
    if date_to < date_from or (date_to - date_from).days > 120:
        raise ValidationFailed("الفترة غير صحيحة (حد أقصى 120 يومًا)", code="invalid_range")
    if end_time <= start_time:
        raise ValidationFailed("نهاية الدورة يجب أن تكون بعد بدايتها", code="invalid_range")
    days = set(weekdays or route.operating_days or range(1, 8))
    created: list[SchoolRun] = []
    day = date_from
    while day <= date_to:
        if day.isoweekday() in days:
            start = _local(day, start_time)
            exists = db.scalar(
                select(SchoolRun.id).where(
                    SchoolRun.route_id == route.id,
                    SchoolRun.vehicle_id == vehicle_id,
                    SchoolRun.scheduled_start_at == start,
                )
            )
            if exists is None:
                run = SchoolRun(
                    route_id=route.id,
                    service_date=day,
                    scheduled_start_at=start,
                    scheduled_end_at=_local(day, end_time),
                    vehicle_id=vehicle_id,
                    driver_id=driver_id,
                    label=label,
                    created_by_id=actor.id,
                )
                db.add(run)
                created.append(run)
        day += timedelta(days=1)
    db.flush()
    audit.record(
        db,
        action="school_runs.generated",
        actor=actor,
        entity_type="route",
        entity_id=route.id,
        details={
            "created": len(created),
            "from": date_from,
            "to": date_to,
            "vehicle_id": vehicle_id,
        },
    )
    db.commit()
    return created


# ------------------------------------------------------------------ session hooks


def link_session(db: Session, session: OperationSession) -> SchoolRun | None:
    """Attach a starting school-route session to its scheduled run (no commit)."""
    if session.route_id is None or session.operation_type.kind is not OperationKind.SCHOOL_ROUTE:
        return None
    run = db.scalar(
        select(SchoolRun)
        .where(
            SchoolRun.route_id == session.route_id,
            SchoolRun.vehicle_id == session.shift.vehicle_id,
            SchoolRun.status == SchoolRunStatus.SCHEDULED,
            SchoolRun.session_id.is_(None),
            SchoolRun.scheduled_start_at - LINK_TOLERANCE <= session.started_at,
            SchoolRun.scheduled_end_at + LINK_TOLERANCE >= session.started_at,
        )
        .order_by(SchoolRun.scheduled_start_at)
        .limit(1)
        .with_for_update()
    )
    if run is None:
        return None
    run.session_id = session.id
    run.actual_start_at = session.started_at
    run.status = SchoolRunStatus.IN_PROGRESS
    if run.driver_id is None:
        run.driver_id = session.shift.driver_id
    return run


# Outcomes the system decides; staff corrections ("manual: ...") are never overwritten.
AUTO_OUTCOMES = (
    SchoolRunStatus.COMPLETED,
    SchoolRunStatus.COMPLETED_LATE,
    SchoolRunStatus.INCOMPLETE,
    SchoolRunStatus.COMPLETED_UNVERIFIED,
)


def _minutes_late(actual: datetime | None, planned: datetime) -> int | None:
    if actual is None:
        return None
    return int((actual - planned).total_seconds() // 60)


def evaluate(db: Session, run: SchoolRun, session: OperationSession) -> None:
    """Decide the outcome of a finished run from its GPS evidence (no commit).

    - every required stop reached: مكتملة, or مكتملة بتأخير when the start or
      the arrival at the destination was later than the grace period;
    - stops missed although GPS covered the run: غير مكتملة;
    - stops missed and GPS too thin to tell: تحتاج مراجعة.
    Nothing is inferred for missing GPS; the evidence is stored with the run.
    """
    s = get_settings()
    route = db.get(RouteDefinition, run.route_id)
    assert route is not None and session.ended_at is not None  # noqa: S101
    required = [st for st in route.stops if st.latitude is not None and st.longitude is not None]
    events = db.scalars(
        select(RouteEvent).where(
            RouteEvent.session_id == session.id,
            RouteEvent.status == EventStatus.ACTIVE,
            RouteEvent.event_type.in_((RouteEventType.ENTERED, RouteEventType.REACHED_DESTINATION)),
        )
    ).all()
    reached = {e.stop_id for e in events if e.stop_id is not None}
    arrivals = [e.occurred_at for e in events if e.event_type is RouteEventType.REACHED_DESTINATION]
    arrival = min(arrivals) if arrivals else None
    missing = [st for st in required if st.id not in reached]

    track = [
        TrackPoint(p.recorded_at, p.latitude, p.longitude, p.accuracy_m, p.speed_mps)
        for p in db.scalars(
            select(GpsPoint)
            .where(
                GpsPoint.shift_id == session.shift_id,
                GpsPoint.quality == PointQuality.VALID,
                GpsPoint.recorded_at >= session.started_at,
                GpsPoint.recorded_at <= session.ended_at,
            )
            .order_by(GpsPoint.recorded_at)
        ).all()
    ]
    total = (session.ended_at - session.started_at).total_seconds()
    coverage = 0.0
    if total > 0:
        gaps = find_gaps(
            track,
            window_start=session.started_at,
            window_end=session.ended_at,
            max_gap_seconds=s.gps_gap_seconds,
        )
        coverage = round(100 * (1 - sum(g.seconds for g in gaps) / total), 1)
    line = [(float(st.latitude), float(st.longitude)) for st in required]  # type: ignore[arg-type]
    deviation = (
        round(max(point_to_polyline_m(p.latitude, p.longitude, line) for p in track))
        if track and line
        else None
    )
    start_late = _minutes_late(run.actual_start_at, run.scheduled_start_at)
    arrival_late = _minutes_late(arrival, run.scheduled_end_at)
    grace = s.school_late_grace_minutes
    late = (start_late is not None and start_late > grace) or (
        arrival_late is not None and arrival_late > grace
    )
    run.verification = {
        "required_stops": [{"id": str(st.id), "name": st.name} for st in required],
        "reached_stops": [str(st.id) for st in required if st.id in reached],
        "missing_stops": [st.name for st in missing],
        "arrived_at": arrival.isoformat() if arrival else None,
        "start_delay_minutes": start_late,
        "arrival_delay_minutes": arrival_late,
        "late_grace_minutes": grace,
        "gps_points": len(track),
        "gps_coverage_pct": coverage,
        "min_gps_coverage_pct": s.school_min_gps_coverage_pct,
        "max_deviation_m": deviation,
        "corridor_m": s.exception_route_corridor_m,
    }
    run.actual_end_at = session.ended_at
    if required and not missing:
        run.status = SchoolRunStatus.COMPLETED_LATE if late else SchoolRunStatus.COMPLETED
        run.status_reason = "gps_all_stops_reached_late" if late else "gps_all_stops_reached"
    elif required and coverage >= s.school_min_gps_coverage_pct:
        run.status = SchoolRunStatus.INCOMPLETE
        run.status_reason = "stops_not_reached"
    else:
        run.status = SchoolRunStatus.COMPLETED_UNVERIFIED
        run.status_reason = "no_gps_evidence"


def on_session_closed(db: Session, session: OperationSession) -> SchoolRun | None:
    """Evaluate a run when its session ends, and again when late GPS arrives (no commit)."""
    run = db.scalar(select(SchoolRun).where(SchoolRun.session_id == session.id))
    re_evaluable = run is not None and (
        run.status is SchoolRunStatus.IN_PROGRESS
        or (run.status in AUTO_OUTCOMES and not (run.status_reason or "").startswith("manual:"))
    )
    if run is None or not re_evaluable:
        return run
    if session.status is SessionStatus.CANCELLED:
        run.session_id = None
        run.actual_start_at = None
        run.actual_end_at = None
        run.verification = None
        run.status = SchoolRunStatus.SCHEDULED
        run.status_reason = None
        return run
    evaluate(db, run, session)
    return run


def correct_status(
    db: Session, *, actor: User, run_id: uuid.UUID, status: SchoolRunStatus, reason: str
) -> SchoolRun:
    run = get_run(db, run_id)
    if status is SchoolRunStatus.IN_PROGRESS:
        raise ValidationFailed("لا يمكن ضبط الحالة يدويًا إلى جارية", code="invalid_status")
    before = audit.snapshot(run, RUN_AUDITED)
    run.status = status
    run.status_reason = f"manual: {reason}"
    audit.record(
        db,
        action="school_run.status_corrected",
        actor=actor,
        entity_type="school_run",
        entity_id=run.id,
        changes=audit.diff(before, audit.snapshot(run, RUN_AUDITED)),
        reason=reason,
    )
    db.commit()
    return run


def update_run(
    db: Session,
    *,
    actor: User,
    run_id: uuid.UUID,
    vehicle_id: uuid.UUID | None,
    driver_id: uuid.UUID | None,
    notes: str | None,
    fields_set: set[str],
) -> SchoolRun:
    run = get_run(db, run_id)
    reassigning = bool({"vehicle_id", "driver_id"} & fields_set)
    if reassigning and run.status not in OPEN_STATUSES[:1]:
        raise ConflictError("لا يمكن تغيير المركبة أو السائق بعد بدء الدورة", code="run_started")
    before = audit.snapshot(run, RUN_AUDITED)
    if "vehicle_id" in fields_set and vehicle_id is not None:
        _check_assignees(db, vehicle_id, None)
        run.vehicle_id = vehicle_id
    if "driver_id" in fields_set:
        run.driver_id = driver_id
    if "notes" in fields_set:
        run.notes = notes
    changes = audit.diff(before, audit.snapshot(run, RUN_AUDITED))
    if changes:
        audit.record(
            db,
            action="school_run.updated",
            actor=actor,
            entity_type="school_run",
            entity_id=run.id,
            changes=changes,
        )
        db.commit()
    return run


def runs_for_vehicle_day(db: Session, vehicle_id: uuid.UUID, day: date) -> list[SchoolRun]:
    return list(
        db.scalars(
            select(SchoolRun)
            .where(SchoolRun.vehicle_id == vehicle_id, SchoolRun.service_date == day)
            .order_by(SchoolRun.scheduled_start_at)
        ).all()
    )
