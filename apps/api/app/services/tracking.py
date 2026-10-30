"""GPS ingestion and tracking queries."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationFailed
from app.core.geo import haversine_m
from app.core.time import utcnow
from app.models.driver import Driver
from app.models.shift import OperationSession, SessionStatus, Shift, ShiftStatus
from app.models.tracking import (
    GpsPoint,
    GpsUploadBatch,
    PointQuality,
    TrackingEvent,
    VehicleLatestPosition,
)
from app.schemas.tracking import (
    DriverTrackingStatus,
    GapOut,
    LivePosition,
    PointBatchIn,
    PointBatchResult,
    RejectedPoint,
    ShiftTrackOut,
    StopOut,
    TimelineItem,
    TrackingEventsIn,
    TrackingEventsResult,
    TrackingState,
    TrackPointOut,
)
from app.services import route_events, school_runs
from app.services.track_analysis import TrackPoint, find_gaps, find_stops, recorded_distance_m

WINDOW_TOLERANCE = timedelta(minutes=2)
EVENT_LABELS_AR = {
    "TRACKING_STARTED": "بدء التتبع على الجهاز",
    "TRACKING_STOPPED": "إيقاف التتبع على الجهاز",
    "PERMISSION_GRANTED": "تم منح إذن الموقع",
    "PERMISSION_DENIED": "رفض إذن الموقع",
    "BACKGROUND_PERMISSION_DENIED": "رفض إذن الموقع في الخلفية",
    "LOCATION_DISABLED": "خدمة الموقع مغلقة",
    "LOCATION_ENABLED": "تم تشغيل خدمة الموقع",
    "GPS_SIGNAL_LOST": "فقد إشارة GPS",
    "GPS_SIGNAL_RESTORED": "عودة إشارة GPS",
    "BATTERY_OPTIMIZATION_ENABLED": "تحسين البطارية مفعل",
    "SERVICE_RESTARTED": "إعادة تشغيل خدمة التتبع",
    "OFFLINE_QUEUE_BACKLOG": "نقاط بانتظار الإرسال",
}


def _own_tracked_shift(db: Session, driver: Driver, shift_id: uuid.UUID) -> Shift:
    shift = db.get(Shift, shift_id)
    if shift is None or shift.driver_id != driver.id:
        raise NotFoundError("الوردية غير موجودة")
    if shift.started_at is None:
        raise ValidationFailed("الوردية لم تبدأ", code="shift_not_started")
    return shift


def _quality(point: Any, prev: tuple[datetime, float, float] | None) -> PointQuality:
    settings = get_settings()
    if point.is_mock:
        return PointQuality.MOCK
    if point.accuracy_m is not None and point.accuracy_m > settings.gps_max_accuracy_m:
        return PointQuality.LOW_ACCURACY
    if prev is not None:
        seconds = (point.recorded_at - prev[0]).total_seconds()
        if seconds > 0:
            dist = haversine_m(prev[1], prev[2], point.latitude, point.longitude)
            if dist / seconds * 3.6 > settings.gps_max_speed_kmh:
                return PointQuality.IMPLAUSIBLE_SPEED
    return PointQuality.VALID


def _partition(
    data: PointBatchIn, window_start: datetime, window_end: datetime, now: datetime
) -> tuple[list[RejectedPoint], list[Any]]:
    """Split points into rejected (future / outside the shift) and storable candidates."""
    rejected: list[RejectedPoint] = []
    candidates = []
    for p in data.points:
        if p.recorded_at > now + WINDOW_TOLERANCE:
            rejected.append(
                RejectedPoint(client_point_id=p.client_point_id, reason="future_timestamp")
            )
        elif not (window_start <= p.recorded_at <= window_end):
            # Never store locations from outside the work shift.
            rejected.append(
                RejectedPoint(client_point_id=p.client_point_id, reason="outside_shift")
            )
        else:
            candidates.append(p)
    candidates.sort(key=lambda p: p.recorded_at)
    return rejected, candidates


def _refresh_derived(db: Session, shift_id: uuid.UUID, inserted_rows: list[dict[str, Any]]) -> None:
    """Re-run geofence detection (and school-run evaluation) for affected sessions."""
    if not inserted_rows:
        return
    affected = route_events.sessions_for_points(
        db,
        shift_id,
        min(r["recorded_at"] for r in inserted_rows),
        max(r["recorded_at"] for r in inserted_rows),
    )
    route_events.detect_safely(db, affected)
    for session_id in affected:
        session = db.get(OperationSession, session_id)
        if session is not None and session.ended_at is not None:
            school_runs.on_session_closed(db, session)


def ingest_points(db: Session, *, driver: Driver, data: PointBatchIn) -> PointBatchResult:
    existing = db.scalar(
        select(GpsUploadBatch).where(
            GpsUploadBatch.driver_id == driver.id, GpsUploadBatch.client_batch_id == data.batch_id
        )
    )
    if existing is not None:
        return PointBatchResult(
            batch_id=data.batch_id,
            accepted=existing.accepted,
            duplicates=existing.duplicates,
            rejected=[],
            replayed=True,
        )

    shift = _own_tracked_shift(db, driver, data.shift_id)
    assert shift.started_at is not None  # noqa: S101
    now = utcnow()
    window_start = shift.started_at - WINDOW_TOLERANCE
    window_end = (shift.ended_at or now) + WINDOW_TOLERANCE

    rejected, candidates = _partition(data, window_start, window_end, now)

    prev: tuple[datetime, float, float] | None = None
    if candidates:
        last_valid = db.execute(
            select(GpsPoint.recorded_at, GpsPoint.latitude, GpsPoint.longitude)
            .where(
                GpsPoint.shift_id == shift.id,
                GpsPoint.quality == PointQuality.VALID,
                GpsPoint.recorded_at < candidates[0].recorded_at,
            )
            .order_by(GpsPoint.recorded_at.desc())
            .limit(1)
        ).first()
        if last_valid is not None:
            prev = (last_valid[0], last_valid[1], last_valid[2])

    rows: list[dict[str, Any]] = []
    for p in candidates:
        quality = _quality(p, prev)
        if quality is PointQuality.VALID:
            prev = (p.recorded_at, p.latitude, p.longitude)
        rows.append(
            {
                "id": uuid.uuid4(),
                "shift_id": shift.id,
                "driver_id": driver.id,
                "vehicle_id": shift.vehicle_id,
                "client_point_id": p.client_point_id,
                "batch_id": data.batch_id,
                "recorded_at": p.recorded_at,
                "received_at": now,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "accuracy_m": p.accuracy_m,
                "speed_mps": p.speed_mps,
                "heading_deg": p.heading_deg,
                "altitude_m": p.altitude_m,
                "source": p.source,
                "is_mock": p.is_mock,
                "quality": quality,
            }
        )

    inserted_ids: set[uuid.UUID] = set()
    if rows:
        result = db.execute(
            insert(GpsPoint)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["shift_id", "client_point_id"])
            .returning(GpsPoint.id)
        )
        inserted_ids = {r[0] for r in result}

    _refresh_derived(db, shift.id, [r for r in rows if r["id"] in inserted_ids])

    newest = next(
        (
            r
            for r in reversed(rows)
            if r["id"] in inserted_ids
            and r["quality"] in (PointQuality.VALID, PointQuality.LOW_ACCURACY)
        ),
        None,
    )
    if newest is not None:
        _update_latest(db, newest)

    accepted = len(inserted_ids)
    batch = GpsUploadBatch(
        driver_id=driver.id,
        shift_id=shift.id,
        client_batch_id=data.batch_id,
        point_count=len(data.points),
        accepted=accepted,
        duplicates=len(rows) - accepted,
        rejected=len(rejected),
        app_version=data.device.app_version if data.device else None,
        battery_level=data.device.battery_level if data.device else None,
        pending_points=data.device.pending_points if data.device else None,
    )
    db.add(batch)
    db.commit()
    return PointBatchResult(
        batch_id=data.batch_id,
        accepted=accepted,
        duplicates=len(rows) - accepted,
        rejected=rejected,
    )


def _update_latest(db: Session, row: dict[str, Any]) -> None:
    values = {
        "vehicle_id": row["vehicle_id"],
        "shift_id": row["shift_id"],
        "driver_id": row["driver_id"],
        "point_id": row["id"],
        "recorded_at": row["recorded_at"],
        "received_at": row["received_at"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "accuracy_m": row["accuracy_m"],
        "speed_mps": row["speed_mps"],
        "heading_deg": row["heading_deg"],
    }
    stmt = insert(VehicleLatestPosition).values(values)
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["vehicle_id"],
            set_={k: stmt.excluded[k] for k in values if k != "vehicle_id"},
            where=VehicleLatestPosition.recorded_at < stmt.excluded.recorded_at,
        )
    )


def record_events(db: Session, *, driver: Driver, data: TrackingEventsIn) -> TrackingEventsResult:
    rows = []
    for e in data.events:
        if e.shift_id is not None:
            _own_tracked_shift(db, driver, e.shift_id)
        rows.append(
            {
                "id": uuid.uuid4(),
                "driver_id": driver.id,
                "shift_id": e.shift_id,
                "client_event_id": e.client_event_id,
                "event_type": e.event_type,
                "occurred_at": e.occurred_at,
                "details": e.details,
            }
        )
    result = db.execute(
        insert(TrackingEvent)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["driver_id", "client_event_id"])
        .returning(TrackingEvent.id)
    )
    accepted = len(list(result))
    db.commit()
    return TrackingEventsResult(accepted=accepted, duplicates=len(rows) - accepted)


def tracking_state(last_received: datetime | None, *, in_shift: bool) -> TrackingState:
    if not in_shift:
        return "NOT_IN_SHIFT"
    if last_received is None:
        return "OFFLINE"
    settings = get_settings()
    age = (utcnow() - last_received).total_seconds()
    if age <= settings.tracking_online_seconds:
        return "ONLINE"
    if age <= settings.tracking_stale_seconds:
        return "STALE"
    return "OFFLINE"


def driver_status(db: Session, *, driver: Driver) -> DriverTrackingStatus:
    shift = db.scalar(
        select(Shift).where(Shift.driver_id == driver.id, Shift.status == ShiftStatus.ACTIVE)
    )
    last_point = (
        db.execute(
            select(GpsPoint.recorded_at, GpsPoint.received_at)
            .where(GpsPoint.shift_id == shift.id)
            .order_by(GpsPoint.received_at.desc())
            .limit(1)
        ).first()
        if shift
        else None
    )
    last_event = db.scalar(
        select(TrackingEvent)
        .where(TrackingEvent.driver_id == driver.id)
        .order_by(TrackingEvent.occurred_at.desc())
        .limit(1)
    )
    return DriverTrackingStatus(
        shift_id=shift.id if shift else None,
        state=tracking_state(last_point[1] if last_point else None, in_shift=shift is not None),
        last_point_recorded_at=last_point[0] if last_point else None,
        last_point_received_at=last_point[1] if last_point else None,
        last_event=last_event.event_type if last_event else None,
        last_event_at=last_event.occurred_at if last_event else None,
    )


def live_positions(db: Session) -> list[LivePosition]:
    shifts = db.scalars(select(Shift).where(Shift.status == ShiftStatus.ACTIVE)).all()
    latest = {
        p.vehicle_id: p
        for p in db.scalars(
            select(VehicleLatestPosition).where(
                VehicleLatestPosition.vehicle_id.in_([s.vehicle_id for s in shifts])
            )
        ).all()
    }
    last_events: dict[uuid.UUID, TrackingEvent] = {}
    if shifts:
        for ev in db.scalars(
            select(TrackingEvent)
            .where(TrackingEvent.shift_id.in_([s.id for s in shifts]))
            .order_by(TrackingEvent.occurred_at)
        ).all():
            if ev.shift_id is not None:
                last_events[ev.shift_id] = ev
    out = []
    for s in shifts:
        pos = latest.get(s.vehicle_id)
        if pos is not None and pos.shift_id != s.id:
            pos = None  # position belongs to an earlier shift
        session = next((x for x in s.sessions if x.status is SessionStatus.ACTIVE), None)
        last_ev = last_events.get(s.id)
        out.append(
            LivePosition(
                vehicle_id=s.vehicle_id,
                vehicle_code=s.vehicle.internal_code,
                plate_number=s.vehicle.plate_number,
                driver_id=s.driver_id,
                driver_name=s.driver.full_name,
                shift_id=s.id,
                state=tracking_state(pos.received_at if pos else None, in_shift=True),
                latitude=pos.latitude if pos else None,
                longitude=pos.longitude if pos else None,
                accuracy_m=pos.accuracy_m if pos else None,
                speed_kmh=round(pos.speed_mps * 3.6, 1)
                if pos and pos.speed_mps is not None
                else None,
                heading_deg=pos.heading_deg if pos else None,
                last_recorded_at=pos.recorded_at if pos else None,
                last_received_at=pos.received_at if pos else None,
                current_operation=(
                    session.operation_type.name_ar
                    + (f" — {session.route.name}" if session.route else "")
                    if session
                    else None
                ),
                last_event=last_ev.event_type if last_ev else None,
            )
        )
    return out


def shift_points(db: Session, shift_id: uuid.UUID) -> list[GpsPoint]:
    return list(
        db.scalars(
            select(GpsPoint).where(GpsPoint.shift_id == shift_id).order_by(GpsPoint.recorded_at)
        ).all()
    )


def valid_track(points: list[GpsPoint]) -> list[TrackPoint]:
    return [
        TrackPoint(p.recorded_at, p.latitude, p.longitude, p.accuracy_m, p.speed_mps)
        for p in points
        if p.quality is PointQuality.VALID
    ]


def shift_track(db: Session, shift_id: uuid.UUID) -> ShiftTrackOut:
    settings = get_settings()
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise NotFoundError("الوردية غير موجودة")
    points = shift_points(db, shift.id)
    track = valid_track(points)
    counts: dict[str, int] = {q.value: 0 for q in PointQuality}
    for p in points:
        counts[p.quality.value] += 1

    window_start = shift.started_at
    window_end = shift.ended_at or (utcnow() if shift.status is ShiftStatus.ACTIVE else None)
    gaps = (
        find_gaps(
            track,
            window_start=window_start,
            window_end=window_end,
            max_gap_seconds=settings.gps_gap_seconds,
        )
        if window_start and window_end
        else []
    )
    stops = find_stops(
        track, radius_m=settings.gps_stop_radius_m, min_seconds=settings.gps_stop_min_seconds
    )

    timeline: list[TimelineItem] = []
    if shift.started_at:
        timeline.append(
            TimelineItem(at=shift.started_at, kind="SHIFT_STARTED", label="بدء الوردية")
        )
    for s in shift.sessions:
        name = s.operation_type.name_ar + (f" — {s.route.name}" if s.route else "")
        timeline.append(
            TimelineItem(
                at=s.started_at, kind="SESSION_STARTED", label=f"بدء {name}", until=s.ended_at
            )
        )
        if s.ended_at:
            timeline.append(
                TimelineItem(at=s.ended_at, kind="SESSION_ENDED", label=f"انتهاء {name}")
            )
    for st in stops:
        timeline.append(
            TimelineItem(
                at=st.start, kind="STOP", label=f"توقف {st.seconds // 60} دقيقة", until=st.end
            )
        )
    for g in gaps:
        timeline.append(
            TimelineItem(
                at=g.start,
                kind="GAP",
                label=f"انقطاع بيانات GPS لمدة {g.seconds // 60} دقيقة",
                until=g.end,
            )
        )
    for ev in db.scalars(
        select(TrackingEvent)
        .where(TrackingEvent.shift_id == shift.id)
        .order_by(TrackingEvent.occurred_at)
    ).all():
        timeline.append(
            TimelineItem(
                at=ev.occurred_at,
                kind="DEVICE_EVENT",
                label=EVENT_LABELS_AR.get(ev.event_type.value, ev.event_type.value),
            )
        )
    if shift.ended_at:
        timeline.append(TimelineItem(at=shift.ended_at, kind="SHIFT_ENDED", label="انتهاء الوردية"))
    timeline.sort(key=lambda t: t.at)

    return ShiftTrackOut(
        shift_id=shift.id,
        vehicle_id=shift.vehicle_id,
        driver_id=shift.driver_id,
        window_start=window_start,
        window_end=window_end,
        points=[
            TrackPointOut(
                t=p.recorded_at,
                lat=p.latitude,
                lng=p.longitude,
                acc=p.accuracy_m,
                spd=p.speed_mps,
                q=p.quality,
            )
            for p in points
        ],
        counts=counts,
        gps_distance_km=round(
            recorded_distance_m(track, max_gap_seconds=settings.gps_gap_seconds) / 1000, 2
        ),
        odometer_distance_km=shift.odometer_distance_km,
        gaps=[
            GapOut(start=g.start, end=g.end, seconds=g.seconds, displacement_m=g.displacement_m)
            for g in gaps
        ],
        stops=[
            StopOut(
                start=s.start,
                end=s.end,
                seconds=s.seconds,
                latitude=s.latitude,
                longitude=s.longitude,
            )
            for s in stops
        ],
        timeline=timeline,
    )


def prune_old_points(db: Session, *, older_than_days: int) -> int:
    """Delete raw points of finished shifts older than the retention period."""
    cutoff = utcnow() - timedelta(days=older_than_days)
    finished = select(Shift.id).where(
        Shift.status.in_([ShiftStatus.COMPLETED, ShiftStatus.CANCELLED]), Shift.ended_at < cutoff
    )
    db.execute(delete(VehicleLatestPosition).where(VehicleLatestPosition.shift_id.in_(finished)))
    result = db.execute(delete(GpsPoint).where(GpsPoint.shift_id.in_(finished)))
    db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
