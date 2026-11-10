"""Dashboard aggregates computed from source records."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.api.presenters import assignment_summary, shift_out
from app.core.time import local_today, utcnow
from app.models.assignment import AssignmentRole, DriverVehicleAssignment
from app.models.audit import AuditLog
from app.models.driver import Driver, EmploymentStatus
from app.models.fleet import Vehicle
from app.models.shift import SessionStatus, Shift, ShiftStatus
from app.models.user import User
from app.schemas.dashboard import (
    ActivityItem,
    DashboardSummary,
    ExpiringDocument,
    Kpis,
    VehicleStatusRow,
)
from app.services.expiry import expiry_status, warning_cutoff
from app.services.shifts import day_filter

OPERATIONAL_ENTITIES = ("vehicle", "driver", "assignment", "shift", "route")
LIST_LIMIT = 50


def _count(db: Session, stmt: Select[Any]) -> int:
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def summary(db: Session) -> DashboardSummary:
    now = utcnow()
    today = local_today()

    active_shifts = list(
        db.scalars(
            select(Shift).where(Shift.status == ShiftStatus.ACTIVE).order_by(Shift.started_at)
        ).all()
    )
    shift_by_vehicle = {s.vehicle_id: s for s in active_shifts}

    kpis = Kpis(
        active_vehicles=_count(db, select(Vehicle.id).where(Vehicle.is_active.is_(True))),
        active_drivers=_count(
            db, select(Driver.id).where(Driver.employment_status == EmploymentStatus.ACTIVE)
        ),
        active_shifts=len(active_shifts),
        today_shifts=_count(
            db,
            select(Shift.id).where(Shift.status != ShiftStatus.CANCELLED, day_filter(today)),
        ),
    )

    open_assignments = list(
        db.scalars(
            select(DriverVehicleAssignment)
            .where(
                DriverVehicleAssignment.starts_at <= now,
                or_(
                    DriverVehicleAssignment.ends_at.is_(None),
                    DriverVehicleAssignment.ends_at > now,
                ),
            )
            .order_by(DriverVehicleAssignment.role, DriverVehicleAssignment.starts_at.desc())
            .limit(LIST_LIMIT)
        ).all()
    )
    primary_by_vehicle = {
        a.vehicle_id: a for a in open_assignments if a.role is AssignmentRole.PRIMARY
    }

    vehicles = db.scalars(
        select(Vehicle)
        .where(Vehicle.is_active.is_(True))
        .order_by(Vehicle.internal_code)
        .limit(LIST_LIMIT)
    ).all()
    vehicle_rows = []
    for v in vehicles:
        shift = shift_by_vehicle.get(v.id)
        session = next(
            (x for x in (shift.sessions if shift else []) if x.status is SessionStatus.ACTIVE), None
        )
        assignment = primary_by_vehicle.get(v.id)
        vehicle_rows.append(
            VehicleStatusRow(
                id=v.id,
                internal_code=v.internal_code,
                plate_number=v.plate_number,
                vehicle_type=v.vehicle_type.name_ar,
                driver_name=(
                    shift.driver.full_name
                    if shift
                    else (assignment.driver.full_name if assignment else None)
                ),
                in_shift=shift is not None,
                current_operation=(
                    session.operation_type.name_ar
                    + (f" — {session.route.name}" if session.route else "")
                    if session
                    else None
                ),
            )
        )
    vehicle_rows.sort(key=lambda r: (not r.in_shift, r.internal_code))

    cutoff = warning_cutoff(today)
    docs: list[ExpiringDocument] = []
    for v in db.scalars(
        select(Vehicle).where(
            Vehicle.is_active.is_(True),
            or_(Vehicle.license_expiry <= cutoff, Vehicle.insurance_expiry <= cutoff),
        )
    ).all():
        label = f"{v.internal_code} · {v.plate_number}"
        if v.license_expiry and v.license_expiry <= cutoff:
            docs.append(
                ExpiringDocument(
                    kind="VEHICLE_LICENSE",
                    entity_type="vehicle",
                    entity_id=v.id,
                    label=label,
                    expires_on=v.license_expiry,
                    status=expiry_status(v.license_expiry, today=today),
                )
            )
        if v.insurance_expiry and v.insurance_expiry <= cutoff:
            docs.append(
                ExpiringDocument(
                    kind="VEHICLE_INSURANCE",
                    entity_type="vehicle",
                    entity_id=v.id,
                    label=label,
                    expires_on=v.insurance_expiry,
                    status=expiry_status(v.insurance_expiry, today=today),
                )
            )
    for d in db.scalars(
        select(Driver).where(
            Driver.employment_status == EmploymentStatus.ACTIVE, Driver.license_expiry <= cutoff
        )
    ).all():
        assert d.license_expiry is not None  # noqa: S101
        docs.append(
            ExpiringDocument(
                kind="DRIVER_LICENSE",
                entity_type="driver",
                entity_id=d.id,
                label=d.full_name,
                expires_on=d.license_expiry,
                status=expiry_status(d.license_expiry, today=today),
            )
        )
    docs.sort(key=lambda x: x.expires_on)

    activity_rows = db.execute(
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(AuditLog.entity_type.in_(OPERATIONAL_ENTITIES))
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id)
        .limit(15)
    ).all()
    activity = [
        ActivityItem(
            id=row.id,
            occurred_at=row.occurred_at,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            actor_name=name,
        )
        for row, name in activity_rows
    ]

    return DashboardSummary(
        generated_at=now,
        kpis=kpis,
        active_shifts=[shift_out(s) for s in active_shifts[:LIST_LIMIT]],
        vehicles=vehicle_rows,
        assignments=[assignment_summary(a) for a in open_assignments],
        expiring_documents=docs[:LIST_LIMIT],
        recent_activity=activity,
    )
