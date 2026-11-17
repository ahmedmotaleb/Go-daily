"""Schemas for fuel stations and vendors (U16)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.models.finance import QuantityUnit, RecordStatus
from app.schemas.finance import FuelTypeOut, Notes, Ref, ShortText

Brand = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Radius = Annotated[int, Field(ge=20, le=5000)]


class FuelStationFields(BaseModel):
    brand: Brand | None = None
    address: Address | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    radius_m: Radius | None = None
    is_trusted: bool | None = None
    fuel_type_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)
    notes: Notes | None = None

    @model_validator(mode="after")
    def _location(self) -> FuelStationFields:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("أدخل خط العرض وخط الطول معًا")
        return self


class FuelStationCreate(FuelStationFields):
    name: ShortText


class FuelStationUpdate(FuelStationFields):
    name: ShortText | None = None
    is_active: bool | None = None


class FuelStationOut(BaseModel):
    id: uuid.UUID
    name: str
    brand: str | None
    address: str | None
    latitude: float | None
    longitude: float | None
    radius_m: int
    is_trusted: bool
    is_active: bool
    notes: str | None
    fuel_types: list[FuelTypeOut]
    transactions_count: int = 0
    last_purchase_at: datetime | None = None


class StationPrice(BaseModel):
    """Approved purchases of one fuel type at the station, with the fleet's price."""

    fuel_type: FuelTypeOut
    unit: QuantityUnit
    count: int
    quantity: Decimal
    total_amount: Decimal
    average_price: Decimal
    min_price: Decimal
    max_price: Decimal
    last_price: Decimal
    fleet_average_price: Decimal | None
    # (station average - fleet average) / fleet average, in percent.
    difference_pct: Decimal | None


class MonthlyPrice(BaseModel):
    month: date
    fuel_type: str
    average_price: Decimal
    count: int


class StationPurchase(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    vehicle: Ref
    driver: Ref | None
    fuel_type: str
    quantity: Decimal
    unit_price: Decimal
    total_amount: Decimal
    status: RecordStatus
    has_receipt: bool


class FuelStationDetail(FuelStationOut):
    prices: list[StationPrice]
    monthly: list[MonthlyPrice]
    recent: list[StationPurchase]
    receipts_count: int
    pending_count: int
