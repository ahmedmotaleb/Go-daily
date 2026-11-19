"""Operation type and route schemas."""

from __future__ import annotations

import uuid
from datetime import datetime, time
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, BeforeValidator, Field, StringConstraints, model_validator

from app.models.operations import OperationKind, StopKind, TripPattern
from app.schemas.common import ORMModel

TypeCode = Annotated[
    str,
    BeforeValidator(lambda v: v.strip().upper() if isinstance(v, str) else v),
    StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{1,39}$"),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Latitude = Annotated[Decimal, Field(ge=-90, le=90, max_digits=9, decimal_places=6)]
Longitude = Annotated[Decimal, Field(ge=-180, le=180, max_digits=9, decimal_places=6)]


class OperationTypeOut(ORMModel):
    id: uuid.UUID
    code: str
    kind: OperationKind
    name_ar: str
    name_en: str | None
    is_active: bool
    sort_order: int
    uses_routes: bool


class OperationTypeCreate(BaseModel):
    code: TypeCode
    kind: OperationKind
    name_ar: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    name_en: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    sort_order: int = Field(default=50, ge=0, le=1000)


class OperationTypeUpdate(BaseModel):
    name_ar: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None
    ) = None
    name_en: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=1000)


class StopIn(BaseModel):
    name: Name
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    radius_m: int = Field(default=150, ge=20, le=5000)

    @model_validator(mode="after")
    def _paired(self) -> Self:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("يجب إدخال خط العرض وخط الطول معًا")
        return self


class StopOut(ORMModel):
    id: uuid.UUID
    sequence: int
    kind: StopKind
    name: str
    latitude: Decimal | None
    longitude: Decimal | None
    radius_m: int


Weekday = Annotated[int, Field(ge=1, le=7)]


class _RouteFields(BaseModel):
    @model_validator(mode="after")
    def _window(self) -> Self:
        start = getattr(self, "window_start", None)
        end = getattr(self, "window_end", None)
        if (start is None) != (end is None):
            raise ValueError("حدد بداية ونهاية فترة التشغيل معًا")
        return self


class RouteCreate(_RouteFields):
    name: Name
    operation_type_id: uuid.UUID
    trip_pattern: TripPattern = TripPattern.ROUND_TRIP
    origin: StopIn
    destination: StopIn
    intermediate_stops: list[StopIn] = Field(default_factory=list, max_length=30)
    expected_distance_km: Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=2)] | None = (
        None
    )
    expected_duration_minutes: Annotated[int, Field(gt=0, le=24 * 60)] | None = None
    window_start: time | None = None
    window_end: time | None = None
    operating_days: list[Weekday] | None = None
    notes: Notes | None = None


class RouteUpdate(_RouteFields):
    name: Name | None = None
    trip_pattern: TripPattern | None = None
    origin: StopIn | None = None
    destination: StopIn | None = None
    intermediate_stops: list[StopIn] | None = Field(default=None, max_length=30)
    expected_distance_km: Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=2)] | None = (
        None
    )
    expected_duration_minutes: Annotated[int, Field(gt=0, le=24 * 60)] | None = None
    window_start: time | None = None
    window_end: time | None = None
    operating_days: list[Weekday] | None = None
    notes: Notes | None = None


class RouteOut(ORMModel):
    id: uuid.UUID
    name: str
    operation_type: OperationTypeOut
    trip_pattern: TripPattern
    is_active: bool
    expected_distance_km: Decimal | None
    expected_duration_minutes: int | None
    window_start: time | None
    window_end: time | None
    operating_days: list[int] | None
    notes: str | None
    stops: list[StopOut]
    created_at: datetime
    updated_at: datetime
