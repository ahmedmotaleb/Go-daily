"""Hardware GPS trackers (U05): provider-neutral ingestion.

No tracker hardware or provider is in use yet. These tables let a future
provider's events be received, checked and stored without changing the rest
of the system:

- `tracker_devices`: a tracker known to the company (provider + its own id);
- `tracker_bindings`: which vehicle a tracker was fitted to, over time, so an
  event is always attributed to the vehicle it was in at that moment;
- `tracker_raw_events`: every event received, as sent, with its outcome
  (accepted or quarantined with a reason). The (provider, event id) pair is
  unique, so a resent event is never stored twice;
- `tracker_locations`: the normalised positions of accepted events.

A vehicle tracker is not the driver's phone: it reports the vehicle, not a
person, and its positions are never mixed into the phone track.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column_type
from app.models.fleet import Vehicle


class TrackerDevice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tracker_devices"

    provider: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(100))
    label: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_tracker_devices_ref"),)


class TrackerBinding(UUIDPrimaryKeyMixin, Base):
    """A tracker fitted to a vehicle from `starts_at` until `ends_at` (open = still fitted)."""

    __tablename__ = "tracker_bindings"

    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracker_devices.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime | None]
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    vehicle: Mapped[Vehicle] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="binding_range"),
        Index("ix_tracker_bindings_device", "device_id", "starts_at"),
    )


class RawEventStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    QUARANTINED = "QUARANTINED"  # kept with a reason; never used for analytics


class TrackerRawEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tracker_raw_events"

    provider: Mapped[str] = mapped_column(String(40))
    provider_event_id: Mapped[str] = mapped_column(String(120))
    device_external_id: Mapped[str | None] = mapped_column(String(100))
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[RawEventStatus] = mapped_column(
        enum_column_type(RawEventStatus, "tracker_event_status")
    )
    reason: Mapped[str | None] = mapped_column(String(40))
    reprocessed_at: Mapped[datetime | None]

    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_tracker_raw_events_ref"),
        Index("ix_tracker_raw_events_status", "status", "received_at"),
    )


class TrackerLocation(UUIDPrimaryKeyMixin, Base):
    """A normalised vehicle position from an accepted tracker event."""

    __tablename__ = "tracker_locations"

    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracker_devices.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    raw_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracker_raw_events.id"))
    recorded_at: Mapped[datetime]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    ignition_on: Mapped[bool | None]
    external_power: Mapped[bool | None]

    __table_args__ = (
        Index("ix_tracker_locations_vehicle", "vehicle_id", "recorded_at"),
        Index(
            "ix_tracker_locations_recorded_brin",
            "recorded_at",
            postgresql_using="brin",
        ),
    )
