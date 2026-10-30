"""Financial records: fuel/consumables, expenses, revenue, ride-hailing
statements, the driver account ledger and settlements.

Money is always Numeric(14, 2). Financial records are never edited after
approval and never deleted: a correction voids the original and creates a
replacement that points back to it (`corrects_id`), and both stay visible
in history. Reports count APPROVED records only.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.models.base import Base, Quantity, TimestampMixin, UUIDPrimaryKeyMixin, enum_column_type
from app.models.driver import Driver
from app.models.fleet import Vehicle
from app.models.operations import OperationType
from app.models.user import User


class RecordStatus(StrEnum):
    SUBMITTED = "SUBMITTED"  # entered, waiting for review; excluded from totals
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"  # returned to the submitter; may be edited and resubmitted
    VOIDED = "VOIDED"  # cancelled or replaced by a correction; kept for history


class RecordSource(StrEnum):
    ADMIN = "ADMIN"
    DRIVER_APP = "DRIVER_APP"
    SYSTEM = "SYSTEM"  # generated from another record (e.g. a ride-hailing statement)


class PaymentMethod(StrEnum):
    CASH = "CASH"
    CARD = "CARD"
    BANK_TRANSFER = "BANK_TRANSFER"
    WALLET = "WALLET"  # mobile wallets (e.g. Vodafone Cash, InstaPay)
    PLATFORM = "PLATFORM"  # settled by a ride-hailing platform
    OTHER = "OTHER"


class PaidBy(StrEnum):
    COMPANY = "COMPANY"
    DRIVER = "DRIVER"  # driver paid out of pocket or from collected cash -> reimbursement


class ReviewMixin:
    """Shared review/void columns for financial records."""

    status: Mapped[RecordStatus] = mapped_column(
        enum_column_type(RecordStatus, "record_status"), default=RecordStatus.SUBMITTED
    )
    source: Mapped[RecordSource] = mapped_column(
        enum_column_type(RecordSource, "record_source"), default=RecordSource.ADMIN
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None]
    review_note: Mapped[str | None] = mapped_column(Text)
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None]
    void_reason: Mapped[str | None] = mapped_column(Text)


# --- Fuel, CNG, oil & consumables -------------------------------------------


class FuelCategory(StrEnum):
    FUEL = "FUEL"  # counts towards fuel efficiency (CNG, gasoline, diesel)
    CONSUMABLE = "CONSUMABLE"  # engine oil and other consumables; never fuel efficiency


class QuantityUnit(StrEnum):
    LITER = "LITER"
    CUBIC_METER = "CUBIC_METER"  # CNG is sold per m³ in Egypt
    KG = "KG"
    UNIT = "UNIT"


class FuelType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Extensible fuel/consumable types (CNG, GASOLINE, DIESEL, ENGINE_OIL, ...)."""

    __tablename__ = "fuel_types"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name_ar: Mapped[str] = mapped_column(String(80))
    category: Mapped[FuelCategory] = mapped_column(enum_column_type(FuelCategory, "fuel_category"))
    default_unit: Mapped[QuantityUnit] = mapped_column(
        enum_column_type(QuantityUnit, "quantity_unit")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))


class FuelTransaction(UUIDPrimaryKeyMixin, TimestampMixin, ReviewMixin, Base):
    __tablename__ = "fuel_transactions"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    driver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drivers.id"))
    shift_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shifts.id"))
    fuel_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fuel_types.id"))
    quantity: Mapped[Decimal] = mapped_column(Quantity)
    unit: Mapped[QuantityUnit] = mapped_column(enum_column_type(QuantityUnit, "quantity_unit"))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    total_amount: Mapped[Decimal]
    occurred_at: Mapped[datetime]
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    vendor: Mapped[str | None] = mapped_column(String(150))
    payment_method: Mapped[PaymentMethod] = mapped_column(
        enum_column_type(PaymentMethod, "payment_method"), default=PaymentMethod.CASH
    )
    paid_by: Mapped[PaidBy] = mapped_column(
        enum_column_type(PaidBy, "paid_by"), default=PaidBy.COMPANY
    )
    # Only when captured by the authorised driver app at entry time.
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    location_accuracy_m: Mapped[float | None]
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fuel_transactions.id"))

    vehicle: Mapped[Vehicle] = relationship(lazy="joined")
    driver: Mapped[Driver | None] = relationship(lazy="joined")
    fuel_type: Mapped[FuelType] = relationship(lazy="joined")
    created_by: Mapped[User | None] = relationship(foreign_keys="FuelTransaction.created_by_id")
    reviewed_by: Mapped[User | None] = relationship(foreign_keys="FuelTransaction.reviewed_by_id")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("total_amount > 0", name="total_positive"),
        CheckConstraint("unit_price IS NULL OR unit_price > 0", name="unit_price_positive"),
        CheckConstraint("odometer_km IS NULL OR odometer_km >= 0", name="odometer_non_negative"),
        Index("ix_fuel_transactions_vehicle", "vehicle_id", "occurred_at"),
        Index("ix_fuel_transactions_driver", "driver_id", "occurred_at"),
        Index("ix_fuel_transactions_status", "status"),
    )


