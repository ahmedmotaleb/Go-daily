"""Scheduled school duties and their completion evidence."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
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
from app.models.user import User
from app.schemas.common import PageParams
from app.services import audit
from app.services.common import paginate

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


def on_session_closed(db: Session, session: OperationSession) -> SchoolRun | None:
    """Decide completion from GPS evidence when a linked session ends (no commit)."""
    run = db.scalar(select(SchoolRun).where(SchoolRun.session_id == session.id))
    re_evaluable = run is not None and (
        run.status is SchoolRunStatus.IN_PROGRESS
        or (
            run.status is SchoolRunStatus.COMPLETED_UNVERIFIED
            and run.status_reason == "no_gps_evidence"
        )
    )
    if run is None or not re_evaluable:
        return run
    if session.status is SessionStatus.CANCELLED:
        run.session_id = None
        run.actual_start_at = None
        run.status = SchoolRunStatus.SCHEDULED
        return run
    reached = db.scalar(
        select(RouteEvent.id).where(
            RouteEvent.session_id == session.id,
            RouteEvent.status == EventStatus.ACTIVE,
            RouteEvent.event_type == RouteEventType.REACHED_DESTINATION,
        )
    )
    run.actual_end_at = session.ended_at
    if reached is not None:
        run.status = SchoolRunStatus.COMPLETED
        run.status_reason = "gps_destination_reached"
    else:
        run.status = SchoolRunStatus.COMPLETED_UNVERIFIED
        run.status_reason = "no_gps_evidence"
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
