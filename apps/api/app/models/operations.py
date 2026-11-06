"""Operation types and route definitions.

Operation types are an extensible lookup. Each type has a `kind` naming the
built-in behaviour it uses (route loops, school duty, ride-hailing
statements, ...), so new types can be added without code changes and
business logic never depends on a specific university, school or station.
"""

from __future__ import annotations

import uuid
from datetime import time
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column_type


class OperationKind(StrEnum):
    RIDE_HAILING = "RIDE_HAILING"  # نقل ذكي
    FIXED_ROUTE = "FIXED_ROUTE"  # خط ثابت
    SCHOOL_ROUTE = "SCHOOL_ROUTE"  # دورة مدرسة
    PRIVATE_TRIP = "PRIVATE_TRIP"  # رحلة خاصة
    EMPLOYEE_TRANSPORT = "EMPLOYEE_TRANSPORT"  # نقل موظفين
    OTHER = "OTHER"


ROUTE_BASED_KINDS = frozenset(
    {OperationKind.FIXED_ROUTE, OperationKind.SCHOOL_ROUTE, OperationKind.EMPLOYEE_TRANSPORT}
)


class OperationType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "operation_types"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    kind: Mapped[OperationKind] = mapped_column(enum_column_type(OperationKind, "operation_kind"))
    name_ar: Mapped[str] = mapped_column(String(80))
    name_en: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(default=0, server_default=text("0"))

    @property
    def uses_routes(self) -> bool:
        return self.kind in ROUTE_BASED_KINDS


class TripPattern(StrEnum):
    ONE_WAY = "ONE_WAY"  # اتجاه واحد
    ROUND_TRIP = "ROUND_TRIP"  # ذهاب وعودة متكرر (مثل موقف ⇄ جامعة)


class RouteDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "route_definitions"

    name: Mapped[str] = mapped_column(String(120))
    operation_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operation_types.id"))
    trip_pattern: Mapped[TripPattern] = mapped_column(
        enum_column_type(TripPattern, "trip_pattern"), default=TripPattern.ROUND_TRIP
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    expected_distance_km: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    expected_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    window_start: Mapped[time | None]
    window_end: Mapped[time | None]
    # ISO weekdays (1=Monday .. 7=Sunday); empty/NULL means every day.
    operating_days: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    notes: Mapped[str | None] = mapped_column(Text)

    operation_type: Mapped[OperationType] = relationship(lazy="joined")
    stops: Mapped[list[RouteStop]] = relationship(
        back_populates="route", order_by="RouteStop.sequence", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "expected_distance_km IS NULL OR expected_distance_km > 0", name="distance_positive"
        ),
        CheckConstraint(
            "expected_duration_minutes IS NULL OR expected_duration_minutes > 0",
            name="duration_positive",
        ),
        Index("ix_route_definitions_operation_type", "operation_type_id"),
    )


class StopKind(StrEnum):
    ORIGIN = "ORIGIN"
    INTERMEDIATE = "INTERMEDIATE"
    DESTINATION = "DESTINATION"


class RouteStop(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ordered stop of a route. Coordinates + radius become geofences (Task 12)."""

    __tablename__ = "route_stops"

    route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("route_definitions.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[StopKind] = mapped_column(enum_column_type(StopKind, "stop_kind"))
    name: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    radius_m: Mapped[int] = mapped_column(Integer, default=150, server_default=text("150"))

    route: Mapped[RouteDefinition] = relationship(back_populates="stops")

    __table_args__ = (
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180", name="longitude_range"
        ),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="coordinates_paired"),
        CheckConstraint("radius_m BETWEEN 20 AND 5000", name="radius_range"),
        Index("uq_route_stops_route_sequence", "route_id", "sequence", unique=True),
    )
