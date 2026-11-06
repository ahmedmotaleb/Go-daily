"""Fleet: vehicle types and vehicles.

Vehicles never carry a permanent driver or operation type: drivers are
linked through the assignment history (assignment.py) and work through
shifts/operation sessions.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column_type


class VehicleType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Extensible lookup (seeded: MICROBUS, SEDAN, VAN, BUS, OTHER)."""

    __tablename__ = "vehicle_types"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name_ar: Mapped[str] = mapped_column(String(80))
    name_en: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(default=0, server_default=text("0"))


class OwnershipStatus(StrEnum):
    OWNED = "OWNED"  # ملك الشركة
    LEASED = "LEASED"  # إيجار
    PARTNER = "PARTNER"  # شراكة / مستثمر
    DRIVER_OWNED = "DRIVER_OWNED"  # ملك السائق
    OTHER = "OTHER"


class Vehicle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"

    internal_code: Mapped[str] = mapped_column(String(30), unique=True)
    plate_number: Mapped[str] = mapped_column(String(30))
    # Normalised plate (letters folded, digits latinised) for uniqueness/search.
    plate_key: Mapped[str] = mapped_column(String(30), unique=True)
    vehicle_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicle_types.id"))
    manufacturer: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(60))
    model_year: Mapped[int | None] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(String(40))
    ownership_status: Mapped[OwnershipStatus] = mapped_column(
        enum_column_type(OwnershipStatus, "ownership_status"),
        default=OwnershipStatus.OWNED,
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    current_odometer_km: Mapped[int | None] = mapped_column(Integer)
    license_expiry: Mapped[date | None]
    insurance_expiry: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)

    vehicle_type: Mapped[VehicleType] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "model_year IS NULL OR model_year BETWEEN 1950 AND 2100", name="model_year_range"
        ),
        CheckConstraint(
            "current_odometer_km IS NULL OR current_odometer_km >= 0", name="odometer_non_negative"
        ),
        Index("ix_vehicles_is_active", "is_active"),
        Index("ix_vehicles_vehicle_type_id", "vehicle_type_id"),
    )
