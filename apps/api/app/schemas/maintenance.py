"""Maintenance schemas (Task 21)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, model_validator

from app.schemas.common import ORMModel
from app.schemas.finance import (
    Code,
    MoneyOrZero,
    NameAr,
    Notes,
    Qty,
    Reason,
    Ref,
    ReviewOut,
    ShortText,
)

Spec = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class MaintenanceTypeOut(ORMModel):
    id: uuid.UUID
    code: str
    name_ar: str
    interval_km: int | None
    interval_days: int | None
    is_active: bool
    sort_order: int
    consumable_type_id: uuid.UUID | None = None


class MaintenanceTypeCreate(BaseModel):
    code: Code
    name_ar: NameAr
    interval_km: int | None = Field(default=None, gt=0, le=500_000)
    interval_days: int | None = Field(default=None, gt=0, le=3650)
    sort_order: int = Field(default=0, ge=0, le=999)
    consumable_type_id: uuid.UUID | None = None


class MaintenanceTypeUpdate(BaseModel):
    name_ar: NameAr | None = None
    interval_km: int | None = Field(default=None, gt=0, le=500_000)
    interval_days: int | None = Field(default=None, gt=0, le=3650)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=999)
    consumable_type_id: uuid.UUID | None = None


class ScheduleIn(BaseModel):
    type_id: uuid.UUID
    # Null = use the type's default interval.
    interval_km: int | None = Field(default=None, gt=0, le=500_000)
    interval_days: int | None = Field(default=None, gt=0, le=3650)
    baseline_km: int | None = Field(default=None, ge=0, le=5_000_000)
    baseline_date: date | None = None
    is_active: bool = True


DueState = Literal["OK", "DUE_SOON", "OVERDUE", "UNKNOWN"]


class DueItem(BaseModel):
    schedule_id: uuid.UUID
    vehicle: Ref
    type: MaintenanceTypeOut
    interval_km: int | None
    interval_days: int | None
    last_performed_on: date | None
    last_odometer_km: int | None
    current_odometer_km: int | None
    next_due_km: int | None
    next_due_date: date | None
    km_left: int | None
    days_left: int | None
    state: DueState
    is_active: bool


class RecordFields(BaseModel):
    vehicle_id: uuid.UUID
    type_id: uuid.UUID
    performed_on: date
    odometer_km: int | None = Field(default=None, ge=0, le=5_000_000)
    vendor: ShortText | None = None
    parts_cost: MoneyOrZero = Decimal("0")
    labor_cost: MoneyOrZero = Decimal("0")
    other_cost: MoneyOrZero = Decimal("0")
    description: Notes | None = None
    downtime_start: AwareDatetime | None = None
    downtime_end: AwareDatetime | None = None
    fuel_transaction_id: uuid.UUID | None = None
    # The driver's close-out maintenance expense for the same job, if any.
    closeout_expense_id: uuid.UUID | None = None
    consumable_quantity: Qty | None = None
    consumable_spec: Spec | None = None
    # Blank: computed from the vehicle's schedule or the type's interval.
    next_due_km: int | None = Field(default=None, ge=0, le=5_000_000)
    next_due_on: date | None = None
    notes: Notes | None = None

    @model_validator(mode="after")
    def _ranges(self) -> RecordFields:
        if self.downtime_end and not self.downtime_start:
            raise ValueError("حدد بداية التوقف")
        if self.downtime_start and self.downtime_end and self.downtime_end < self.downtime_start:
            raise ValueError("نهاية التوقف قبل بدايته")
        return self


class RecordCreate(RecordFields):
    approve_now: bool = False


class RecordCorrection(RecordFields):
    reason: Reason
    approve_now: bool = False


class RecordOut(ReviewOut):
    id: uuid.UUID
    vehicle: Ref
    type: MaintenanceTypeOut
    performed_on: date
    odometer_km: int | None
    vendor: str | None
    parts_cost: Decimal
    labor_cost: Decimal
    other_cost: Decimal
    total_cost: Decimal
    description: str | None
    downtime_start: datetime | None
    downtime_end: datetime | None
    downtime_hours: float | None
    fuel_transaction_id: uuid.UUID | None
    closeout_expense_id: uuid.UUID | None = None
    consumable_quantity: Decimal | None = None
    consumable_spec: str | None = None
    next_due_km: int | None = None
    next_due_on: date | None = None


# --- Oil and service reconciliation (U17) ----------------------------------------


class OilPurchaseRow(BaseModel):
    id: uuid.UUID
    vehicle: str
    vehicle_id: uuid.UUID
    day: date
    item: str
    quantity: Decimal
    unit: str
    total_amount: Decimal
    used: Decimal | None
    services: list[uuid.UUID]
    status: Literal["NOT_LINKED", "OVER_USED", "PARTLY_USED", "USED"]
    label: str


class OilServiceRow(BaseModel):
    id: uuid.UUID
    vehicle: str
    vehicle_id: uuid.UUID
    day: date
    service: str
    quantity: Decimal | None
    spec: str | None
    purchase_id: uuid.UUID | None
    parts_cost: Decimal
    next_due_km: int | None
    next_due_on: date | None
    status: Literal["NO_QUANTITY", "NO_PURCHASE", "OK"]
    label: str


class OilExpenseRow(BaseModel):
    id: uuid.UUID
    vehicle: str
    vehicle_id: uuid.UUID
    day: date
    amount: Decimal
    service_id: uuid.UUID | None
    status: Literal["NO_SERVICE", "MATCHED"]
    label: str


class OilReconciliationOut(BaseModel):
    date_from: date
    date_to: date
    purchases: list[OilPurchaseRow]
    services: list[OilServiceRow]
    expenses: list[OilExpenseRow]
    to_check: int
