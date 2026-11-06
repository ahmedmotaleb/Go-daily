"""Vehicle and vehicle type schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, StringConstraints, field_validator

from app.core.text import collapse_spaces, to_latin_digits
from app.models.assignment import AssignmentRole
from app.models.fleet import OwnershipStatus
from app.schemas.common import ORMModel
from app.services.expiry import ExpiryStatus

TypeCode = Annotated[
    str,
    BeforeValidator(lambda v: v.strip().upper() if isinstance(v, str) else v),
    StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{1,39}$"),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Odometer = Annotated[int, Field(ge=0, le=5_000_000)]
ModelYear = Annotated[int, Field(ge=1950, le=2100)]


class VehicleTypeOut(ORMModel):
    id: uuid.UUID
    code: str
    name_ar: str
    name_en: str | None
    is_active: bool
    sort_order: int


class VehicleTypeCreate(BaseModel):
    code: TypeCode
    name_ar: Name
    name_en: Name | None = None
    sort_order: int = Field(default=50, ge=0, le=1000)


class VehicleTypeUpdate(BaseModel):
    name_ar: Name | None = None
    name_en: Name | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=1000)


def _clean_code(value: object) -> object:
    if isinstance(value, str):
        return to_latin_digits(collapse_spaces(value)).upper()
    return value


def _clean_plate(value: object) -> object:
    if isinstance(value, str):
        return collapse_spaces(value)
    return value


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class _VehicleFields(BaseModel):
    @field_validator("internal_code", mode="before", check_fields=False)
    @classmethod
    def _code(cls, v: object) -> object:
        return _clean_code(v)

    @field_validator("plate_number", mode="before", check_fields=False)
    @classmethod
    def _plate(cls, v: object) -> object:
        return _clean_plate(v)

    @field_validator("manufacturer", "model", "color", "notes", mode="before", check_fields=False)
    @classmethod
    def _blank(cls, v: object) -> object:
        return _blank_to_none(v)


class VehicleCreate(_VehicleFields):
    internal_code: Code
    plate_number: Code
    vehicle_type_id: uuid.UUID
    manufacturer: Short | None = None
    model: Short | None = None
    model_year: ModelYear | None = None
    color: Short | None = None
    ownership_status: OwnershipStatus = OwnershipStatus.OWNED
    current_odometer_km: Odometer | None = None
    license_expiry: date | None = None
    insurance_expiry: date | None = None
    notes: Notes | None = None


class VehicleUpdate(_VehicleFields):
    internal_code: Code | None = None
    plate_number: Code | None = None
    vehicle_type_id: uuid.UUID | None = None
    manufacturer: Short | None = None
    model: Short | None = None
    model_year: ModelYear | None = None
    color: Short | None = None
    ownership_status: OwnershipStatus | None = None
    current_odometer_km: Odometer | None = None
    license_expiry: date | None = None
    insurance_expiry: date | None = None
    notes: Notes | None = None
    # Required when lowering the odometer (a correction, not normal use).
    odometer_correction_reason: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
        | None
    ) = None


class StatusChange(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class AssignmentSummary(BaseModel):
    id: uuid.UUID
    driver_id: uuid.UUID
    driver_name: str
    vehicle_id: uuid.UUID
    vehicle_code: str
    vehicle_plate: str
    role: AssignmentRole
    starts_at: datetime


class VehicleOut(ORMModel):
    id: uuid.UUID
    internal_code: str
    plate_number: str
    vehicle_type: VehicleTypeOut
    manufacturer: str | None
    model: str | None
    model_year: int | None
    color: str | None
    ownership_status: OwnershipStatus
    is_active: bool
    current_odometer_km: int | None
    license_expiry: date | None
    insurance_expiry: date | None
    license_status: ExpiryStatus
    insurance_status: ExpiryStatus
    notes: str | None
    current_assignments: list[AssignmentSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
