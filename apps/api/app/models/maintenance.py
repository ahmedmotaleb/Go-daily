"""Maintenance: types, per-vehicle schedules and service records (Task 21).

A service record is a cost, so it follows the financial review lifecycle
(submitted, approved, rejected, voided; corrections replace). Buying engine
oil is a fuel/consumable transaction; changing it is a maintenance record.
The two can be linked, never confused.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Quantity, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.finance import FuelType, ReviewMixin
from app.models.fleet import Vehicle


class MaintenanceType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_types"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name_ar: Mapped[str] = mapped_column(String(80))
    # Default intervals; a vehicle schedule may override them.
    interval_km: Mapped[int | None] = mapped_column(Integer)
    interval_days: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))
    # The consumable this service uses (U17), e.g. an oil change uses engine
    # oil: its records are reconciled with the purchases of that consumable.
    consumable_type_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fuel_types.id"))

    consumable_type: Mapped[FuelType | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("interval_km IS NULL OR interval_km > 0", name="interval_km_positive"),
        CheckConstraint(
            "interval_days IS NULL OR interval_days > 0", name="interval_days_positive"
        ),
    )


class MaintenanceSchedule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Which maintenance a vehicle needs, and how often."""

    __tablename__ = "maintenance_schedules"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("maintenance_types.id"))
    interval_km: Mapped[int | None] = mapped_column(Integer)
    interval_days: Mapped[int | None] = mapped_column(Integer)
    # Starting point used until the first service record of this type exists.
    baseline_km: Mapped[int | None] = mapped_column(Integer)
    baseline_date: Mapped[date | None]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))

    vehicle: Mapped[Vehicle] = relationship(lazy="joined")
    type: Mapped[MaintenanceType] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("vehicle_id", "type_id", name="uq_maintenance_schedules_vehicle_type"),
        CheckConstraint("interval_km IS NULL OR interval_km > 0", name="interval_km_positive"),
        CheckConstraint(
            "interval_days IS NULL OR interval_days > 0", name="interval_days_positive"
        ),
    )


class MaintenanceRecord(UUIDPrimaryKeyMixin, TimestampMixin, ReviewMixin, Base):
    __tablename__ = "maintenance_records"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("maintenance_types.id"))
    performed_on: Mapped[date]
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    vendor: Mapped[str | None] = mapped_column(String(150))
    parts_cost: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    labor_cost: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    other_cost: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    description: Mapped[str | None] = mapped_column(Text)
    downtime_start: Mapped[datetime | None]
    downtime_end: Mapped[datetime | None]
    # Optional link to the oil/consumable purchase used in this service.
    fuel_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fuel_transactions.id")
    )
    # What was put in (U17): quantity in the purchase's unit, and the grade
    # (e.g. 5W-30). The next targets are stored as decided at the service.
    consumable_quantity: Mapped[Decimal | None] = mapped_column(Quantity)
    consumable_spec: Mapped[str | None] = mapped_column(String(80))
    next_due_km: Mapped[int | None] = mapped_column(Integer)
    next_due_on: Mapped[date | None]
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("maintenance_records.id"))

    vehicle: Mapped[Vehicle] = relationship(lazy="joined")
    type: Mapped[MaintenanceType] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "parts_cost >= 0 AND labor_cost >= 0 AND other_cost >= 0", name="costs_non_negative"
        ),
        CheckConstraint("odometer_km IS NULL OR odometer_km >= 0", name="odometer_non_negative"),
        CheckConstraint(
            "consumable_quantity IS NULL OR consumable_quantity > 0",
            name="consumable_quantity_positive",
        ),
        CheckConstraint(
            "downtime_end IS NULL OR "
            "(downtime_start IS NOT NULL AND downtime_end >= downtime_start)",
            name="downtime_range",
        ),
        Index("ix_maintenance_records_vehicle", "vehicle_id", "performed_on"),
        Index("ix_maintenance_records_status", "status"),
    )

    @property
    def total_cost(self) -> Decimal:
        return self.parts_cost + self.labor_cost + self.other_cost
