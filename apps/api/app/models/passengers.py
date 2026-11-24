"""Passenger counts (U11).

Optional, and only ever recorded: by the driver, a supervisor, or later by a
ticketing system or an on-board counter once one is approved. Each count
says where it came from and how sure it is. A count is never inferred from
GPS or from revenue. Counts are never edited; a wrong one is voided with a
reason and re-entered.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin, enum_column_type
from app.models.route_events import LegDirection


class CountSource(StrEnum):
    DRIVER = "DRIVER"  # reported by the driver
    SUPERVISOR = "SUPERVISOR"  # counted by a supervisor on site
    TICKETING = "TICKETING"  # reserved: an approved ticketing integration
    HARDWARE = "HARDWARE"  # reserved: an approved on-board counter


class CountConfidence(StrEnum):
    COUNTED = "COUNTED"  # each passenger counted
    ESTIMATED = "ESTIMATED"  # an approximate figure


class PassengerCount(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "passenger_counts"

    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("operation_sessions.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    route_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("route_definitions.id"))
    direction: Mapped[LegDirection | None] = mapped_column(
        enum_column_type(LegDirection, "leg_direction")
    )
    counted_at: Mapped[datetime]
    passengers: Mapped[int] = mapped_column(Integer)
    source: Mapped[CountSource] = mapped_column(enum_column_type(CountSource, "count_source"))
    confidence: Mapped[CountConfidence] = mapped_column(
        enum_column_type(CountConfidence, "count_confidence")
    )
    note: Mapped[str | None] = mapped_column(String(300))
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None]
    void_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("passengers BETWEEN 0 AND 200", name="passengers_range"),
        Index("ix_passenger_counts_shift", "shift_id", "counted_at"),
        Index("ix_passenger_counts_route", "route_id", "counted_at"),
    )
