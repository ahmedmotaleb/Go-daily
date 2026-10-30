"""Geofence / route events derived from GPS (and admin corrections).

Events are derived deterministically from stored GPS points. Re-running
detection never duplicates rows (dedupe key) and never deletes: automatic
events that are no longer produced are VOIDED with a system reason.
Admins can void events or add manual ones; both are audited.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column_type


class RouteEventType(StrEnum):
    ENTERED = "ENTERED"
    EXITED = "EXITED"
    REACHED_ORIGIN = "REACHED_ORIGIN"
    REACHED_DESTINATION = "REACHED_DESTINATION"
    LEG_COMPLETED = "LEG_COMPLETED"
    LOOP_COMPLETED = "LOOP_COMPLETED"


class LegDirection(StrEnum):
    OUTBOUND = "OUTBOUND"  # origin -> destination
    INBOUND = "INBOUND"  # destination -> origin


class EventSource(StrEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class EventStatus(StrEnum):
    ACTIVE = "ACTIVE"
    VOIDED = "VOIDED"


class RouteEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "route_events"

    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id"))
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operation_sessions.id"))
    route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("route_definitions.id"))
    stop_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("route_stops.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    event_type: Mapped[RouteEventType] = mapped_column(
        enum_column_type(RouteEventType, "route_event_type")
    )
    direction: Mapped[LegDirection | None] = mapped_column(
        enum_column_type(LegDirection, "leg_direction")
    )
    occurred_at: Mapped[datetime]
    sequence_no: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[EventSource] = mapped_column(enum_column_type(EventSource, "event_source"))
    status: Mapped[EventStatus] = mapped_column(
        enum_column_type(EventStatus, "event_status"), default=EventStatus.ACTIVE
    )
    dedupe_key: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str | None] = mapped_column(String(500))
    void_reason: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        Index("uq_route_events_dedupe", "dedupe_key", unique=True),
        Index("ix_route_events_session", "session_id", "occurred_at"),
        Index("ix_route_events_vehicle", "vehicle_id", "occurred_at"),
    )


class SchoolRunStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"  # GPS evidence shows the route was served
    COMPLETED_UNVERIFIED = "COMPLETED_UNVERIFIED"  # ended without GPS evidence -> review
    MISSED = "MISSED"
    CANCELLED = "CANCELLED"


class SchoolRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One scheduled school duty (e.g. morning pickup) on a service date.

    School routes are RouteDefinitions of kind SCHOOL_ROUTE; several schools
    or contracts are simply several routes (and later contract links), so
    the model does not assume a single school.
    """

    __tablename__ = "school_runs"

    route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("route_definitions.id"))
    service_date: Mapped[date]
    scheduled_start_at: Mapped[datetime]
    scheduled_end_at: Mapped[datetime]
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    driver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drivers.id"))
    status: Mapped[SchoolRunStatus] = mapped_column(
        enum_column_type(SchoolRunStatus, "school_run_status"), default=SchoolRunStatus.SCHEDULED
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("operation_sessions.id"))
    actual_start_at: Mapped[datetime | None]
    actual_end_at: Mapped[datetime | None]
    label: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(String(2000))
    status_reason: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        Index("ix_school_runs_date", "service_date"),
        Index("ix_school_runs_vehicle", "vehicle_id", "scheduled_start_at"),
        Index(
            "uq_school_runs_route_vehicle_start",
            "route_id",
            "vehicle_id",
            "scheduled_start_at",
            unique=True,
        ),
        Index("uq_school_runs_session", "session_id", unique=True),
    )
