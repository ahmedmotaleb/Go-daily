"""Route event and school run schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

from app.models.route_events import (
    EventSource,
    EventStatus,
    LegDirection,
    RouteEventType,
    SchoolRunStatus,
)
from app.schemas.shift import PersonRef, RouteRef, VehicleRef

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class RouteEventOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    stop_id: uuid.UUID | None
    stop_name: str | None
    event_type: RouteEventType
    direction: LegDirection | None
    occurred_at: datetime
    sequence_no: int | None
    source: EventSource
    status: EventStatus
    reason: str | None
    void_reason: str | None


class ManualRouteEventIn(BaseModel):
    event_type: Literal["LOOP_COMPLETED", "LEG_COMPLETED", "REACHED_ORIGIN", "REACHED_DESTINATION"]
    occurred_at: AwareDatetime
    direction: LegDirection | None = None
    reason: Reason


class VoidIn(BaseModel):
    reason: Reason


class RecomputeOut(BaseModel):
    events: int
    voided: int = 0


class SchoolRunEvidence(BaseModel):
    reached_origin: bool
    reached_destination: bool
    route_events: int


class SchoolRunOut(BaseModel):
    id: uuid.UUID
    route: RouteRef
    service_date: date
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    vehicle: VehicleRef
    driver: PersonRef | None
    status: SchoolRunStatus
    session_id: uuid.UUID | None
    shift_id: uuid.UUID | None
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    label: str | None
    notes: str | None
    status_reason: str | None
    evidence: SchoolRunEvidence


class SchoolRunGenerate(BaseModel):
    route_id: uuid.UUID
    date_from: date
    date_to: date
    start_time: time
    end_time: time
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID | None = None
    label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    weekdays: list[Annotated[int, Field(ge=1, le=7)]] | None = None


class SchoolRunGenerateOut(BaseModel):
    created: int


class SchoolRunUpdate(BaseModel):
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None


class SchoolRunStatusIn(BaseModel):
    status: Literal["SCHEDULED", "COMPLETED", "COMPLETED_UNVERIFIED", "MISSED", "CANCELLED"]
    reason: Reason
