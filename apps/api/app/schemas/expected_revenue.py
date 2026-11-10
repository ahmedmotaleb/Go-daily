"""Expected revenue per fixed-route loop/leg (U10)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.finance import ExpectedRevenueModel
from app.schemas.finance import Money


class RateCreate(BaseModel):
    model: ExpectedRevenueModel
    amount_per_loop: Money | None = None
    amount_per_leg: Money | None = None
    fare: Money | None = None
    # A planning assumption (average passengers per leg), never measured from GPS.
    passengers_per_leg: int | None = Field(default=None, ge=1, le=100)
    effective_from: date
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _amount_for_model(self) -> RateCreate:
        needed = {
            ExpectedRevenueModel.PER_LOOP: ("amount_per_loop",),
            ExpectedRevenueModel.PER_LEG: ("amount_per_leg",),
            ExpectedRevenueModel.PASSENGERS_X_FARE: ("fare", "passengers_per_leg"),
        }[self.model]
        missing = [name for name in needed if getattr(self, name) is None]
        if missing:
            raise ValueError("أدخل قيمة " + " و".join(_FIELD_AR[m] for m in missing))
        return self


_FIELD_AR = {
    "amount_per_loop": "السعر لكل دورة",
    "amount_per_leg": "السعر لكل اتجاه",
    "fare": "الأجرة",
    "passengers_per_leg": "عدد الركاب المتوقع لكل اتجاه",
}


class RateOut(BaseModel):
    id: uuid.UUID
    route_id: uuid.UUID
    model: ExpectedRevenueModel
    amount_per_loop: Decimal | None
    amount_per_leg: Decimal | None
    fare: Decimal | None
    passengers_per_leg: int | None
    effective_from: date
    effective_to: date | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
