"""GPS tracking endpoints: device ingestion (driver) and live/replay (staff)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentDriver, DbSession, require_permissions
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.tracking import (
    DriverTrackingStatus,
    LivePosition,
    PointBatchIn,
    PointBatchResult,
    ShiftTrackOut,
    TrackingEventsIn,
    TrackingEventsResult,
)
from app.services import tracking as tracking_service

router = APIRouter(tags=["tracking"])

TrackingReader = Annotated[User, Depends(require_permissions(Permission.TRACKING_READ))]


@router.post("/driver/tracking/points", response_model=PointBatchResult)
def upload_points(body: PointBatchIn, driver: CurrentDriver, db: DbSession) -> PointBatchResult:
    """Batch upload from the device's offline queue. Safe to retry (batch and point IDs)."""
    return tracking_service.ingest_points(db, driver=driver, data=body)


@router.post("/driver/tracking/events", response_model=TrackingEventsResult)
def upload_events(
    body: TrackingEventsIn, driver: CurrentDriver, db: DbSession
) -> TrackingEventsResult:
    return tracking_service.record_events(db, driver=driver, data=body)


@router.get("/driver/tracking/status", response_model=DriverTrackingStatus)
def driver_tracking_status(driver: CurrentDriver, db: DbSession) -> DriverTrackingStatus:
    return tracking_service.driver_status(db, driver=driver)


@router.get("/tracking/live", response_model=list[LivePosition])
def live(_: TrackingReader, db: DbSession) -> list[LivePosition]:
    return tracking_service.live_positions(db)


@router.get("/shifts/{shift_id}/track", response_model=ShiftTrackOut)
def shift_track(shift_id: uuid.UUID, _: TrackingReader, db: DbSession) -> ShiftTrackOut:
    return tracking_service.shift_track(db, shift_id)
