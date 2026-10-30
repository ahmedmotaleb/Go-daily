"""Shift and operation session schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

from app.models.operations import OperationKind
from app.models.shift import SessionStatus, ShiftSource, ShiftStatus

Odometer = Annotated[int, Field(ge=0, le=5_000_000)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class ShiftCreate(BaseModel):
    driver_id: uuid.UUID
    vehicle_id: uuid.UUID
    planned_start_at: AwareDatetime | None = None
    planned_end_at: AwareDatetime | None = None
    planned_operation_type_id: uuid.UUID | None = None
    planned_route_id: uuid.UUID | None = None
    notes: Notes | None = None
    # Start immediately instead of only planning.
    start_now: bool = False
    start_odometer_km: Odometer | None = None
    started_at: AwareDatetime | None = None
    assignment_override_reason: Reason | None = None


class ShiftUpdate(BaseModel):
    planned_start_at: AwareDatetime | None = None
    planned_end_at: AwareDatetime | None = None
    planned_operation_type_id: uuid.UUID | None = None
    planned_route_id: uuid.UUID | None = None
    notes: Notes | None = None


class ShiftStart(BaseModel):
    start_odometer_km: Odometer
    started_at: AwareDatetime | None = None
    assignment_override_reason: Reason | None = None
    # Initial operation; defaults to the planned one when present.
    operation_type_id: uuid.UUID | None = None
    route_id: uuid.UUID | None = None


class ShiftEnd(BaseModel):
    end_odometer_km: Odometer
    ended_at: AwareDatetime | None = None
    notes: Notes | None = None


class ShiftCancel(BaseModel):
    reason: Reason


class OdometerCorrection(BaseModel):
    start_odometer_km: Odometer | None = None
    end_odometer_km: Odometer | None = None
    reason: Reason


class SessionStart(BaseModel):
    operation_type_id: uuid.UUID
    route_id: uuid.UUID | None = None
    started_at: AwareDatetime | None = None
    start_odometer_km: Odometer | None = None
    notes: Notes | None = None


class SessionEnd(BaseModel):
    ended_at: AwareDatetime | None = None
    end_odometer_km: Odometer | None = None
    notes: Notes | None = None


class SessionCancel(BaseModel):
    reason: Reason


class PersonRef(BaseModel):
    id: uuid.UUID
    full_name: str


class VehicleRef(BaseModel):
    id: uuid.UUID
    internal_code: str
    plate_number: str


class OperationTypeRef(BaseModel):
    id: uuid.UUID
    code: str
    kind: OperationKind
    name_ar: str


class RouteRef(BaseModel):
    id: uuid.UUID
    name: str


class SessionOut(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    operation_type: OperationTypeRef
    route: RouteRef | None
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None
    start_odometer_km: int | None
    end_odometer_km: int | None
    notes: str | None


class ShiftOut(BaseModel):
    id: uuid.UUID
    driver: PersonRef
    vehicle: VehicleRef
    status: ShiftStatus
    source: ShiftSource
    planned_start_at: datetime | None
    planned_end_at: datetime | None
    planned_operation_type: OperationTypeRef | None
    planned_route: RouteRef | None
    started_at: datetime | None
    ended_at: datetime | None
    start_odometer_km: int | None
    end_odometer_km: int | None
    odometer_distance_km: int | None
    duration_minutes: int | None
    assignment_override_reason: str | None
    cancel_reason: str | None
    notes: str | None
    sessions: list[SessionOut]
    active_session: SessionOut | None
    created_at: datetime
    updated_at: datetime
