"""Convert ORM objects into response schemas (computed fields live here)."""

from __future__ import annotations

from app.core.time import utcnow
from app.models.assignment import DriverVehicleAssignment
from app.models.driver import Driver
from app.models.fleet import Vehicle
from app.schemas.assignment import AssignmentOut
from app.schemas.driver import DriverOut
from app.schemas.fleet import AssignmentSummary, VehicleOut, VehicleTypeOut
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
