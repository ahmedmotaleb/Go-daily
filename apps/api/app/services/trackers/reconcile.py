"""Phone GPS vs vehicle tracker (U06).

Ready for when a tracker is fitted (U05); until then every comparison says
there is no tracker data. Nothing is inferred when one side is missing:

- per shift: the phone's VALID points are paired with the tracker position
  nearest in time (within ALIGN_SECONDS); the distance between each pair,
  both path lengths, and windows where the vehicle moved while the phone
  stayed still;
- per vehicle and day: tracker movement while no shift was running on it.

Everything is a fact to check («مراجعة مطلوبة»), not a finding: a phone in
a pocket, a tracker's own error or a missing binding can all explain it.
"""

from __future__ import annotations

import bisect
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.geo import haversine_m
from app.core.time import local_day_bounds_utc
from app.models.shift import Shift, ShiftStatus
from app.models.trackers import TrackerLocation
from app.services import tracking
from app.services.track_analysis import TrackPoint, recorded_distance_m

ALIGN_SECONDS = 60
# A pair farther apart than this is a discrepancy (both sides have their own error).
DISCREPANCY_M = 250
WINDOW = timedelta(minutes=5)
# In one window: the vehicle covered this much while the phone moved less than PHONE_STILL_M.
VEHICLE_MOVED_M = 500
PHONE_STILL_M = 50
# Movement outside shifts: positions this far apart within the gap tolerance.
MOVING_M = 200
MARGIN = timedelta(minutes=30)


@dataclass
class Window:
    start: datetime
    end: datetime
    vehicle_m: float
    phone_m: float


@dataclass
class ShiftComparison:
    shift_id: uuid.UUID
    status: str  # NO_TRACKER_DATA | NO_PHONE_DATA | COMPARED
    message: str
    phone_points: int = 0
    tracker_points: int = 0
    pairs: int = 0
    median_distance_m: float | None = None
    max_distance_m: float | None = None
    discrepancies: int = 0
    phone_distance_km: float | None = None
    tracker_distance_km: float | None = None
    phone_still_vehicle_moving: list[Window] = field(default_factory=list)


def _tracker(
    db: Session, vehicle_id: uuid.UUID, start: datetime, end: datetime
) -> list[TrackPoint]:
    return [
        TrackPoint(r.recorded_at, r.latitude, r.longitude, None, r.speed_mps)
        for r in db.scalars(
            select(TrackerLocation)
            .where(
                TrackerLocation.vehicle_id == vehicle_id,
                TrackerLocation.recorded_at >= start,
                TrackerLocation.recorded_at <= end,
            )
            .order_by(TrackerLocation.recorded_at)
        ).all()
    ]


def _nearest(track: list[TrackPoint], times: list[datetime], at: datetime) -> TrackPoint | None:
    i = bisect.bisect_left(times, at)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(track):
            gap = abs((track[j].recorded_at - at).total_seconds())
            if gap <= ALIGN_SECONDS and (
                best is None or gap < abs((best.recorded_at - at).total_seconds())
            ):
                best = track[j]
    return best


def _windows(phone: list[TrackPoint], vehicle: list[TrackPoint], max_gap: int) -> list[Window]:
    """Windows where the vehicle clearly moved and the phone, reporting, did not."""
    if not phone or not vehicle:
        return []
    out = []
    start = min(phone[0].recorded_at, vehicle[0].recorded_at)
    end = max(phone[-1].recorded_at, vehicle[-1].recorded_at)
    cursor = start
    while cursor < end:
        upto = cursor + WINDOW
        v = [p for p in vehicle if cursor <= p.recorded_at < upto]
        ph = [p for p in phone if cursor <= p.recorded_at < upto]
        if len(v) >= 2 and len(ph) >= 2:
            vm = recorded_distance_m(v, max_gap_seconds=max_gap)
            pm = recorded_distance_m(ph, max_gap_seconds=max_gap)
            if vm >= VEHICLE_MOVED_M and pm < PHONE_STILL_M:
                out.append(Window(cursor, upto, round(vm), round(pm)))
        cursor = upto
    return out


