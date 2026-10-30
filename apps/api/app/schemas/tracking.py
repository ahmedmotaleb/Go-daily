"""GPS tracking schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.models.tracking import PointQuality, PointSource, TrackingEventType


class PointIn(BaseModel):
    client_point_id: uuid.UUID
    recorded_at: AwareDatetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0, le=100_000)
    speed_mps: float | None = Field(default=None, ge=0, le=200)
    heading_deg: float | None = Field(default=None, ge=0, le=360)
    altitude_m: float | None = Field(default=None, ge=-500, le=10_000)
    source: PointSource = PointSource.UNKNOWN
    is_mock: bool = False


class DeviceInfo(BaseModel):
    app_version: str | None = Field(default=None, max_length=40)
    battery_level: int | None = Field(default=None, ge=0, le=100)
    pending_points: int | None = Field(default=None, ge=0)


class PointBatchIn(BaseModel):
    batch_id: uuid.UUID
    shift_id: uuid.UUID
    points: list[PointIn] = Field(min_length=1, max_length=500)
    device: DeviceInfo | None = None


class RejectedPoint(BaseModel):
    client_point_id: uuid.UUID
    reason: Literal["outside_shift", "future_timestamp"]


class PointBatchResult(BaseModel):
    batch_id: uuid.UUID
    accepted: int
    duplicates: int
    rejected: list[RejectedPoint]
    replayed: bool = False


class TrackingEventIn(BaseModel):
    client_event_id: uuid.UUID
    event_type: TrackingEventType
    occurred_at: AwareDatetime
    shift_id: uuid.UUID | None = None
    details: dict[str, Any] | None = None


class TrackingEventsIn(BaseModel):
    events: list[TrackingEventIn] = Field(min_length=1, max_length=200)


class TrackingEventsResult(BaseModel):
    accepted: int
    duplicates: int


TrackingState = Literal["ONLINE", "STALE", "OFFLINE", "NOT_IN_SHIFT"]


class DriverTrackingStatus(BaseModel):
    shift_id: uuid.UUID | None
    state: TrackingState
    last_point_recorded_at: datetime | None
    last_point_received_at: datetime | None
    last_event: TrackingEventType | None
    last_event_at: datetime | None


class LivePosition(BaseModel):
    vehicle_id: uuid.UUID
    vehicle_code: str
    plate_number: str
    driver_id: uuid.UUID
    driver_name: str
    shift_id: uuid.UUID
    state: TrackingState
    latitude: float | None
    longitude: float | None
    accuracy_m: float | None
    speed_kmh: float | None
    heading_deg: float | None
    last_recorded_at: datetime | None
    last_received_at: datetime | None
    current_operation: str | None
    last_event: TrackingEventType | None


class TrackPointOut(BaseModel):
    t: datetime
    lat: float
    lng: float
    acc: float | None
    spd: float | None
    q: PointQuality


class GapOut(BaseModel):
    start: datetime
    end: datetime
    seconds: int
    displacement_m: float | None


class StopOut(BaseModel):
    start: datetime
    end: datetime
    seconds: int
    latitude: float
    longitude: float


class TimelineItem(BaseModel):
    at: datetime
    kind: Literal[
        "SHIFT_STARTED",
        "SHIFT_ENDED",
        "SESSION_STARTED",
        "SESSION_ENDED",
        "STOP",
        "GAP",
        "DEVICE_EVENT",
    ]
    label: str
    until: datetime | None = None


class ShiftTrackOut(BaseModel):
    shift_id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID
    window_start: datetime | None
    window_end: datetime | None
    points: list[TrackPointOut]
    counts: dict[str, int]
    gps_distance_km: float
    odometer_distance_km: int | None
    gaps: list[GapOut]
    stops: list[StopOut]
    timeline: list[TimelineItem]
