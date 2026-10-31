"""Schemas for financial records (Tasks 14-19).

Money crosses the API as decimal strings (Pydantic serialises Decimal as a
string); inputs accept strings or numbers and are validated as fixed-point.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, model_validator

from app.models.finance import (
    ExpenseGroup,
    FuelCategory,
    LedgerEntryType,
    LedgerSource,
    PaidBy,
    PaymentMethod,
    QuantityUnit,
    ReceivedBy,
    RecordSource,
    RecordStatus,
    RevenueKind,
    SettlementStatus,
)
from app.schemas.common import ORMModel

Money = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
MoneyOrZero = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
SignedMoney = Annotated[Decimal, Field(max_digits=14, decimal_places=2)]
Qty = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
UnitPrice = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
Odometer = Annotated[int, Field(ge=0, le=5_000_000)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z][A-Z0-9_]{1,39}$")]
NameAr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class Ref(BaseModel):
    id: uuid.UUID
    name: str


class UserRef(BaseModel):
    id: uuid.UUID
    full_name: str


class ReviewOut(BaseModel):
    """Lifecycle fields shared by all reviewable records."""

    status: RecordStatus
    source: RecordSource
    notes: str | None
    created_by: UserRef | None
    created_at: datetime
    updated_at: datetime
    reviewed_by: UserRef | None
    reviewed_at: datetime | None
    review_note: str | None
    voided_by: UserRef | None
    voided_at: datetime | None
    void_reason: str | None
    corrects_id: uuid.UUID | None
    corrected_by_id: uuid.UUID | None = None


class ReviewAction(BaseModel):
    note: Notes | None = None


class RejectAction(BaseModel):
    reason: Reason


class VoidAction(BaseModel):
    reason: Reason


# --- Fuel -------------------------------------------------------------------------


class FuelTypeOut(ORMModel):
    id: uuid.UUID
    code: str
    name_ar: str
    category: FuelCategory
    default_unit: QuantityUnit
    is_active: bool
    sort_order: int


class FuelTypeCreate(BaseModel):
    code: Code
    name_ar: NameAr
    category: FuelCategory
    default_unit: QuantityUnit
    sort_order: int = Field(default=0, ge=0, le=999)


class FuelTypeUpdate(BaseModel):
    name_ar: NameAr | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=999)


class FuelFields(BaseModel):
    fuel_type_id: uuid.UUID
    quantity: Qty
    unit: QuantityUnit | None = None
    unit_price: UnitPrice | None = None
    total_amount: Money | None = None
    occurred_at: AwareDatetime
    odometer_km: Odometer | None = None
    vendor: ShortText | None = None
    payment_method: PaymentMethod = PaymentMethod.CASH
    paid_by: PaidBy = PaidBy.COMPANY
    notes: Notes | None = None

    @model_validator(mode="after")
    def _amounts(self) -> FuelFields:
        if self.total_amount is None and self.unit_price is None:
            raise ValueError("أدخل الإجمالي أو سعر الوحدة")
        return self


class FuelCreate(FuelFields):
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID | None = None
    shift_id: uuid.UUID | None = None
    approve_now: bool = False


class FuelCorrection(FuelCreate):
    reason: Reason


class FuelUpdate(BaseModel):
    fuel_type_id: uuid.UUID | None = None
    quantity: Qty | None = None
    unit: QuantityUnit | None = None
    unit_price: UnitPrice | None = None
    total_amount: Money | None = None
    occurred_at: AwareDatetime | None = None
    odometer_km: Odometer | None = None
    vendor: ShortText | None = None
    payment_method: PaymentMethod | None = None
    paid_by: PaidBy | None = None
    driver_id: uuid.UUID | None = None
    shift_id: uuid.UUID | None = None
    notes: Notes | None = None


class FuelOut(ReviewOut):
    id: uuid.UUID
    vehicle: Ref
    driver: Ref | None
    shift_id: uuid.UUID | None
    fuel_type: FuelTypeOut
    quantity: Decimal
    unit: QuantityUnit
    unit_price: Decimal | None
    effective_unit_price: Decimal
    total_amount: Decimal
    occurred_at: datetime
    odometer_km: int | None
    vendor: str | None
    payment_method: PaymentMethod
    paid_by: PaidBy
    latitude: float | None
    longitude: float | None
    location_accuracy_m: float | None


class FuelTypeTotal(BaseModel):
    fuel_type: FuelTypeOut
    count: int
    quantity: Decimal
    total_amount: Decimal


class FuelSummary(BaseModel):
    by_type: list[FuelTypeTotal]
    fuel_amount: Decimal
    consumables_amount: Decimal
    pending_count: int


class DriverFuelCreate(BaseModel):
    """Fuel entry from the driver app (vehicle comes from the active shift)."""

    fuel_type_id: uuid.UUID
    quantity: Qty
    total_amount: Money
    unit_price: UnitPrice | None = None
    odometer_km: Odometer | None = None
    vendor: ShortText | None = None
    paid_by: PaidBy = PaidBy.DRIVER
    payment_method: PaymentMethod = PaymentMethod.CASH
    notes: Notes | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_accuracy_m: float | None = Field(default=None, ge=0, le=100_000)


# --- Expenses -------------------------------------------------------------------------


class ExpenseCategoryOut(ORMModel):
    id: uuid.UUID
    code: str
    name_ar: str
    pnl_group: ExpenseGroup
    is_active: bool
    sort_order: int


class ExpenseCategoryCreate(BaseModel):
    code: Code
    name_ar: NameAr
    pnl_group: ExpenseGroup = ExpenseGroup.OPERATING
    sort_order: int = Field(default=0, ge=0, le=999)


class ExpenseCategoryUpdate(BaseModel):
    name_ar: NameAr | None = None
    pnl_group: ExpenseGroup | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=999)


class ExpenseCreate(BaseModel):
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID | None = None
    shift_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    category_id: uuid.UUID
    amount: Money
    occurred_at: AwareDatetime
    vendor: ShortText | None = None
    payment_method: PaymentMethod = PaymentMethod.CASH
    paid_by: PaidBy = PaidBy.COMPANY
    notes: Notes | None = None
    approve_now: bool = False


class ExpenseCorrection(ExpenseCreate):
    reason: Reason


class ExpenseUpdate(BaseModel):
    driver_id: uuid.UUID | None = None
    shift_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    amount: Money | None = None
    occurred_at: AwareDatetime | None = None
    vendor: ShortText | None = None
    payment_method: PaymentMethod | None = None
    paid_by: PaidBy | None = None
    notes: Notes | None = None


class ExpenseOut(ReviewOut):
    id: uuid.UUID
    vehicle: Ref
    driver: Ref | None
    shift_id: uuid.UUID | None
    session_id: uuid.UUID | None
    category: ExpenseCategoryOut
    amount: Decimal
    occurred_at: datetime
    vendor: str | None
    payment_method: PaymentMethod
    paid_by: PaidBy


class ExpenseCategoryTotal(BaseModel):
    category: ExpenseCategoryOut
    count: int
    amount: Decimal


class ExpenseSummary(BaseModel):
    by_category: list[ExpenseCategoryTotal]
    total_amount: Decimal
    pending_count: int


# --- Revenue ------------------------------------------------------------------------------


class ReceiptIn(BaseModel):
    amount: Money
    received_at: AwareDatetime
    method: PaymentMethod
    received_by: ReceivedBy
    reference: Reference | None = None
    notes: Notes | None = None


class ReceiptOut(BaseModel):
    id: uuid.UUID
    amount: Decimal
    received_at: datetime
    method: PaymentMethod
    received_by: ReceivedBy
    reference: str | None
    notes: str | None
    created_by: UserRef | None
    created_at: datetime
    voided_at: datetime | None
    void_reason: str | None


class RevenueFields(BaseModel):
    kind: RevenueKind
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID | None = None
    shift_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    operation_type_id: uuid.UUID | None = None
    occurred_on: date
    period_start: date | None = None
    period_end: date | None = None
    amount: MoneyOrZero
    loops_count: int | None = Field(default=None, ge=0, le=1000)
    customer_name: ShortText | None = None
    reference: Reference | None = None
    notes: Notes | None = None

    @model_validator(mode="after")
    def _period(self) -> RevenueFields:
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("حدد بداية ونهاية فترة الخدمة معًا")
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("نهاية الفترة قبل بدايتها")
        return self


class RevenueCreate(RevenueFields):
    # Optional first receipt (e.g. the day's cash collection).
    receipt: ReceiptIn | None = None
    approve_now: bool = False


class RevenueCorrection(RevenueFields):
    reason: Reason
    approve_now: bool = False


class RevenueUpdate(BaseModel):
    driver_id: uuid.UUID | None = None
    shift_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    operation_type_id: uuid.UUID | None = None
    occurred_on: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    amount: MoneyOrZero | None = None
    loops_count: int | None = Field(default=None, ge=0, le=1000)
    customer_name: ShortText | None = None
    reference: Reference | None = None
    notes: Notes | None = None


class RevenueOut(ReviewOut):
    id: uuid.UUID
    kind: RevenueKind
    vehicle: Ref
    driver: Ref | None
    shift_id: uuid.UUID | None
    session_id: uuid.UUID | None
    operation_type: Ref | None
    occurred_on: date
    period_start: date | None
    period_end: date | None
    amount: Decimal
    fees_withheld: Decimal
    net_amount: Decimal
    received_amount: Decimal
    received_cash: Decimal
    received_electronic: Decimal
    outstanding_amount: Decimal
    loops_count: int | None
    customer_name: str | None
    reference: str | None
    statement_id: uuid.UUID | None
    receipts: list[ReceiptOut]


class RevenueSummary(BaseModel):
    by_kind: dict[str, Decimal]
    gross_amount: Decimal
    fees_withheld: Decimal
    received_cash: Decimal
    received_electronic: Decimal
    outstanding_amount: Decimal
    pending_count: int


# --- Ride-hailing ---------------------------------------------------------------------


class PlatformOut(ORMModel):
    id: uuid.UUID
    name: str
    is_active: bool
    notes: str | None


class PlatformCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    notes: Notes | None = None


class PlatformUpdate(BaseModel):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None
    ) = None
    is_active: bool | None = None
    notes: Notes | None = None


class StatementFields(BaseModel):
    platform_id: uuid.UUID
    driver_id: uuid.UUID
    vehicle_id: uuid.UUID
    period_start: date
    period_end: date
    trips_count: int | None = Field(default=None, ge=0, le=100_000)
    gross_earnings: MoneyOrZero
    platform_fees: MoneyOrZero
    tips: MoneyOrZero = Decimal("0")
    adjustments: SignedMoney = Decimal("0")
    cash_collected: MoneyOrZero = Decimal("0")
    payout_recipient: ReceivedBy = ReceivedBy.DRIVER
    statement_reference: Reference | None = None
    notes: Notes | None = None

    @model_validator(mode="after")
    def _consistent(self) -> StatementFields:
        if self.period_end < self.period_start:
            raise ValueError("نهاية الفترة قبل بدايتها")
        income = self.gross_earnings + self.tips + self.adjustments
        if income < 0:
            raise ValueError("إجمالي الدخل لا يمكن أن يكون سالبًا")
        if self.platform_fees > income:
            raise ValueError("عمولة المنصة أكبر من إجمالي الدخل")
        return self


class StatementCreate(StatementFields):
    approve_now: bool = False


class StatementCorrection(StatementFields):
    reason: Reason
    approve_now: bool = False


class StatementOut(ReviewOut):
    id: uuid.UUID
    platform: Ref
    driver: Ref
    vehicle: Ref
    period_start: date
    period_end: date
    trips_count: int | None
    gross_earnings: Decimal
    platform_fees: Decimal
    tips: Decimal
    adjustments: Decimal
    income: Decimal
    net_earnings: Decimal
    cash_collected: Decimal
    platform_payout: Decimal
    payout_recipient: ReceivedBy
    statement_reference: str | None
    revenue_entry_id: uuid.UUID | None


class ReconciliationFlag(BaseModel):
    code: str
    message: str


class ReconciliationRow(BaseModel):
    """One statement compared with recorded operational activity."""

    statement: StatementOut | None
    driver: Ref
    vehicle: Ref
    period_start: date
    period_end: date
    shifts_count: int
    ride_hailing_minutes: int
    odometer_km: int | None
    gps_km: float | None
    net_per_hour: Decimal | None
    net_per_km: Decimal | None
    flags: list[ReconciliationFlag]


class Reconciliation(BaseModel):
    rows: list[ReconciliationRow]
    # Days with ride-hailing work but no statement covering them.
    uncovered: list[ReconciliationRow]


# --- Driver ledger & settlements ------------------------------------------------------


class LedgerEntryIn(BaseModel):
    entry_type: LedgerEntryType
    amount: Money
    occurred_on: date
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=300)
    ]
    # Required for ADJUSTMENT: whether it credits or debits the driver.
    direction: Literal["CREDIT", "DEBIT"] | None = None
    reason: Reason | None = None
    vehicle_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _rules(self) -> LedgerEntryIn:
        if self.entry_type is LedgerEntryType.EARNING:
            raise ValueError("المستحقات تُسجل من التسويات فقط")
        if self.entry_type is LedgerEntryType.ADJUSTMENT:
            if self.direction is None:
                raise ValueError("حدد اتجاه التسوية (له أو عليه)")
            if self.reason is None:
                raise ValueError("سبب التسوية مطلوب")
        if self.entry_type is LedgerEntryType.DEDUCTION and self.reason is None:
            raise ValueError("سبب الخصم مطلوب")
        return self


class LedgerEntryOut(BaseModel):
    id: uuid.UUID
    driver_id: uuid.UUID
    entry_type: LedgerEntryType
    amount: Decimal
    occurred_on: date
    description: str
    reason: str | None
    source_type: LedgerSource
    source_id: uuid.UUID | None
    settlement_id: uuid.UUID | None
    vehicle_id: uuid.UUID | None
    period_start: date | None
    period_end: date | None
    created_by: UserRef | None
    created_at: datetime
    voided_at: datetime | None
    void_reason: str | None


class DriverStatement(BaseModel):
    driver: Ref
    date_from: date
    date_to: date
    opening_balance: Decimal
    earned: Decimal
    bonuses: Decimal
    reimbursements: Decimal
    cash_collected: Decimal
    cash_handed_over: Decimal
    advances: Decimal
    deductions: Decimal
    paid: Decimal
    adjustments: Decimal
    closing_balance: Decimal
    entries: list[LedgerEntryOut]


class SettlementCreate(BaseModel):
    driver_id: uuid.UUID
    period_start: date
    period_end: date
    notes: Notes | None = None

    @model_validator(mode="after")
    def _range(self) -> SettlementCreate:
        if self.period_end < self.period_start:
            raise ValueError("نهاية الفترة قبل بدايتها")
        if (self.period_end - self.period_start).days > 92:
            raise ValueError("فترة التسوية لا تتجاوز ثلاثة أشهر")
        return self


class SettlementOut(BaseModel):
    id: uuid.UUID
    driver: Ref
    period_start: date
    period_end: date
    status: SettlementStatus
    earnings_amount: Decimal
    details: dict[str, Any]
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    notes: str | None
    created_at: datetime
    finalized_at: datetime | None
    finalized_by: UserRef | None
    voided_at: datetime | None
    void_reason: str | None


# --- Profitability ----------------------------------------------------------------------


class PnlWarning(BaseModel):
    code: str
    message: str
    count: int | None = None


class OperationTypePnl(BaseModel):
    operation_type: Ref | None
    revenue: Decimal
    allocated_cost: Decimal
    profit: Decimal
    session_minutes: int


class VehiclePnl(BaseModel):
    vehicle: Ref
    date_from: date
    date_to: date
    gross_revenue: Decimal
    platform_fees: Decimal
    fuel_by_type: dict[str, Decimal]
    fuel_cost: Decimal
    consumables_cost: Decimal
    maintenance_cost: Decimal
    expenses_by_group: dict[str, Decimal]
    other_expenses: Decimal
    direct_operating_cost: Decimal
    driver_cost: Decimal
    net_operating_profit: Decimal
    shifts_count: int
    odometer_km: int
    gps_km: float
    cost_per_km: Decimal | None
    revenue_per_km: Decimal | None
    profit_per_shift: Decimal | None
    by_operation_type: list[OperationTypePnl]
    warnings: list[PnlWarning]


class FleetPnl(BaseModel):
    date_from: date
    date_to: date
    vehicles: list[VehiclePnl]
    totals: dict[str, Decimal]
