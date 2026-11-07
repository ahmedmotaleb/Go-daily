"""Day-offs, end-of-shift close-outs, cash collections and the driver's cash account."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

from app.models.cash import MaintenanceKind
from app.models.finance import RecordSource, RecordStatus
from app.schemas.finance import ClientEntryId, Money, MoneyOrZero, Notes, Odometer, Reason
from app.schemas.shift import PersonRef, VehicleRef

ShortNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
# Quantities on the close-out: optional, but required when the amount is above zero.
OptionalQty = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)]

CloseoutStatus = Literal["WAITING", "PARTIAL", "COLLECTED", "NOTHING_DUE"]


# --- Day-offs -------------------------------------------------------------------


class DayOffIn(BaseModel):
    note: ShortNote | None = None


class StaffDayOffIn(DayOffIn):
    driver_id: uuid.UUID
    day: date


class CancelIn(BaseModel):
    reason: ShortNote | None = None


class DayOffOut(BaseModel):
    id: uuid.UUID
    driver: PersonRef
    day: date
    note: str | None
    source: RecordSource
    created_at: datetime


# --- Close-outs -----------------------------------------------------------------


class CloseoutIn(BaseModel):
    """«تقفيل الوردية». Zero means none; a quantity is required with a fuel amount."""

    end_odometer_km: Odometer
    collection_amount: MoneyOrZero
    gas_quantity: OptionalQty | None = None
    gas_amount: MoneyOrZero = Decimal("0")
    gasoline_quantity: OptionalQty | None = None
    gasoline_amount: MoneyOrZero = Decimal("0")
    # «الكارتة»: asked every shift; 0 when there was none.
    toll_amount: MoneyOrZero
    maintenance_kind: MaintenanceKind = MaintenanceKind.NONE
    maintenance_amount: MoneyOrZero = Decimal("0")
    maintenance_note: Notes | None = None
    notes: Notes | None = None
    # Close-outs queued on the phone (U45): stable id and the phone's clock.
    client_entry_id: ClientEntryId | None = None
    recorded_at: AwareDatetime | None = None


class CloseoutLine(BaseModel):
    key: Literal["gas", "gasoline", "toll", "maintenance"]
    label: str
    quantity: Decimal | None
    unit: str | None
    amount: Decimal
    # Review state of the finance record behind the line (null: nothing recorded).
    record_status: RecordStatus | None
    # False when the office rejected or voided it: the amount is then due from the driver.
    deducted: bool


class CollectionOut(BaseModel):
    id: uuid.UUID
    driver_id: uuid.UUID
    closeout_id: uuid.UUID | None
    amount: Decimal
    collected_at: datetime
    note: str | None
    collected_by: PersonRef | None
    voided_at: datetime | None
    void_reason: str | None


class CloseoutOut(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    driver: PersonRef
    vehicle: VehicleRef
    service_date: date
    submitted_at: datetime
    source: RecordSource
    operation_label: str
    start_odometer_km: int | None
    end_odometer_km: int
    start_odometer_photo_id: uuid.UUID | None
    collection_amount: Decimal
    # Collection is not booked as revenue here for ride-hailing (statements are the source).
    collection_booked: bool
    lines: list[CloseoutLine]
    maintenance_kind: MaintenanceKind
    maintenance_note: str | None
    notes: str | None
    receipt_attachment_ids: list[uuid.UUID]
    deductions: Decimal
    # Collection less the deductions: what this shift hands over (negative: owed to the driver).
    net_amount: Decimal
    # Not yet collected from earlier close-outs when this one was submitted.
    carried_before: Decimal
    total_due: Decimal
    collected: Decimal
    remaining: Decimal
    status: CloseoutStatus
    collections: list[CollectionOut]
    voided_at: datetime | None
    void_reason: str | None


class StaffCloseoutIn(CloseoutIn):
    """Office entry on the driver's behalf (paper close-out, or after a void)."""


class VoidIn(BaseModel):
    reason: Reason


# --- Collections ----------------------------------------------------------------


class CollectionIn(BaseModel):
    driver_id: uuid.UUID
    closeout_id: uuid.UUID | None = None
    amount: Money
    note: ShortNote | None = None


# --- Board and account ----------------------------------------------------------


class BoardRow(BaseModel):
    kind: Literal["CLOSEOUT", "DAY_OFF", "OPEN_SHIFT", "ENDED_NOT_CLOSED"]
    driver: PersonRef
    vehicle: VehicleRef | None
    operation_label: str | None
    closeout: CloseoutOut | None = None
    day_off: DayOffOut | None = None
    shift_id: uuid.UUID | None = None
    started_at: datetime | None = None
    # The driver's whole balance now (all days).
    outstanding: Decimal


class CashBoardOut(BaseModel):
    day: date
    net_due: Decimal
    closeouts: int
    collected: Decimal
    open_balance: Decimal
    day_offs: int
    open_shifts: int
    rows: list[BoardRow]


class AccountDay(BaseModel):
    day: date
    kind: Literal["CLOSEOUT", "DAY_OFF", "COLLECTION"]
    closeout: CloseoutOut | None = None
    day_off: DayOffOut | None = None
    collection: CollectionOut | None = None


class CashAccountOut(BaseModel):
    driver: PersonRef
    outstanding: Decimal
    date_from: date
    date_to: date
    due_total: Decimal
    collected_total: Decimal
    day_off_days: int
    days: list[AccountDay]
    # Today's state for the driver app home: day-off or the submitted close-out.
    today_day_off: DayOffOut | None
    today_closeout: CloseoutOut | None


class PhotoOut(BaseModel):
    attachment_id: uuid.UUID
    created_at: datetime


__all__ = [
    "AccountDay",
    "BoardRow",
    "CancelIn",
    "CashAccountOut",
    "CashBoardOut",
    "CloseoutIn",
    "CloseoutLine",
    "CloseoutOut",
    "CloseoutStatus",
    "CollectionIn",
    "CollectionOut",
    "DayOffIn",
    "DayOffOut",
    "PhotoOut",
    "StaffCloseoutIn",
    "StaffDayOffIn",
    "VoidIn",
]
