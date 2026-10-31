"""Work shifts and the operation sessions performed during them.

A shift is one driver working one vehicle for a period. Within a shift
the vehicle may perform several operations (e.g. university loops, then a
school route), each recorded as an OperationSession.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column_type
from app.models.driver import Driver
from app.models.fleet import Vehicle
from app.models.operations import OperationType, RouteDefinition


class ShiftStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ShiftSource(StrEnum):
    ADMIN = "ADMIN"
    DRIVER_APP = "DRIVER_APP"


class Shift(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shifts"

    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    status: Mapped[ShiftStatus] = mapped_column(
        enum_column_type(ShiftStatus, "shift_status"), default=ShiftStatus.PLANNED
    )
    planned_start_at: Mapped[datetime | None]
    planned_end_at: Mapped[datetime | None]
    planned_operation_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("operation_types.id")
    )
    planned_route_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("route_definitions.id"))
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]
    start_odometer_km: Mapped[int | None] = mapped_column(Integer)
    end_odometer_km: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[ShiftSource] = mapped_column(
        enum_column_type(ShiftSource, "shift_source"), default=ShiftSource.ADMIN
    )
    # Set when staff started a shift for a driver not assigned to the vehicle.
    assignment_override_reason: Mapped[str | None] = mapped_column(String(500))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    started_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ended_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    driver: Mapped[Driver] = relationship(lazy="joined")
    vehicle: Mapped[Vehicle] = relationship(lazy="joined")
    planned_operation_type: Mapped[OperationType | None] = relationship(lazy="joined")
    planned_route: Mapped[RouteDefinition | None] = relationship(lazy="joined")
    sessions: Mapped[list[OperationSession]] = relationship(
        back_populates="shift", order_by="OperationSession.started_at", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "end_odometer_km IS NULL OR start_odometer_km IS NULL "
            "OR end_odometer_km >= start_odometer_km",
            name="odometer_not_decreasing",
        ),
        CheckConstraint(
            "start_odometer_km IS NULL OR start_odometer_km >= 0", name="odometer_non_negative"
        ),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ends_after_start"),
        CheckConstraint(
            "status <> 'ACTIVE' OR (started_at IS NOT NULL AND start_odometer_km IS NOT NULL)",
            name="active_has_start",
        ),
        CheckConstraint(
            "status <> 'COMPLETED' OR (ended_at IS NOT NULL AND end_odometer_km IS NOT NULL)",
            name="completed_has_end",
        ),
        # At most one active shift per driver and per vehicle.
        Index(
            "uq_shifts_active_driver",
            "driver_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "uq_shifts_active_vehicle",
            "vehicle_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_shifts_driver_started", "driver_id", "started_at"),
        Index("ix_shifts_vehicle_started", "vehicle_id", "started_at"),
        Index("ix_shifts_status", "status"),
        Index("ix_shifts_planned_start", "planned_start_at"),
    )

    @property
    def odometer_distance_km(self) -> int | None:
        if self.start_odometer_km is None or self.end_odometer_km is None:
            return None
        return self.end_odometer_km - self.start_odometer_km


class SessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class OperationSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "operation_sessions"

    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id"))
    operation_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operation_types.id"))
    route_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("route_definitions.id"))
    status: Mapped[SessionStatus] = mapped_column(
        enum_column_type(SessionStatus, "session_status"), default=SessionStatus.ACTIVE
    )
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
    start_odometer_km: Mapped[int | None] = mapped_column(Integer)
    end_odometer_km: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    shift: Mapped[Shift] = relationship(back_populates="sessions")
    operation_type: Mapped[OperationType] = relationship(lazy="joined")
    route: Mapped[RouteDefinition | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ends_after_start"),
        CheckConstraint(
            "end_odometer_km IS NULL OR start_odometer_km IS NULL "
            "OR end_odometer_km >= start_odometer_km",
            name="odometer_not_decreasing",
        ),
        Index(
            "uq_operation_sessions_active_per_shift",
            "shift_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_operation_sessions_shift", "shift_id", "started_at"),
    )
