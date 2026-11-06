"""Driver day-offs, end-of-shift close-outs and cash collections.

A close-out is what the driver declares when ending a shift: odometer,
collection, fuel, toll («الكارتة») and maintenance or oil. Each money line
also becomes the usual finance record (revenue entry with a driver
receipt, driver-paid fuel or expense, all reviewed by the office), so
reports and the driver ledger keep a single source. The cash the driver
must hand over is the collection less the expenses that were not
rejected; a manager records what was actually received (cash collection),
and whatever is left carries over to the next day.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.models.base import Base, Quantity, UUIDPrimaryKeyMixin, enum_column_type
from app.models.driver import Driver
from app.models.finance import RecordSource
from app.models.fleet import Vehicle
from app.models.user import User


class DriverDayOff(UUIDPrimaryKeyMixin, Base):
    """«اليوم إجازة»: no shift, no tracking and no transactions that day."""

    __tablename__ = "driver_day_offs"

    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    day: Mapped[date]
    note: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[RecordSource] = mapped_column(enum_column_type(RecordSource, "record_source"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    cancelled_at: Mapped[datetime | None]
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))

    driver: Mapped[Driver] = relationship(lazy="joined")

    __table_args__ = (
        Index(
            "uq_driver_day_offs_live",
            "driver_id",
            "day",
            unique=True,
            postgresql_where=text("cancelled_at IS NULL"),
        ),
        Index("ix_driver_day_offs_day", "day"),
    )


class MaintenanceKind(StrEnum):
    NONE = "NONE"
    OIL_CHANGE = "OIL_CHANGE"  # تغيير زيت
    MAINTENANCE = "MAINTENANCE"  # صيانة


class ShiftCloseout(UUIDPrimaryKeyMixin, Base):
    """«تقفيل الوردية»: the driver's end-of-shift declaration. Voided, never edited."""

    __tablename__ = "shift_closeouts"

    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id"))
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    # Local (Cairo) date the shift started: the day the close-out belongs to.
    service_date: Mapped[date]
    submitted_at: Mapped[datetime]
    source: Mapped[RecordSource] = mapped_column(enum_column_type(RecordSource, "record_source"))
    end_odometer_km: Mapped[int] = mapped_column(Integer)
    collection_amount: Mapped[Decimal]
    gas_quantity: Mapped[Decimal | None] = mapped_column(Quantity)
    gas_amount: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    gasoline_quantity: Mapped[Decimal | None] = mapped_column(Quantity)
    gasoline_amount: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    toll_amount: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    maintenance_kind: Mapped[MaintenanceKind] = mapped_column(
        enum_column_type(MaintenanceKind, "maintenance_kind"), default=MaintenanceKind.NONE
    )
    maintenance_amount: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    maintenance_note: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # The finance records created from this close-out (null when the line was zero).
    revenue_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("revenue_entries.id"))
    gas_fuel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fuel_transactions.id"))
    gasoline_fuel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fuel_transactions.id"))
    toll_expense_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("expenses.id"))
    maintenance_expense_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("expenses.id"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    voided_at: Mapped[datetime | None]
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    void_reason: Mapped[str | None] = mapped_column(Text)

    driver: Mapped[Driver] = relationship(lazy="joined")
    vehicle: Mapped[Vehicle] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "collection_amount >= 0 AND gas_amount >= 0 AND gasoline_amount >= 0 "
            "AND toll_amount >= 0 AND maintenance_amount >= 0",
            name="amounts_non_negative",
        ),
        CheckConstraint("end_odometer_km >= 0", name="odometer_non_negative"),
        CheckConstraint(
            "gas_amount = 0 OR (gas_quantity IS NOT NULL AND gas_quantity > 0)",
            name="gas_quantity_required",
        ),
        CheckConstraint(
            "gasoline_amount = 0 OR (gasoline_quantity IS NOT NULL AND gasoline_quantity > 0)",
            name="gasoline_quantity_required",
        ),
        CheckConstraint(
            "(maintenance_kind = 'NONE' AND maintenance_amount = 0) OR "
            "(maintenance_kind <> 'NONE' AND maintenance_amount > 0 "
            "AND maintenance_note IS NOT NULL AND length(trim(maintenance_note)) > 0)",
            name="maintenance_complete",
        ),
        # One live close-out per shift; a voided one can be replaced.
        Index(
            "uq_shift_closeouts_live",
            "shift_id",
            unique=True,
            postgresql_where=text("voided_at IS NULL"),
        ),
        Index("ix_shift_closeouts_driver", "driver_id", "service_date"),
        Index("ix_shift_closeouts_day", "service_date"),
    )


class CashCollection(UUIDPrimaryKeyMixin, Base):
    """Cash a manager actually received from a driver. Voided, never edited."""

    __tablename__ = "cash_collections"

    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    # The close-out the manager recorded it against (null: an older remainder).
    closeout_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shift_closeouts.id"))
    amount: Mapped[Decimal]
    collected_at: Mapped[datetime]
    # Shown to the driver in «حسابي».
    note: Mapped[str | None] = mapped_column(String(300))
    collected_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    voided_at: Mapped[datetime | None]
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    void_reason: Mapped[str | None] = mapped_column(Text)

    collected_by: Mapped[User | None] = relationship(foreign_keys="CashCollection.collected_by_id")

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_cash_collections_driver", "driver_id", "collected_at"),
        Index("ix_cash_collections_closeout", "closeout_id"),
    )


__all__ = ["CashCollection", "DriverDayOff", "MaintenanceKind", "ShiftCloseout"]