# --- General expenses ---------------------------------------------------------


class ExpenseGroup(StrEnum):
    """How a category is reported in vehicle P&L."""

    OPERATING = "OPERATING"
    MAINTENANCE = "MAINTENANCE"
    FINES = "FINES"
    OTHER = "OTHER"


class ExpenseCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "expense_categories"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name_ar: Mapped[str] = mapped_column(String(80))
    pnl_group: Mapped[ExpenseGroup] = mapped_column(
        enum_column_type(ExpenseGroup, "expense_group"), default=ExpenseGroup.OPERATING
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))


class Expense(UUIDPrimaryKeyMixin, TimestampMixin, ReviewMixin, Base):
    __tablename__ = "expenses"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    driver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drivers.id"))
    shift_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shifts.id"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("operation_sessions.id"))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expense_categories.id"))
    amount: Mapped[Decimal]
    occurred_at: Mapped[datetime]
    vendor: Mapped[str | None] = mapped_column(String(150))
    payment_method: Mapped[PaymentMethod] = mapped_column(
        enum_column_type(PaymentMethod, "payment_method"), default=PaymentMethod.CASH
    )
    paid_by: Mapped[PaidBy] = mapped_column(
        enum_column_type(PaidBy, "paid_by"), default=PaidBy.COMPANY
    )
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("expenses.id"))

    vehicle: Mapped[Vehicle] = relationship(lazy="joined")
    driver: Mapped[Driver | None] = relationship(lazy="joined")
    category: Mapped[ExpenseCategory] = relationship(lazy="joined")
    created_by: Mapped[User | None] = relationship(foreign_keys="Expense.created_by_id")
    reviewed_by: Mapped[User | None] = relationship(foreign_keys="Expense.reviewed_by_id")

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_expenses_vehicle", "vehicle_id", "occurred_at"),
        Index("ix_expenses_status", "status"),
    )


# --- Revenue ------------------------------------------------------------------


class RevenueKind(StrEnum):
    FIXED_ROUTE_COLLECTION = "FIXED_ROUTE_COLLECTION"  # تحصيل خط ثابت
    CONTRACT_SERVICE = "CONTRACT_SERVICE"  # عقد مدرسة/موظفين (allocated over its period)
    PRIVATE_TRIP = "PRIVATE_TRIP"  # رحلة خاصة
    RIDE_HAILING = "RIDE_HAILING"  # only created from an approved platform statement
    OTHER = "OTHER"


class ReceivedBy(StrEnum):
    DRIVER = "DRIVER"  # the driver holds the money until handover (custody)
    COMPANY = "COMPANY"


class RevenueEntry(UUIDPrimaryKeyMixin, TimestampMixin, ReviewMixin, Base):
    """One earned amount. The single source of revenue for every report.

    `amount` is the gross earned; `fees_withheld` is deducted at source
    (platform commission); money actually received is tracked in receipts,
    so outstanding = amount - fees_withheld - received.
    """

    __tablename__ = "revenue_entries"

    kind: Mapped[RevenueKind] = mapped_column(enum_column_type(RevenueKind, "revenue_kind"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    driver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drivers.id"))
    shift_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shifts.id"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("operation_sessions.id"))
    operation_type_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("operation_types.id"))
    occurred_on: Mapped[date]
    # Service period (contracts, statements); amounts are spread over it in reports.
    period_start: Mapped[date | None]
    period_end: Mapped[date | None]
    amount: Mapped[Decimal]
    fees_withheld: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    loops_count: Mapped[int | None] = mapped_column(Integer)
    customer_name: Mapped[str | None] = mapped_column(String(150))
    reference: Mapped[str | None] = mapped_column(String(100))
    statement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ride_hailing_statements.id"))
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("revenue_entries.id"))

    vehicle: Mapped[Vehicle] = relationship(lazy="joined")
    driver: Mapped[Driver | None] = relationship(lazy="joined")
    operation_type: Mapped[OperationType | None] = relationship(lazy="joined")
    receipts: Mapped[list[RevenueReceipt]] = relationship(
        back_populates="entry", order_by="RevenueReceipt.received_at"
    )

    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint(
            "fees_withheld >= 0 AND fees_withheld <= amount", name="fees_within_amount"
        ),
        CheckConstraint(
            "(period_start IS NULL AND period_end IS NULL) OR "
            "(period_start IS NOT NULL AND period_end IS NOT NULL AND period_end >= period_start)",
            name="period_range",
        ),
        CheckConstraint("loops_count IS NULL OR loops_count >= 0", name="loops_non_negative"),
        # A statement produces at most one live revenue entry (no double counting).
        Index(
            "uq_revenue_entries_statement",
            "statement_id",
            unique=True,
            postgresql_where=text("statement_id IS NOT NULL AND status <> 'VOIDED'"),
        ),
        Index("ix_revenue_entries_vehicle", "vehicle_id", "occurred_on"),
        Index("ix_revenue_entries_driver", "driver_id", "occurred_on"),
        Index("ix_revenue_entries_status", "status"),
    )