def compare_shift(db: Session, shift: Shift) -> ShiftComparison:
    settings = get_settings()
    started = shift.started_at
    if started is None:  # a planned shift that never started
        return ShiftComparison(shift.id, "NO_PHONE_DATA", "الوردية لم تبدأ")
    end = shift.ended_at or started + timedelta(hours=24)
    vehicle = _tracker(db, shift.vehicle_id, started - MARGIN, end + MARGIN)
    phone = tracking.valid_tracks(db, [shift.id])[shift.id]
    result = ShiftComparison(
        shift_id=shift.id,
        status="COMPARED",
        message="",
        phone_points=len(phone),
        tracker_points=len(vehicle),
    )
    if not vehicle:
        result.status = "NO_TRACKER_DATA"
        result.message = "لا توجد بيانات جهاز تتبع للمركبة في هذه الوردية"
        return result
    if not phone:
        result.status = "NO_PHONE_DATA"
        result.message = "لا توجد نقاط موقع صالحة من الهاتف في هذه الوردية"
        return result
    in_shift = [p for p in vehicle if started <= p.recorded_at <= end]
    times = [p.recorded_at for p in vehicle]
    distances = []
    for p in phone:
        match = _nearest(vehicle, times, p.recorded_at)
        if match is not None:
            distances.append(haversine_m(p.latitude, p.longitude, match.latitude, match.longitude))
    result.pairs = len(distances)
    if distances:
        result.median_distance_m = round(statistics.median(distances), 1)
        result.max_distance_m = round(max(distances), 1)
        result.discrepancies = sum(1 for d in distances if d > DISCREPANCY_M)
    gap = settings.gps_gap_seconds
    result.phone_distance_km = round(recorded_distance_m(phone, max_gap_seconds=gap) / 1000, 2)
    result.tracker_distance_km = round(recorded_distance_m(in_shift, max_gap_seconds=gap) / 1000, 2)
    result.phone_still_vehicle_moving = _windows(phone, in_shift, gap)
    result.message = (
        "فروق بين الهاتف وجهاز المركبة — مراجعة مطلوبة"
        if result.discrepancies or result.phone_still_vehicle_moving
        else "مسار الهاتف يطابق جهاز المركبة"
    )
    return result


@dataclass
class Movement:
    start: datetime
    end: datetime
    distance_km: float
    positions: int


@dataclass
class VehicleDay:
    vehicle_id: uuid.UUID
    day: date
    status: str  # NO_TRACKER_DATA | CHECKED
    tracker_points: int
    outside_shift: list[Movement] = field(default_factory=list)


def movement_outside_shifts(db: Session, vehicle_id: uuid.UUID, day: date) -> VehicleDay:
    """Tracker movement on a local day while no shift was running on the vehicle."""
    start, end = local_day_bounds_utc(day)
    vehicle = _tracker(db, vehicle_id, start, end)
    out = VehicleDay(vehicle_id, day, "CHECKED" if vehicle else "NO_TRACKER_DATA", len(vehicle))
    if not vehicle:
        return out
    shifts = db.execute(
        select(Shift.started_at, Shift.ended_at).where(
            Shift.vehicle_id == vehicle_id,
            Shift.status.in_((ShiftStatus.ACTIVE, ShiftStatus.COMPLETED)),
            Shift.started_at < end,
            or_(Shift.ended_at.is_(None), Shift.ended_at > start),
        )
    ).all()

    def in_shift(at: datetime) -> bool:
        return any(s is not None and s <= at <= (e or end) for s, e in shifts)

    gap = get_settings().gps_gap_seconds
    run: list[TrackPoint] = []

    def close() -> None:
        if len(run) >= 2:
            meters = recorded_distance_m(run, max_gap_seconds=gap)
            if meters >= MOVING_M:
                out.outside_shift.append(
                    Movement(
                        run[0].recorded_at, run[-1].recorded_at, round(meters / 1000, 2), len(run)
                    )
                )
        run.clear()

    for p in vehicle:
        if in_shift(p.recorded_at) or (
            run and (p.recorded_at - run[-1].recorded_at).total_seconds() > gap
        ):
            close()
        if not in_shift(p.recorded_at):
            run.append(p)
    close()
    return out


__all__ = ["ShiftComparison", "VehicleDay", "compare_shift", "movement_outside_shifts"]
