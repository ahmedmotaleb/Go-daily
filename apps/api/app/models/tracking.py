"""Work-shift GPS tracking.

Privacy: points are accepted only for the driver's own shift and only for
timestamps inside that shift window; nothing is recorded outside work.

Integrity: points are never fabricated or interpolated. Suspicious points
are kept as evidence with a `quality` flag; analytics use VALID points.

Retention: raw points are indexed by time (BRIN) so old data can be pruned
in bulk (`python -m app.cli prune-gps`) after shift summaries exist.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin, enum_column_type


class PointSource(StrEnum):
    GPS = "GPS"
    NETWORK = "NETWORK"
    FUSED = "FUSED"
    UNKNOWN = "UNKNOWN"


class PointQuality(StrEnum):
    VALID = "VALID"
    LOW_ACCURACY = "LOW_ACCURACY"  # reported accuracy worse than the threshold
    IMPLAUSIBLE_SPEED = "IMPLAUSIBLE_SPEED"  # jump from the previous point is physically unlikely
    MOCK = "MOCK"  # device reported a mock/test location provider


class GpsPoint(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "gps_points"

    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id"))
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    client_point_id: Mapped[uuid.UUID]
    batch_id: Mapped[uuid.UUID | None]
    recorded_at: Mapped[datetime]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    altitude_m: Mapped[float | None] = mapped_column(Float)
    source: Mapped[PointSource] = mapped_column(
        enum_column_type(PointSource, "point_source"), default=PointSource.UNKNOWN
    )
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    quality: Mapped[PointQuality] = mapped_column(
        enum_column_type(PointQuality, "point_quality"), default=PointQuality.VALID
    )

    __table_args__ = (
        # Idempotent ingestion: a point is stored once per shift.
        Index("uq_gps_points_shift_client", "shift_id", "client_point_id", unique=True),
        Index("ix_gps_points_shift_recorded", "shift_id", "recorded_at"),
        Index("ix_gps_points_vehicle_recorded", "vehicle_id", "recorded_at"),
        Index("brin_gps_points_recorded_at", "recorded_at", postgresql_using="brin"),
    )


class VehicleLatestPosition(Base):
    """Most recent point per vehicle, for the live map."""

    __tablename__ = "vehicle_latest_positions"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"), primary_key=True)
    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id"))
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gps_points.id"))
    recorded_at: Mapped[datetime]
    received_at: Mapped[datetime]
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)


class TrackingEventType(StrEnum):
    TRACKING_STARTED = "TRACKING_STARTED"
    TRACKING_STOPPED = "TRACKING_STOPPED"
    PERMISSION_GRANTED = "PERMISSION_GRANTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    BACKGROUND_PERMISSION_DENIED = "BACKGROUND_PERMISSION_DENIED"
    LOCATION_DISABLED = "LOCATION_DISABLED"
    LOCATION_ENABLED = "LOCATION_ENABLED"
    GPS_SIGNAL_LOST = "GPS_SIGNAL_LOST"
    GPS_SIGNAL_RESTORED = "GPS_SIGNAL_RESTORED"
    BATTERY_OPTIMIZATION_ENABLED = "BATTERY_OPTIMIZATION_ENABLED"
    SERVICE_RESTARTED = "SERVICE_RESTARTED"
    OFFLINE_QUEUE_BACKLOG = "OFFLINE_QUEUE_BACKLOG"


class TrackingEvent(UUIDPrimaryKeyMixin, Base):
    """Device-reported tracking status changes (permission, GPS, service)."""

    __tablename__ = "tracking_events"

    shift_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shifts.id"))
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    client_event_id: Mapped[uuid.UUID]
    event_type: Mapped[TrackingEventType] = mapped_column(
        enum_column_type(TrackingEventType, "tracking_event_type")
    )
    occurred_at: Mapped[datetime]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("uq_tracking_events_driver_client", "driver_id", "client_event_id", unique=True),
        Index("ix_tracking_events_shift", "shift_id", "occurred_at"),
    )


class GpsUploadBatch(UUIDPrimaryKeyMixin, Base):
    """One upload request from a device (diagnostics + batch-level idempotency)."""

    __tablename__ = "gps_upload_batches"

    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id"))
    client_batch_id: Mapped[uuid.UUID]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    point_count: Mapped[int] = mapped_column(Integer)
    accepted: Mapped[int] = mapped_column(Integer)
    duplicates: Mapped[int] = mapped_column(Integer)
    rejected: Mapped[int] = mapped_column(Integer)
    app_version: Mapped[str | None] = mapped_column(String(40))
    battery_level: Mapped[int | None] = mapped_column(Integer)
    pending_points: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        Index("uq_gps_batches_driver_client", "driver_id", "client_batch_id", unique=True),
    )
