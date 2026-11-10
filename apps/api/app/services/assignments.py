"""Driver <-> vehicle assignment history use cases.

Rules:
- Assignments are never deleted; ending one sets `ends_at`.
- PRIMARY assignments may not overlap per vehicle or per driver (service
  check for a clear message + database exclusion constraint for races).
- RELIEF assignments (backup / second-shift driver) may overlap.
- Only ACTIVE drivers and active vehicles can receive new assignments.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.time import utcnow
from app.models.assignment import AssignmentRole, DriverVehicleAssignment
from app.models.driver import Driver, EmploymentStatus
from app.models.fleet import Vehicle
from app.models.user import User
from app.schemas.assignment import AssignmentCorrection, AssignmentCreate, AssignmentEnd
from app.schemas.common import PageParams
from app.services import audit
from app.services.common import paginate

MAX_FUTURE = timedelta(days=7)
AUDITED = ("driver_id", "vehicle_id", "role", "starts_at", "ends_at", "notes")


def get_assignment(db: Session, assignment_id: uuid.UUID) -> DriverVehicleAssignment:
    a = db.get(DriverVehicleAssignment, assignment_id)
    if a is None:
        raise NotFoundError("التكليف غير موجود")
    return a


def list_assignments(
    db: Session,
    params: PageParams,
    *,
    driver_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    active_only: bool = False,
) -> tuple[list[DriverVehicleAssignment], int]:
    stmt = select(DriverVehicleAssignment)
    if driver_id:
        stmt = stmt.where(DriverVehicleAssignment.driver_id == driver_id)
    if vehicle_id:
        stmt = stmt.where(DriverVehicleAssignment.vehicle_id == vehicle_id)
    if active_only:
        now = utcnow()
        stmt = stmt.where(
            DriverVehicleAssignment.starts_at <= now,
            or_(DriverVehicleAssignment.ends_at.is_(None), DriverVehicleAssignment.ends_at > now),
        )
    stmt = stmt.order_by(DriverVehicleAssignment.starts_at.desc(), DriverVehicleAssignment.id)
    return paginate(db, stmt, params)


def _active_at_clause(at: datetime) -> Any:
    return (DriverVehicleAssignment.starts_at <= at) & (
        DriverVehicleAssignment.ends_at.is_(None) | (DriverVehicleAssignment.ends_at > at)
    )


def current_for_vehicles(
    db: Session, vehicle_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[DriverVehicleAssignment]]:
    ids = list(vehicle_ids)
    out: dict[uuid.UUID, list[DriverVehicleAssignment]] = {i: [] for i in ids}
    if not ids:
        return out
    rows = db.scalars(
        select(DriverVehicleAssignment)
        .where(DriverVehicleAssignment.vehicle_id.in_(ids), _active_at_clause(utcnow()))
        .order_by(DriverVehicleAssignment.role, DriverVehicleAssignment.starts_at)
    ).all()
    for row in rows:
        out[row.vehicle_id].append(row)
    return out


def current_for_drivers(
    db: Session, driver_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[DriverVehicleAssignment]]:
    ids = list(driver_ids)
    out: dict[uuid.UUID, list[DriverVehicleAssignment]] = {i: [] for i in ids}
    if not ids:
        return out
    rows = db.scalars(
        select(DriverVehicleAssignment)
        .where(DriverVehicleAssignment.driver_id.in_(ids), _active_at_clause(utcnow()))
        .order_by(DriverVehicleAssignment.role, DriverVehicleAssignment.starts_at)
    ).all()
    for row in rows:
        out[row.driver_id].append(row)
    return out


def _overlapping_primary(
    db: Session,
    *,
    starts_at: datetime,
    ends_at: datetime | None,
    driver_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    exclude: uuid.UUID | None = None,
) -> list[DriverVehicleAssignment]:
    stmt = select(DriverVehicleAssignment).where(
        DriverVehicleAssignment.role == AssignmentRole.PRIMARY,
        or_(DriverVehicleAssignment.ends_at.is_(None), DriverVehicleAssignment.ends_at > starts_at),
    )
    if ends_at is not None:
        stmt = stmt.where(DriverVehicleAssignment.starts_at < ends_at)
    if driver_id:
        stmt = stmt.where(DriverVehicleAssignment.driver_id == driver_id)
    if vehicle_id:
        stmt = stmt.where(DriverVehicleAssignment.vehicle_id == vehicle_id)
    if exclude:
        stmt = stmt.where(DriverVehicleAssignment.id != exclude)
    return list(db.scalars(stmt.with_for_update(of=DriverVehicleAssignment)).all())


def _validate_window(starts_at: datetime, ends_at: datetime | None) -> None:
    now = utcnow()
    if starts_at > now + MAX_FUTURE:
        raise ValidationFailed("لا يمكن بدء تكليف بعد أكثر من 7 أيام", code="assignment_too_far")
    if ends_at is not None and ends_at <= starts_at:
        raise ValidationFailed("وقت النهاية يجب أن يكون بعد وقت البداية", code="invalid_range")


def _conflict_details(rows: list[DriverVehicleAssignment]) -> dict[str, Any]:
    return {
        "conflicts": [
            {
                "assignment_id": str(r.id),
                "driver_name": r.driver.full_name,
                "vehicle_code": r.vehicle.internal_code,
                "starts_at": r.starts_at.isoformat(),
            }
            for r in rows
        ]
    }


def _end(
    db: Session, a: DriverVehicleAssignment, *, actor: User, ends_at: datetime, note: str
) -> None:
    before = audit.snapshot(a, AUDITED)
    a.ends_at = ends_at
    a.ended_by_id = actor.id
    audit.record(
        db,
        action="assignment.ended",
        actor=actor,
        entity_type="assignment",
        entity_id=a.id,
        changes=audit.diff(before, audit.snapshot(a, AUDITED)),
        reason=note,
    )


def create_assignment(
    db: Session, *, actor: User, data: AssignmentCreate
) -> DriverVehicleAssignment:
    driver = db.scalar(select(Driver).where(Driver.id == data.driver_id).with_for_update(of=Driver))
    if driver is None:
        raise NotFoundError("السائق غير موجود")
    vehicle = db.scalar(
        select(Vehicle).where(Vehicle.id == data.vehicle_id).with_for_update(of=Vehicle)
    )
    if vehicle is None:
        raise NotFoundError("المركبة غير موجودة")
    if driver.employment_status is not EmploymentStatus.ACTIVE:
        raise ValidationFailed("لا يمكن تكليف سائق غير نشط", code="driver_not_active")
    if not vehicle.is_active:
        raise ValidationFailed("لا يمكن التكليف على مركبة موقوفة", code="vehicle_not_active")

    starts_at = data.starts_at or utcnow()
    _validate_window(starts_at, data.ends_at)

    if data.role is AssignmentRole.PRIMARY:
        conflicts = {
            r.id: r
            for r in _overlapping_primary(
                db, starts_at=starts_at, ends_at=data.ends_at, vehicle_id=vehicle.id
            )
            + _overlapping_primary(
                db, starts_at=starts_at, ends_at=data.ends_at, driver_id=driver.id
            )
        }
        if conflicts:
            replaceable = [
                r for r in conflicts.values() if r.ends_at is None and r.starts_at < starts_at
            ]
            if data.replace_current and len(replaceable) == len(conflicts):
                for r in replaceable:
                    _end(db, r, actor=actor, ends_at=starts_at, note="replaced_by_new_assignment")
                db.flush()
            else:
                raise ConflictError(
                    "يوجد تكليف أساسي متداخل لنفس السائق أو المركبة",
                    code="assignment_overlap",
                    details=_conflict_details(list(conflicts.values())),
                )

    assignment = DriverVehicleAssignment(
        driver_id=driver.id,
        vehicle_id=vehicle.id,
        role=data.role,
        starts_at=starts_at,
        ends_at=data.ends_at,
        notes=data.notes,
        created_by_id=actor.id,
    )
    db.add(assignment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "يوجد تكليف أساسي متداخل لنفس السائق أو المركبة", code="assignment_overlap"
        ) from exc
    audit.record(
        db,
        action="assignment.created",
        actor=actor,
        entity_type="assignment",
        entity_id=assignment.id,
        changes=audit.diff({}, audit.snapshot(assignment, AUDITED)),
        details={"driver_id": driver.id, "vehicle_id": vehicle.id},
    )
    db.commit()
    db.refresh(assignment)
    return assignment


def end_assignment(
    db: Session, *, actor: User, assignment_id: uuid.UUID, data: AssignmentEnd
) -> DriverVehicleAssignment:
    a = db.scalar(
        select(DriverVehicleAssignment)
        .where(DriverVehicleAssignment.id == assignment_id)
        .with_for_update(of=DriverVehicleAssignment)
        .execution_options(populate_existing=True)
    )
    if a is None:
        raise NotFoundError("التكليف غير موجود")
    if a.ends_at is not None:
        raise ConflictError("هذا التكليف منتهي بالفعل", code="assignment_already_ended")
    ends_at = data.ends_at or utcnow()
    if ends_at <= a.starts_at:
        raise ValidationFailed("وقت النهاية يجب أن يكون بعد وقت البداية", code="invalid_range")
    if ends_at > utcnow() + MAX_FUTURE:
        raise ValidationFailed("لا يمكن تحديد نهاية بعد أكثر من 7 أيام", code="assignment_too_far")
    if data.notes:
        a.notes = f"{a.notes}\n{data.notes}" if a.notes else data.notes
    _end(db, a, actor=actor, ends_at=ends_at, note=data.notes or "ended")
    db.commit()
    db.refresh(a)
    return a


def correct_assignment(
    db: Session, *, actor: User, assignment_id: uuid.UUID, data: AssignmentCorrection
) -> DriverVehicleAssignment:
    """Fix times or notes. Changing times requires a reason and re-validates overlaps."""
    a = db.scalar(
        select(DriverVehicleAssignment)
        .where(DriverVehicleAssignment.id == assignment_id)
        .with_for_update(of=DriverVehicleAssignment)
        .execution_options(populate_existing=True)
    )
    if a is None:
        raise NotFoundError("التكليف غير موجود")
    fields = data.model_dump(exclude_unset=True)
    reason = fields.pop("reason", None)
    times_changed = ("starts_at" in fields and fields["starts_at"] != a.starts_at) or (
        "ends_at" in fields and fields["ends_at"] != a.ends_at
    )
    if times_changed and not reason:
        raise ValidationFailed("تعديل أوقات التكليف يتطلب ذكر السبب", code="reason_required")
    starts_at = fields.get("starts_at") or a.starts_at
    ends_at = fields.get("ends_at", a.ends_at)
    if times_changed:
        _validate_window(starts_at, ends_at)
        if a.role is AssignmentRole.PRIMARY:
            conflicts = _overlapping_primary(
                db, starts_at=starts_at, ends_at=ends_at, vehicle_id=a.vehicle_id, exclude=a.id
            ) + _overlapping_primary(
                db, starts_at=starts_at, ends_at=ends_at, driver_id=a.driver_id, exclude=a.id
            )
            if conflicts:
                raise ConflictError(
                    "التعديل يسبب تداخلًا مع تكليف أساسي آخر",
                    code="assignment_overlap",
                    details=_conflict_details(conflicts),
                )
    before = audit.snapshot(a, AUDITED)
    a.starts_at = starts_at
    a.ends_at = ends_at
    if "notes" in fields:
        a.notes = fields["notes"]
    changes = audit.diff(before, audit.snapshot(a, AUDITED))
    if not changes:
        return a
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("التعديل يسبب تداخلًا مع تكليف آخر", code="assignment_overlap") from exc
    audit.record(
        db,
        action="assignment.corrected",
        actor=actor,
        entity_type="assignment",
        entity_id=a.id,
        changes=changes,
        reason=reason,
    )
    db.commit()
    db.refresh(a)
    return a


def end_open_assignments_for_driver(
    db: Session, *, actor: User, driver_id: uuid.UUID, note: str
) -> int:
    """Used when a driver leaves: closes open assignments now (caller commits)."""
    now = utcnow()
    rows = db.scalars(
        select(DriverVehicleAssignment)
        .where(DriverVehicleAssignment.driver_id == driver_id, _active_at_clause(now))
        .with_for_update(of=DriverVehicleAssignment)
    ).all()
    for row in rows:
        _end(db, row, actor=actor, ends_at=now, note=note)
    return len(rows)
