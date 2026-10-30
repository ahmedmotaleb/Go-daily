"""Drivers and their compensation plans.

A Driver is a domain profile (HR/operations data). It may link to a User
account with role DRIVER for the driver app, but the two are separate.

National IDs are stored encrypted with a keyed blind index for uniqueness;
they never appear in logs or audit records.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column_type
from app.models.user import User


class EmploymentStatus(StrEnum):
    ACTIVE = "ACTIVE"  # يعمل
    ON_LEAVE = "ON_LEAVE"  # إجازة
    SUSPENDED = "SUSPENDED"  # موقوف
    TERMINATED = "TERMINATED"  # انتهى التعاقد


class Driver(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "drivers"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    national_id_encrypted: Mapped[str | None] = mapped_column(Text)
    national_id_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    national_id_last4: Mapped[str | None] = mapped_column(String(4))
    license_number: Mapped[str | None] = mapped_column(String(40))
    license_expiry: Mapped[date | None]
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        enum_column_type(EmploymentStatus, "employment_status"),
        default=EmploymentStatus.ACTIVE,
    )
    hire_date: Mapped[date | None]
    end_date: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User | None] = relationship(lazy="joined")

    __table_args__ = (Index("ix_drivers_employment_status", "employment_status"),)


class CompensationMethod(StrEnum):
    FIXED_MONTHLY = "FIXED_MONTHLY"  # راتب شهري ثابت
    DAILY_WAGE = "DAILY_WAGE"  # يومية
    REVENUE_PERCENTAGE = "REVENUE_PERCENTAGE"  # نسبة من الإيراد
    FIXED_PLUS_INCENTIVE = "FIXED_PLUS_INCENTIVE"  # ثابت + حافز


class DriverCompensationPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Versioned compensation terms. Plans are never edited after they take
    effect; a change creates a new plan and closes the previous one, so
    historical settlements keep the terms that applied at the time.
    """

    __tablename__ = "driver_compensation_plans"

    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    method: Mapped[CompensationMethod] = mapped_column(
        enum_column_type(CompensationMethod, "compensation_method")
    )
    fixed_monthly_amount: Mapped[Decimal | None]
    daily_wage_amount: Mapped[Decimal | None]
    # Percent of eligible revenue (0-100), e.g. 25.00.
    revenue_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # FIXED_PLUS_INCENTIVE: incentive % of eligible revenue above the threshold.
    incentive_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    incentive_threshold_amount: Mapped[Decimal | None]
    effective_from: Mapped[date]
    effective_to: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="effective_range"
        ),
        CheckConstraint(
            "revenue_percentage IS NULL OR (revenue_percentage >= 0 AND revenue_percentage <= 100)",
            name="revenue_percentage_range",
        ),
        CheckConstraint(
            "incentive_percentage IS NULL OR "
            "(incentive_percentage >= 0 AND incentive_percentage <= 100)",
            name="incentive_percentage_range",
        ),
        # Plans for one driver never overlap in time.
        ExcludeConstraint(
            ("driver_id", "="),
            (func.daterange(text("effective_from"), text("effective_to"), text("'[]'")), "&&"),
            name="ex_compensation_plans_overlap",
            using="gist",
        ),
        Index("ix_driver_compensation_plans_driver", "driver_id", "effective_from"),
    )
