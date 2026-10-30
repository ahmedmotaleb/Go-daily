"""Shift lifecycle and operation sessions.

Lifecycle: PLANNED -> ACTIVE -> COMPLETED, or CANCELLED (from PLANNED or
ACTIVE, with a reason). Rules enforced here (and by DB constraints):

- one ACTIVE shift per driver and per vehicle (partial unique indexes);
- only ACTIVE drivers and active vehicles; expired driver or vehicle
  licenses block a start (fix the record if it was renewed);
- the driver must hold an assignment on the vehicle at start time, unless
  staff record an explicit override reason (never from the driver app);
- odometer readings never go below the vehicle's last known reading, end
  >= start, and a single shift cannot cover an implausible distance;
- operation sessions only run inside an ACTIVE shift, one at a time.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDenied, ValidationFailed
from app.core.time import local_day_bounds_utc, utcnow
from app.models.assignment import DriverVehicleAssignment
from app.models.driver import Driver, EmploymentStatus
from app.models.fleet import Vehicle
from app.models.operations import OperationType
from app.models.shift import OperationSession, SessionStatus, Shift, ShiftSource, ShiftStatus
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.shift import (
    OdometerCorrection,
    SessionEnd,
    SessionStart,
    ShiftCreate,
    ShiftEnd,
    ShiftStart,
    ShiftUpdate,
)
from app.services import audit, route_events, school_runs
from app.services.common import paginate
from app.services.expiry import ExpiryStatus, expiry_status
from app.services.operations import get_operation_type, validate_route_for_type

MAX_SHIFT_DISTANCE_KM = 1500
MAX_BACKFILL = timedelta(days=7)
CLOCK_SKEW = timedelta(minutes=5)
SHIFT_AUDITED = (
    "status",
    "driver_id",
    "vehicle_id",
    "planned_start_at",
    "planned_end_at",
    "planned_operation_type_id",
    "planned_route_id",
    "started_at",
    "ended_at",
    "start_odometer_km",
    "end_odometer_km",
    "assignment_override_reason",
    "cancel_reason",
    "notes",
)


# ------------------------------------------------------------------ queries


def get_shift(db: Session, shift_id: uuid.UUID, *, for_update: bool = False) -> Shift:
    stmt = select(Shift).where(Shift.id == shift_id)
    if for_update:
        stmt = stmt.with_for_update(of=Shift).execution_options(populate_existing=True)
    shift = db.scalar(stmt)
    if shift is None:
        raise NotFoundError("الوردية غير موجودة")
    return shift


def day_filter(day: date) -> Any:
    """Shifts that touch a local calendar day (planned, started or still running)."""
    start, end = local_day_bounds_utc(day)
    return or_(
        and_(Shift.started_at >= start, Shift.started_at < end),
        and_(
            Shift.started_at.is_(None),
            Shift.planned_start_at >= start,
            Shift.planned_start_at < end,
        ),
        and_(Shift.status == ShiftStatus.ACTIVE, Shift.started_at < end),
        and_(Shift.ended_at >= start, Shift.started_at < end),
    )


def list_shifts(
    db: Session,
    params: PageParams,
    *,
    status: ShiftStatus | None = None,
    driver_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    day: date | None = None,
) -> tuple[list[Shift], int]:
    stmt = select(Shift)
    if status:
        stmt = stmt.where(Shift.status == status)
    if driver_id:
        stmt = stmt.where(Shift.driver_id == driver_id)
    if vehicle_id:
        stmt = stmt.where(Shift.vehicle_id == vehicle_id)
    if day:
        stmt = stmt.where(day_filter(day))
    stmt = stmt.order_by(
        (Shift.status == ShiftStatus.ACTIVE).desc(),
        Shift.started_at.desc().nulls_first(),
        Shift.planned_start_at.desc().nulls_last(),
        Shift.id,
    )
    return paginate(db, stmt, params)


def active_shift_for_driver(db: Session, driver_id: uuid.UUID) -> Shift | None:
    return db.scalar(
        select(Shift).where(Shift.driver_id == driver_id, Shift.status == ShiftStatus.ACTIVE)
    )


def active_session(shift: Shift) -> OperationSession | None:
    return next((s for s in shift.sessions if s.status is SessionStatus.ACTIVE), None)


# ------------------------------------------------------------------ helpers


def _lock(db: Session, model: type[Driver] | type[Vehicle], obj_id: uuid.UUID) -> Any:
    obj = db.scalar(
        select(model)
        .where(model.id == obj_id)
        .with_for_update(of=model)
        .execution_options(populate_existing=True)
    )
    if obj is None:
        raise NotFoundError("السائق غير موجود" if model is Driver else "المركبة غير موجودة")
    return obj


def _check_driver_vehicle(driver: Driver, vehicle: Vehicle) -> None:
    if driver.employment_status is not EmploymentStatus.ACTIVE:
        raise ValidationFailed("السائق غير نشط", code="driver_not_active")
    if not vehicle.is_active:
        raise ValidationFailed("المركبة موقوفة", code="vehicle_not_active")


def _check_documents(driver: Driver, vehicle: Vehicle) -> None:
    if expiry_status(driver.license_expiry) is ExpiryStatus.EXPIRED:
        raise ValidationFailed(
            "رخصة قيادة السائق منتهية، حدّث بيانات الرخصة قبل بدء الوردية",
            code="driver_license_expired",
        )
    if expiry_status(vehicle.license_expiry) is ExpiryStatus.EXPIRED:
        raise ValidationFailed(
            "رخصة المركبة منتهية، حدّث بيانات الرخصة قبل بدء الوردية",
            code="vehicle_license_expired",
        )


def _has_assignment(db: Session, driver_id: uuid.UUID, vehicle_id: uuid.UUID, at: datetime) -> bool:
    return (
        db.scalar(
            select(DriverVehicleAssignment.id).where(
                DriverVehicleAssignment.driver_id == driver_id,
                DriverVehicleAssignment.vehicle_id == vehicle_id,
                DriverVehicleAssignment.starts_at <= at,
                or_(
                    DriverVehicleAssignment.ends_at.is_(None),
                    DriverVehicleAssignment.ends_at > at,
                ),
            )
        )
        is not None
    )


def _resolve_time(value: datetime | None, *, source: ShiftSource, label: str) -> datetime:
    now = utcnow()
    if value is None or source is ShiftSource.DRIVER_APP:
        # The driver app always uses server time; it cannot backdate.
        return now
    if value > now + CLOCK_SKEW:
        raise ValidationFailed(f"لا يمكن أن يكون {label} في المستقبل", code="time_in_future")
    if value < now - MAX_BACKFILL:
        raise ValidationFailed(f"{label} أقدم من المسموح (7 أيام)", code="time_too_old")
    return value


def _ensure_no_active_conflict(db: Session, *, driver_id: uuid.UUID, vehicle_id: uuid.UUID) -> None:
    if active_shift_for_driver(db, driver_id) is not None:
        raise ConflictError("لدى السائق وردية نشطة بالفعل", code="driver_has_active_shift")
    if db.scalar(
        select(Shift.id).where(Shift.vehicle_id == vehicle_id, Shift.status == ShiftStatus.ACTIVE)
    ):
        raise ConflictError("المركبة في وردية نشطة بالفعل", code="vehicle_has_active_shift")


def _validate_plan(
    db: Session, *, operation_type_id: uuid.UUID | None, route_id: uuid.UUID | None
) -> None:
    if operation_type_id is None:
        if route_id is not None:
            raise ValidationFailed("حدد نوع التشغيل للمسار", code="operation_type_required")
        return
    ot = get_operation_type(db, operation_type_id, active_only=True)
    if route_id is not None:
        validate_route_for_type(db, operation_type=ot, route_id=route_id)


def _record(
    db: Session,
    *,
    actor: User,
    shift: Shift,
    action: str,
    before: dict[str, Any] | None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    audit.record(
        db,
        action=action,
        actor=actor,
        entity_type="shift",
        entity_id=shift.id,
        changes=audit.diff(before or {}, audit.snapshot(shift, SHIFT_AUDITED)),
        reason=reason,
        details=details,
    )


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        message = str(exc.orig)
        if "uq_shifts_active_driver" in message:
            raise ConflictError(
                "لدى السائق وردية نشطة بالفعل", code="driver_has_active_shift"
            ) from exc
        if "uq_shifts_active_vehicle" in message:
            raise ConflictError(
                "المركبة في وردية نشطة بالفعل", code="vehicle_has_active_shift"
            ) from exc
        if "uq_operation_sessions_active_per_shift" in message:
            raise ConflictError(
                "يوجد تشغيل نشط في هذه الوردية", code="session_already_active"
            ) from exc
        raise


# ------------------------------------------------------------------ lifecycle


def create_shift(
    db: Session, *, actor: User, data: ShiftCreate, source: ShiftSource = ShiftSource.ADMIN
) -> Shift:
    driver = _lock(db, Driver, data.driver_id)
    vehicle = _lock(db, Vehicle, data.vehicle_id)
    _check_driver_vehicle(driver, vehicle)
    _validate_plan(
        db, operation_type_id=data.planned_operation_type_id, route_id=data.planned_route_id
    )
    if (
        data.planned_start_at
        and data.planned_end_at
        and data.planned_end_at <= data.planned_start_at
    ):
        raise ValidationFailed(
            "نهاية الوردية المخططة يجب أن تكون بعد بدايتها", code="invalid_range"
        )
    if data.start_now and data.start_odometer_km is None:
        raise ValidationFailed("أدخل قراءة العداد عند البدء", code="start_odometer_required")

    shift = Shift(
        driver_id=driver.id,
        vehicle_id=vehicle.id,
        status=ShiftStatus.PLANNED,
        planned_start_at=data.planned_start_at,
        planned_end_at=data.planned_end_at,
        planned_operation_type_id=data.planned_operation_type_id,
        planned_route_id=data.planned_route_id,
        notes=data.notes,
        source=source,
        created_by_id=actor.id,
    )
    db.add(shift)
    db.flush()
    _record(db, actor=actor, shift=shift, action="shift.planned", before=None)
    if not data.start_now:
        _commit(db)
        return shift

    assert data.start_odometer_km is not None  # noqa: S101 - checked above
    return start_shift(
        db,
        actor=actor,
        shift_id=shift.id,
        data=ShiftStart(
            start_odometer_km=data.start_odometer_km,
            started_at=data.started_at,
            assignment_override_reason=data.assignment_override_reason,
        ),
        source=source,
    )


def start_shift(
    db: Session,
    *,
    actor: User,
    shift_id: uuid.UUID,
    data: ShiftStart,
    source: ShiftSource = ShiftSource.ADMIN,
) -> Shift:
    shift = get_shift(db, shift_id, for_update=True)
    if shift.status is not ShiftStatus.PLANNED:
        raise ConflictError("لا يمكن بدء هذه الوردية في حالتها الحالية", code="invalid_shift_state")
    driver = _lock(db, Driver, shift.driver_id)
    vehicle = _lock(db, Vehicle, shift.vehicle_id)
    _check_driver_vehicle(driver, vehicle)
    _check_documents(driver, vehicle)
    _ensure_no_active_conflict(db, driver_id=driver.id, vehicle_id=vehicle.id)

    started_at = _resolve_time(data.started_at, source=source, label="وقت البدء")
    override = data.assignment_override_reason if source is ShiftSource.ADMIN else None
    if not _has_assignment(db, driver.id, vehicle.id, started_at):
        if source is ShiftSource.DRIVER_APP:
            raise PermissionDenied("أنت غير مكلف بهذه المركبة", code="not_assigned_to_vehicle")
        if not override:
            raise ValidationFailed(
                "السائق غير مكلف بهذه المركبة. سجل تكليفًا أو اذكر سبب الاستثناء",
                code="driver_not_assigned",
            )
    else:
        override = None

    last = vehicle.current_odometer_km
    if last is not None and data.start_odometer_km < last:
        raise ValidationFailed(
            f"قراءة العداد أقل من آخر قراءة مسجلة للمركبة ({last} كم)",
            code="odometer_below_last_reading",
            details={"last_reading_km": last},
        )

    before = audit.snapshot(shift, SHIFT_AUDITED)
    shift.status = ShiftStatus.ACTIVE
    shift.started_at = started_at
    shift.start_odometer_km = data.start_odometer_km
    shift.assignment_override_reason = override
    shift.started_by_id = actor.id
    if source is ShiftSource.DRIVER_APP:
        shift.source = ShiftSource.DRIVER_APP
    vehicle.current_odometer_km = max(last or 0, data.start_odometer_km)
    db.flush()

    op_type_id = data.operation_type_id or shift.planned_operation_type_id
    route_id = (
        data.route_id if data.operation_type_id else (data.route_id or shift.planned_route_id)
    )
    if op_type_id is not None:
        _open_session(
            db,
            actor=actor,
            shift=shift,
            operation_type_id=op_type_id,
            route_id=route_id,
            started_at=started_at,
            start_odometer_km=data.start_odometer_km,
            notes=None,
        )
    details: dict[str, Any] = {"source": source.value}
    if last is not None and data.start_odometer_km - last > 0:
        details["odometer_gap_km"] = data.start_odometer_km - last
    _record(
        db,
        actor=actor,
        shift=shift,
        action="shift.started",
        before=before,
        reason=override,
        details=details,
    )
    _commit(db)
    db.refresh(shift)
    return shift


def end_shift(
    db: Session,
    *,
    actor: User,
    shift_id: uuid.UUID,
    data: ShiftEnd,
    source: ShiftSource = ShiftSource.ADMIN,
) -> Shift:
    shift = get_shift(db, shift_id, for_update=True)
    if shift.status is not ShiftStatus.ACTIVE:
        raise ConflictError("الوردية ليست نشطة", code="invalid_shift_state")
    assert shift.started_at is not None and shift.start_odometer_km is not None  # noqa: S101
    ended_at = _resolve_time(data.ended_at, source=source, label="وقت الانتهاء")
    if ended_at < shift.started_at:
        raise ValidationFailed("وقت الانتهاء قبل وقت البدء", code="invalid_range")
    if data.end_odometer_km < shift.start_odometer_km:
        raise ValidationFailed(
            f"قراءة العداد عند الانتهاء أقل من قراءة البدء ({shift.start_odometer_km} كم)",
            code="end_odometer_below_start",
        )
    if data.end_odometer_km - shift.start_odometer_km > MAX_SHIFT_DISTANCE_KM:
        raise ValidationFailed(
            f"المسافة أكبر من الحد المنطقي لوردية واحدة ({MAX_SHIFT_DISTANCE_KM} كم)، راجع القراءة",
            code="implausible_odometer",
        )

    before = audit.snapshot(shift, SHIFT_AUDITED)
    session = active_session(shift)
    if session is not None:
        _close_session(session, ended_at=ended_at, end_odometer_km=data.end_odometer_km)
        _after_session_closed(db, session)
    shift.status = ShiftStatus.COMPLETED
    shift.ended_at = ended_at
    shift.end_odometer_km = data.end_odometer_km
    shift.ended_by_id = actor.id
    if data.notes:
        shift.notes = f"{shift.notes}\n{data.notes}" if shift.notes else data.notes
    vehicle = _lock(db, Vehicle, shift.vehicle_id)
    vehicle.current_odometer_km = max(vehicle.current_odometer_km or 0, data.end_odometer_km)
    _record(
        db,
        actor=actor,
        shift=shift,
        action="shift.ended",
        before=before,
        details={"source": source.value, "odometer_distance_km": shift.odometer_distance_km},
    )
    _commit(db)
    db.refresh(shift)
    return shift


def cancel_shift(db: Session, *, actor: User, shift_id: uuid.UUID, reason: str) -> Shift:
    shift = get_shift(db, shift_id, for_update=True)
    if shift.status not in (ShiftStatus.PLANNED, ShiftStatus.ACTIVE):
        raise ConflictError("لا يمكن إلغاء هذه الوردية", code="invalid_shift_state")
    before = audit.snapshot(shift, SHIFT_AUDITED)
    now = utcnow()
    for session in shift.sessions:
        if session.status is SessionStatus.ACTIVE:
            session.status = SessionStatus.CANCELLED
            session.ended_at = now
            _after_session_closed(db, session)
    shift.status = ShiftStatus.CANCELLED
    shift.cancel_reason = reason
    if shift.started_at is not None:
        shift.ended_at = now
    _record(db, actor=actor, shift=shift, action="shift.cancelled", before=before, reason=reason)
    _commit(db)
    db.refresh(shift)
    return shift


def update_shift(db: Session, *, actor: User, shift_id: uuid.UUID, data: ShiftUpdate) -> Shift:
    shift = get_shift(db, shift_id, for_update=True)
    fields = data.model_dump(exclude_unset=True)
    plan_fields = {k: v for k, v in fields.items() if k != "notes"}
    if plan_fields and shift.status is not ShiftStatus.PLANNED:
        raise ConflictError("لا يمكن تعديل خطة وردية بدأت بالفعل", code="invalid_shift_state")
    if plan_fields:
        _validate_plan(
            db,
            operation_type_id=plan_fields.get(
                "planned_operation_type_id", shift.planned_operation_type_id
            ),
            route_id=plan_fields.get("planned_route_id", shift.planned_route_id),
        )
    before = audit.snapshot(shift, SHIFT_AUDITED)
    for key, value in fields.items():
        setattr(shift, key, value)
    if (
        shift.planned_start_at
        and shift.planned_end_at
        and shift.planned_end_at <= shift.planned_start_at
    ):
        raise ValidationFailed(
            "نهاية الوردية المخططة يجب أن تكون بعد بدايتها", code="invalid_range"
        )
    if audit.diff(before, audit.snapshot(shift, SHIFT_AUDITED)):
        _record(db, actor=actor, shift=shift, action="shift.updated", before=before)
        _commit(db)
    return shift


def correct_odometer(
    db: Session, *, actor: User, shift_id: uuid.UUID, data: OdometerCorrection
) -> Shift:
    """Audited correction of recorded readings (does not rewrite history silently)."""
    shift = get_shift(db, shift_id, for_update=True)
    if shift.status not in (ShiftStatus.ACTIVE, ShiftStatus.COMPLETED):
        raise ConflictError("لا توجد قراءات لتصحيحها", code="invalid_shift_state")
    start = (
        data.start_odometer_km if data.start_odometer_km is not None else shift.start_odometer_km
    )
    end = data.end_odometer_km if data.end_odometer_km is not None else shift.end_odometer_km
    if data.end_odometer_km is not None and shift.status is not ShiftStatus.COMPLETED:
        raise ValidationFailed(
            "لا يمكن تصحيح قراءة الانتهاء لوردية لم تنتهِ", code="invalid_shift_state"
        )
    if start is not None and end is not None:
        if end < start:
            raise ValidationFailed(
                "قراءة الانتهاء أقل من قراءة البدء", code="end_odometer_below_start"
            )
        if end - start > MAX_SHIFT_DISTANCE_KM:
            raise ValidationFailed("المسافة غير منطقية لوردية واحدة", code="implausible_odometer")
    before = audit.snapshot(shift, SHIFT_AUDITED)
    shift.start_odometer_km = start
    shift.end_odometer_km = end
    if audit.diff(before, audit.snapshot(shift, SHIFT_AUDITED)):
        _record(
            db,
            actor=actor,
            shift=shift,
            action="shift.odometer_corrected",
            before=before,
            reason=data.reason,
        )
        _commit(db)
    return shift


# ------------------------------------------------------------------ sessions


def _close_session(
    session: OperationSession, *, ended_at: datetime, end_odometer_km: int | None
) -> None:
    session.status = SessionStatus.COMPLETED
    session.ended_at = max(ended_at, session.started_at)
    if end_odometer_km is not None and session.start_odometer_km is not None:
        session.end_odometer_km = max(end_odometer_km, session.start_odometer_km)


def _after_session_closed(db: Session, session: OperationSession) -> None:
    """Derive route events and school-run completion for a session that just ended."""
    db.flush()
    if session.route_id is not None:
        route_events.detect_safely(db, [session.id])
    school_runs.on_session_closed(db, session)


def _open_session(
    db: Session,
    *,
    actor: User,
    shift: Shift,
    operation_type_id: uuid.UUID,
    route_id: uuid.UUID | None,
    started_at: datetime,
    start_odometer_km: int | None,
    notes: str | None,
) -> OperationSession:
    op_type: OperationType = get_operation_type(db, operation_type_id, active_only=True)
    route = validate_route_for_type(db, operation_type=op_type, route_id=route_id)
    session = OperationSession(
        shift_id=shift.id,
        operation_type_id=op_type.id,
        route_id=route.id if route else None,
        status=SessionStatus.ACTIVE,
        started_at=started_at,
        start_odometer_km=start_odometer_km,
        notes=notes,
        created_by_id=actor.id,
    )
    db.add(session)
    db.flush()
    db.refresh(shift)
    school_runs.link_session(db, session)
    audit.record(
        db,
        action="operation_session.started",
        actor=actor,
        entity_type="shift",
        entity_id=shift.id,
        details={
            "session_id": session.id,
            "operation_type": op_type.code,
            "route_id": route.id if route else None,
        },
    )
    return session


def start_session(
    db: Session,
    *,
    actor: User,
    shift_id: uuid.UUID,
    data: SessionStart,
    source: ShiftSource = ShiftSource.ADMIN,
) -> OperationSession:
    shift = get_shift(db, shift_id, for_update=True)
    if shift.status is not ShiftStatus.ACTIVE:
        raise ConflictError("ابدأ الوردية أولًا", code="shift_not_active")
    assert shift.started_at is not None  # noqa: S101
    started_at = _resolve_time(data.started_at, source=source, label="وقت بدء التشغيل")
    if started_at < shift.started_at:
        raise ValidationFailed("وقت بدء التشغيل قبل بداية الوردية", code="invalid_range")
    current = active_session(shift)
    if current is not None:
        # Switching operation: the previous one ends when the next begins.
        if started_at < current.started_at:
            raise ValidationFailed("وقت البدء قبل بداية التشغيل الحالي", code="invalid_range")
        _close_session(current, ended_at=started_at, end_odometer_km=data.start_odometer_km)
        _after_session_closed(db, current)
    session = _open_session(
        db,
        actor=actor,
        shift=shift,
        operation_type_id=data.operation_type_id,
        route_id=data.route_id,
        started_at=started_at,
        start_odometer_km=data.start_odometer_km,
        notes=data.notes,
    )
    _commit(db)
    db.refresh(session)
    return session


def _get_session(db: Session, session_id: uuid.UUID) -> OperationSession:
    session = db.scalar(
        select(OperationSession)
        .where(OperationSession.id == session_id)
        .with_for_update(of=OperationSession)
        .execution_options(populate_existing=True)
    )
    if session is None:
        raise NotFoundError("التشغيل غير موجود")
    return session


def end_session(
    db: Session,
    *,
    actor: User,
    session_id: uuid.UUID,
    data: SessionEnd,
    source: ShiftSource = ShiftSource.ADMIN,
) -> OperationSession:
    session = _get_session(db, session_id)
    if session.status is not SessionStatus.ACTIVE:
        raise ConflictError("هذا التشغيل غير نشط", code="session_not_active")
    ended_at = _resolve_time(data.ended_at, source=source, label="وقت انتهاء التشغيل")
    if ended_at < session.started_at:
        raise ValidationFailed("وقت الانتهاء قبل وقت البدء", code="invalid_range")
    if (
        data.end_odometer_km is not None
        and session.start_odometer_km is not None
        and data.end_odometer_km < session.start_odometer_km
    ):
        raise ValidationFailed(
            "قراءة العداد أقل من قراءة بدء التشغيل", code="end_odometer_below_start"
        )
    session.status = SessionStatus.COMPLETED
    session.ended_at = ended_at
    session.end_odometer_km = data.end_odometer_km
    if data.notes:
        session.notes = f"{session.notes}\n{data.notes}" if session.notes else data.notes
    _after_session_closed(db, session)
    audit.record(
        db,
        action="operation_session.ended",
        actor=actor,
        entity_type="shift",
        entity_id=session.shift_id,
        details={"session_id": session.id},
    )
    _commit(db)
    db.refresh(session)
    return session


def cancel_session(
    db: Session, *, actor: User, session_id: uuid.UUID, reason: str
) -> OperationSession:
    session = _get_session(db, session_id)
    if session.status is SessionStatus.CANCELLED:
        raise ConflictError("هذا التشغيل ملغي بالفعل", code="session_already_cancelled")
    session.status = SessionStatus.CANCELLED
    session.ended_at = session.ended_at or utcnow()
    _after_session_closed(db, session)
    audit.record(
        db,
        action="operation_session.cancelled",
        actor=actor,
        entity_type="shift",
        entity_id=session.shift_id,
        details={"session_id": session.id},
        reason=reason,
    )
    _commit(db)
    db.refresh(session)
    return session