class RevenueReceipt(UUIDPrimaryKeyMixin, Base):
    """Money received against a revenue entry. Voided, never deleted."""

    __tablename__ = "revenue_receipts"

    revenue_entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("revenue_entries.id"))
    received_at: Mapped[datetime]
    amount: Mapped[Decimal]
    method: Mapped[PaymentMethod] = mapped_column(enum_column_type(PaymentMethod, "payment_method"))
    received_by: Mapped[ReceivedBy] = mapped_column(enum_column_type(ReceivedBy, "received_by"))
    reference: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None]
    void_reason: Mapped[str | None] = mapped_column(Text)

    entry: Mapped[RevenueEntry] = relationship(back_populates="receipts")

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_revenue_receipts_entry", "revenue_entry_id"),
    )


# --- Ride-hailing -------------------------------------------------------------


class RideHailingPlatform(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A smart-transport platform. Earnings are entered manually from its
    statements; no platform is scraped or integrated without an approved API.
    """

    __tablename__ = "ride_hailing_platforms"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    notes: Mapped[str | None] = mapped_column(Text)


class RideHailingStatement(UUIDPrimaryKeyMixin, TimestampMixin, ReviewMixin, Base):
    __tablename__ = "ride_hailing_statements"

    platform_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ride_hailing_platforms.id"))
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    period_start: Mapped[date]
    period_end: Mapped[date]
    trips_count: Mapped[int | None] = mapped_column(Integer)
    gross_earnings: Mapped[Decimal]
    platform_fees: Mapped[Decimal]
    tips: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    # Bonuses (+) or platform corrections (-).
    adjustments: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    # Cash paid by riders directly to the driver.
    cash_collected: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    # Who receives the platform's electronic payout.
    payout_recipient: Mapped[ReceivedBy] = mapped_column(
        enum_column_type(ReceivedBy, "received_by"), default=ReceivedBy.DRIVER
    )
    statement_reference: Mapped[str | None] = mapped_column(String(100))
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ride_hailing_statements.id"))

    platform: Mapped[RideHailingPlatform] = relationship(lazy="joined")
    driver: Mapped[Driver] = relationship(lazy="joined")
    vehicle: Mapped[Vehicle] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="period_range"),
        CheckConstraint("gross_earnings >= 0", name="gross_non_negative"),
        CheckConstraint("platform_fees >= 0", name="fees_non_negative"),
        CheckConstraint("tips >= 0", name="tips_non_negative"),
        CheckConstraint("cash_collected >= 0", name="cash_non_negative"),
        CheckConstraint("trips_count IS NULL OR trips_count >= 0", name="trips_non_negative"),
        Index("ix_ride_hailing_statements_driver", "driver_id", "period_start"),
        Index("ix_ride_hailing_statements_vehicle", "vehicle_id", "period_start"),
    )

    @property
    def income(self) -> Decimal:
        """Gross platform income for the period (fares + tips + adjustments)."""
        return self.gross_earnings + self.tips + self.adjustments

    @property
    def net_earnings(self) -> Decimal:
        return self.income - self.platform_fees

    @property
    def platform_payout(self) -> Decimal:
        """Electronic payout due; negative means the driver owes the platform."""
        return self.net_earnings - self.cash_collected


# --- Driver account -------------------------------------------------------------


class LedgerEntryType(StrEnum):
    EARNING = "EARNING"  # + compensation earned (from a finalised settlement)
    BONUS = "BONUS"  # +
    REIMBURSEMENT = "REIMBURSEMENT"  # + driver paid a company cost
    CASH_HANDOVER = "CASH_HANDOVER"  # + driver handed collected cash to the company
    ADVANCE = "ADVANCE"  # - company advanced money
    DEDUCTION = "DEDUCTION"  # -
    PAYMENT = "PAYMENT"  # - company paid the driver
    CASH_COLLECTED = "CASH_COLLECTED"  # - driver holds company money (fares, payouts)
    ADJUSTMENT = "ADJUSTMENT"  # ± manual, reason required


CREDIT_TYPES = frozenset(
    {
        LedgerEntryType.EARNING,
        LedgerEntryType.BONUS,
        LedgerEntryType.REIMBURSEMENT,
        LedgerEntryType.CASH_HANDOVER,
    }
)
DEBIT_TYPES = frozenset(
    {
        LedgerEntryType.ADVANCE,
        LedgerEntryType.DEDUCTION,
        LedgerEntryType.PAYMENT,
        LedgerEntryType.CASH_COLLECTED,
    }
)


class LedgerSource(StrEnum):
    MANUAL = "MANUAL"
    SETTLEMENT = "SETTLEMENT"
    EXPENSE = "EXPENSE"
    FUEL = "FUEL"
    REVENUE_RECEIPT = "REVENUE_RECEIPT"


class DriverLedgerEntry(UUIDPrimaryKeyMixin, Base):
    """Driver account movement. Balance = what the company owes the driver
    (negative: the driver owes the company). Append-only: corrections void
    an entry and add a new one.
    """

    __tablename__ = "driver_ledger_entries"

    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    entry_type: Mapped[LedgerEntryType] = mapped_column(
        enum_column_type(LedgerEntryType, "ledger_entry_type")
    )
    # Signed: credits positive, debits negative.
    amount: Mapped[Decimal]
    occurred_on: Mapped[date]
    description: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[LedgerSource] = mapped_column(
        enum_column_type(LedgerSource, "ledger_source"), default=LedgerSource.MANUAL
    )
    source_id: Mapped[uuid.UUID | None]
    settlement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("driver_settlements.id"))
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    # Period the amount relates to (earnings): spread over it in vehicle P&L.
    period_start: Mapped[date | None]
    period_end: Mapped[date | None]
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None]
    void_reason: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[User | None] = relationship(foreign_keys="DriverLedgerEntry.created_by_id")

    __table_args__ = (
        CheckConstraint("amount <> 0", name="amount_non_zero"),
        CheckConstraint(
            "entry_type NOT IN ('EARNING','BONUS','REIMBURSEMENT','CASH_HANDOVER') OR amount > 0",
            name="credit_sign",
        ),
        CheckConstraint(
            "entry_type NOT IN ('ADVANCE','DEDUCTION','PAYMENT','CASH_COLLECTED') OR amount < 0",
            name="debit_sign",
        ),
        # A source record posts at most one live entry.
        Index(
            "uq_driver_ledger_source",
            "source_type",
            "source_id",
            unique=True,
            postgresql_where=text("source_id IS NOT NULL AND voided_at IS NULL"),
        ),
        Index("ix_driver_ledger_driver", "driver_id", "occurred_on"),
    )


class SettlementStatus(StrEnum):
    DRAFT = "DRAFT"
    FINALIZED = "FINALIZED"  # earnings posted to the ledger; immutable
    VOIDED = "VOIDED"


class DriverSettlement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Compensation for a period, computed from the plan(s) in force.

    The calculation (plan terms, inputs, lines) is frozen in `details` when
    finalised, so later plan changes never alter a historical settlement.
    """

    __tablename__ = "driver_settlements"

    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    period_start: Mapped[date]
    period_end: Mapped[date]
    status: Mapped[SettlementStatus] = mapped_column(
        enum_column_type(SettlementStatus, "settlement_status"), default=SettlementStatus.DRAFT
    )
    earnings_amount: Mapped[Decimal]
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)
    opening_balance: Mapped[Decimal | None]
    closing_balance: Mapped[Decimal | None]
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    finalized_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    finalized_at: Mapped[datetime | None]
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None]
    void_reason: Mapped[str | None] = mapped_column(Text)

    driver: Mapped[Driver] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="period_range"),
        CheckConstraint("earnings_amount >= 0", name="earnings_non_negative"),
        # Finalised settlements of one driver never overlap.
        ExcludeConstraint(
            ("driver_id", "="),
            (func.daterange(text("period_start"), text("period_end"), text("'[]'")), "&&"),
            name="ex_driver_settlements_overlap",
            using="gist",
            where=text("status = 'FINALIZED'"),
        ),
        Index("ix_driver_settlements_driver", "driver_id", "period_start"),
    )
