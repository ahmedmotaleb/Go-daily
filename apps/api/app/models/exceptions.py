"""Operational exceptions: explainable rule hits awaiting human review (Task 20).

An exception is a signal, never a verdict. Each row says which rule fired,
on what evidence, and links the vehicle/driver/shift/record involved.
Labels are deliberately neutral ("review needed" / "unusual case").
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column_type
from app.models.driver import Driver
from app.models.fleet import Vehicle
from app.models.user import User


class ExceptionSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ExceptionLabel(StrEnum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # مراجعة مطلوبة
    UNUSUAL = "UNUSUAL"  # حالة غير معتادة


class ExceptionStatus(StrEnum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    EXPLAINED = "EXPLAINED"
    CORRECTED = "CORRECTED"
    DISMISSED = "DISMISSED"
    ESCALATED = "ESCALATED"


class OperationalException(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "operational_exceptions"

    rule_code: Mapped[str] = mapped_column(String(40))
    severity: Mapped[ExceptionSeverity] = mapped_column(
        enum_column_type(ExceptionSeverity, "exception_severity")
    )
    label: Mapped[ExceptionLabel] = mapped_column(
        enum_column_type(ExceptionLabel, "exception_label")
    )
    summary: Mapped[str] = mapped_column(String(300))
    # Facts the rule used (times, distances, amounts, thresholds, record ids).
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # When the situation happened (vs. when the engine noticed it).
    occurred_at: Mapped[datetime]
    occurred_until: Mapped[datetime | None]
    detected_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    last_detected_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    # Set when a later run checked the same scope and no longer found it.
    cleared_at: Mapped[datetime | None]

    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    driver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drivers.id"))
    shift_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shifts.id"))
    # The record the signal is about, e.g. ("fuel_transaction", id).
    subject_type: Mapped[str | None] = mapped_column(String(40))
    subject_id: Mapped[uuid.UUID | None]
    # Same situation detected again updates this row instead of adding one.
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)

    status: Mapped[ExceptionStatus] = mapped_column(
        enum_column_type(ExceptionStatus, "exception_status"), default=ExceptionStatus.OPEN
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None]
    review_notes: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)

    vehicle: Mapped[Vehicle | None] = relationship(lazy="joined")
    driver: Mapped[Driver | None] = relationship(lazy="joined")
    reviewer: Mapped[User | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "occurred_until IS NULL OR occurred_until >= occurred_at", name="period_order"
        ),
        CheckConstraint("(subject_type IS NULL) = (subject_id IS NULL)", name="subject_paired"),
        Index("ix_operational_exceptions_status_occurred", "status", "occurred_at"),
        Index("ix_operational_exceptions_vehicle", "vehicle_id", "occurred_at"),
        Index("ix_operational_exceptions_driver", "driver_id", "occurred_at"),
        Index("ix_operational_exceptions_shift", "shift_id"),
        Index("ix_operational_exceptions_rule", "rule_code"),
    )


class ExceptionRun(UUIDPrimaryKeyMixin, Base):
    """One execution of the detection engine, for traceability."""

    __tablename__ = "exception_runs"

    started_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    finished_at: Mapped[datetime | None]
    window_start: Mapped[datetime]
    window_end: Mapped[datetime]
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    trigger: Mapped[str] = mapped_column(String(20))  # api | cli
    # {rule_code: {"found": n, "new": n}} and {rule_code: "error message"}
    results: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    errors: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    __table_args__ = (Index("ix_exception_runs_started", "started_at"),)
