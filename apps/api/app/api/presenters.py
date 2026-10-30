"""Convert ORM objects into response schemas (computed fields live here)."""

from __future__ import annotations

from app.core.time import utcnow
from app.models.assignment import DriverVehicleAssignment
from app.models.driver import Driver
from app.models.fleet import Vehicle
from app.models.operations import OperationType, RouteDefinition
from app.models.shift import OperationSession, SessionStatus, Shift, ShiftStatus
from app.schemas.assignment import AssignmentOut
from app.schemas.driver import DriverOut
from app.schemas.fleet import AssignmentSummary, VehicleOut, VehicleTypeOut
from app.schemas.shift import (
    OperationTypeRef,
    PersonRef,
    RouteRef,
    SessionOut,
    ShiftOut,
    VehicleRef,
)
from app.services.drivers import masked_national_id
from app.services.expiry import expiry_status


def assignment_summary(a: DriverVehicleAssignment) -> AssignmentSummary:
    return AssignmentSummary(
        id=a.id,
        driver_id=a.driver_id,
        driver_name=a.driver.full_name,
        vehicle_id=a.vehicle_id,
        vehicle_code=a.vehicle.internal_code,
        vehicle_plate=a.vehicle.plate_number,
        role=a.role,
        starts_at=a.starts_at,
    )


def assignment_out(a: DriverVehicleAssignment) -> AssignmentOut:
    return AssignmentOut(
        id=a.id,
        driver_id=a.driver_id,
        driver_name=a.driver.full_name,
        vehicle_id=a.vehicle_id,
        vehicle_code=a.vehicle.internal_code,
        vehicle_plate=a.vehicle.plate_number,
        role=a.role,
        starts_at=a.starts_at,
        ends_at=a.ends_at,
        is_active=a.is_active_at(utcnow()),
        notes=a.notes,
        created_at=a.created_at,
    )


def vehicle_out(v: Vehicle, current: list[DriverVehicleAssignment] | None = None) -> VehicleOut:
    return VehicleOut(
        id=v.id,
        internal_code=v.internal_code,
        plate_number=v.plate_number,
        vehicle_type=VehicleTypeOut.model_validate(v.vehicle_type),
        manufacturer=v.manufacturer,
        model=v.model,
        model_year=v.model_year,
        color=v.color,
        ownership_status=v.ownership_status,
        is_active=v.is_active,
        current_odometer_km=v.current_odometer_km,
        license_expiry=v.license_expiry,
        insurance_expiry=v.insurance_expiry,
        license_status=expiry_status(v.license_expiry),
        insurance_status=expiry_status(v.insurance_expiry),
        notes=v.notes,
        current_assignments=[assignment_summary(a) for a in current or []],
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def driver_out(d: Driver, current: list[DriverVehicleAssignment] | None = None) -> DriverOut:
    return DriverOut(
        id=d.id,
        full_name=d.full_name,
        phone=d.phone,
        national_id_masked=masked_national_id(d),
        license_number=d.license_number,
        license_expiry=d.license_expiry,
        license_status=expiry_status(d.license_expiry),
        employment_status=d.employment_status,
        hire_date=d.hire_date,
        end_date=d.end_date,
        notes=d.notes,
        user_id=d.user_id,
        app_account_active=d.user.is_active if d.user is not None else None,
        current_assignments=[assignment_summary(a) for a in current or []],
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _op_ref(ot: OperationType | None) -> OperationTypeRef | None:
    if ot is None:
        return None
    return OperationTypeRef(id=ot.id, code=ot.code, kind=ot.kind, name_ar=ot.name_ar)


def _route_ref(route: RouteDefinition | None) -> RouteRef | None:
    return RouteRef(id=route.id, name=route.name) if route else None


def session_out(s: OperationSession) -> SessionOut:
    op = _op_ref(s.operation_type)
    assert op is not None  # noqa: S101
    return SessionOut(
        id=s.id,
        shift_id=s.shift_id,
        operation_type=op,
        route=_route_ref(s.route),
        status=s.status,
        started_at=s.started_at,
        ended_at=s.ended_at,
        start_odometer_km=s.start_odometer_km,
        end_odometer_km=s.end_odometer_km,
        notes=s.notes,
    )


def shift_out(s: Shift) -> ShiftOut:
    sessions = [session_out(x) for x in s.sessions]
    end = s.ended_at or (utcnow() if s.status is ShiftStatus.ACTIVE else None)
    duration = (
        int((end - s.started_at).total_seconds() // 60)
        if s.started_at and end is not None
        else None
    )
    return ShiftOut(
        id=s.id,
        driver=PersonRef(id=s.driver.id, full_name=s.driver.full_name),
        vehicle=VehicleRef(
            id=s.vehicle.id,
            internal_code=s.vehicle.internal_code,
            plate_number=s.vehicle.plate_number,
        ),
        status=s.status,
        source=s.source,
        planned_start_at=s.planned_start_at,
        planned_end_at=s.planned_end_at,
        planned_operation_type=_op_ref(s.planned_operation_type),
        planned_route=_route_ref(s.planned_route),
        started_at=s.started_at,
        ended_at=s.ended_at,
        start_odometer_km=s.start_odometer_km,
        end_odometer_km=s.end_odometer_km,
        odometer_distance_km=s.odometer_distance_km,
        duration_minutes=duration,
        assignment_override_reason=s.assignment_override_reason,
        cancel_reason=s.cancel_reason,
        notes=s.notes,
        sessions=sessions,
        active_session=next((x for x in sessions if x.status is SessionStatus.ACTIVE), None),
        created_at=s.created_at,
        updated_at=s.updated_at,
    )
