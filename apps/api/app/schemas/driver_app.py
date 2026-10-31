"""Schemas for the driver mobile app (/api/v1/driver)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.operations import OperationTypeOut
from app.schemas.shift import ShiftOut
from app.services.expiry import ExpiryStatus

Odometer = Annotated[int, Field(ge=0, le=5_000_000)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class DriverVehicleOut(BaseModel):
    id: uuid.UUID
    internal_code: str
    plate_number: str
    vehicle_type: str
    assignment_role: str
    last_odometer_km: int | None


class DriverMeOut(BaseModel):
    driver_id: uuid.UUID
    full_name: str
    phone: str
    license_expiry: date | None
    license_status: ExpiryStatus
    vehicles: list[DriverVehicleOut]
    active_shift: ShiftOut | None


class DriverShiftStart(BaseModel):
    vehicle_id: uuid.UUID
    start_odometer_km: Odometer
    # Start a shift that operations planned for this driver, if any.
    planned_shift_id: uuid.UUID | None = None
    operation_type_id: uuid.UUID | None = None
    route_id: uuid.UUID | None = None


class DriverShiftEnd(BaseModel):
    end_odometer_km: Odometer
    notes: Notes | None = None


class DriverSessionStart(BaseModel):
    operation_type_id: uuid.UUID
    route_id: uuid.UUID | None = None


class DriverRouteOut(BaseModel):
    id: uuid.UUID
    name: str
    operation_type_id: uuid.UUID


class DriverFuelTypeOut(BaseModel):
    id: uuid.UUID
    code: str
    name_ar: str
    default_unit: str


class DriverCatalogOut(BaseModel):
    operation_types: list[OperationTypeOut]
    routes: list[DriverRouteOut]
    fuel_types: list[DriverFuelTypeOut] = []


class DriverFuelOut(BaseModel):
    id: uuid.UUID
    fuel_type: str
    quantity: Decimal
    unit: str
    total_amount: Decimal
    occurred_at: datetime
    status: str
    paid_by: str
