"""Detection rules for operational exceptions (Task 20).

Each rule reads recorded data for a time window and returns candidates:
what happened, when, which vehicle/driver/shift/record, and the evidence
(the facts and thresholds that triggered it). Rules never fill in missing
data and never conclude intent: a candidate is "review needed" or
"unusual case", nothing more.

Scope keys let the engine tell "checked again and no longer found" apart
from "not checked this time" (see `RuleResult.scopes`).
"""

from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.config import Settings
from app.core.geo import haversine_m, point_to_polyline_m
from app.core.time import local_day_bounds_utc, local_today, to_local_date, utcnow, week_start
from app.models.attachment import Attachment
from app.models.exceptions import (
    ExceptionLabel,
    ExceptionSeverity,
    ExceptionStatus,
    OperationalException,
)
from app.models.finance import (
    Expense,
    FuelCategory,
    FuelTransaction,
    FuelType,
    PaidBy,
    RecordStatus,
)
from app.models.operations import RouteDefinition
from app.models.shift import SessionStatus, Shift, ShiftStatus
from app.models.tracking import (
    GpsPoint,
    GpsUploadBatch,
    PointQuality,
    TrackingEvent,
    TrackingEventType,
)
from app.services import expected_revenue, ride_hailing
from app.services import finance_common as fc
from app.services.odometer_reconciliation import ReconciliationStatus, reconcile
from app.services.track_analysis import TrackPoint, find_gaps, find_stops

LIVE = (RecordStatus.SUBMITTED, RecordStatus.APPROVED)

R = ExceptionLabel.REVIEW_REQUIRED
U = ExceptionLabel.UNUSUAL
LOW, MEDIUM, HIGH = ExceptionSeverity.LOW, ExceptionSeverity.MEDIUM, ExceptionSeverity.HIGH


@dataclass
class Candidate:
    rule_code: str
    severity: ExceptionSeverity
    summary: str
    evidence: dict[str, Any]
    occurred_at: datetime
    dedupe_key: str
    occurred_until: datetime | None = None
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None
    shift_id: uuid.UUID | None = None
    subject_type: str | None = None
    subject_id: uuid.UUID | None = None


@dataclass
class RuleResult:
    candidates: list[Candidate] = field(default_factory=list)
    # Dedupe keys this run was able to produce. An open exception whose key
    # is in scope but was not produced is marked "no longer detected".
    scopes: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class RuleInfo:
    code: str
    title_ar: str
    description_ar: str
    label: ExceptionLabel


class Context:
    """Window, settings and cached shift data shared by the rules of one run."""

    def __init__(self, db: Session, settings: Settings, start: datetime, end: datetime) -> None:
        self.db = db
        self.settings = settings
        self.start = start
        self.end = end
        self._shifts: list[Shift] | None = None
        self._tracks: dict[uuid.UUID, list[GpsPoint]] = {}
        self._batches: dict[uuid.UUID, list[GpsUploadBatch]] | None = None

    def shifts(self) -> list[Shift]:
        """Started shifts that overlap the window (active or completed)."""
        if self._shifts is None:
            self._shifts = list(
                self.db.scalars(
                    select(Shift)
                    .where(
                        Shift.status.in_((ShiftStatus.ACTIVE, ShiftStatus.COMPLETED)),
                        Shift.started_at < self.end,
                        or_(Shift.ended_at.is_(None), Shift.ended_at >= self.start),
                    )
                    .order_by(Shift.started_at)
                ).all()
            )
        return self._shifts

    def completed(self) -> list[Shift]:
        """Finished shifts: their tracks are complete enough to analyse."""
        return [
            s
            for s in self.shifts()
            if s.status is ShiftStatus.COMPLETED and s.started_at and s.ended_at
        ]

    def active_keys(self, rule_code: str) -> set[str]:
        """Keys of still-open exceptions of a rule that this window re-checks.

        Record-based rules only see records that still qualify (e.g. not
        voided), so they add these to their scope to notice when a case
        has disappeared.
        """
        return set(
            self.db.scalars(
                select(OperationalException.dedupe_key).where(
                    OperationalException.rule_code == rule_code,
                    OperationalException.status.in_(
                        (
                            ExceptionStatus.OPEN,
                            ExceptionStatus.UNDER_REVIEW,
                            ExceptionStatus.ESCALATED,
                        )
                    ),
                    OperationalException.occurred_at >= self.start,
                    OperationalException.occurred_at < self.end,
                )
            ).all()
        )

    def points(self, shift_id: uuid.UUID) -> list[GpsPoint]:
        if shift_id not in self._tracks:
            self._tracks[shift_id] = list(
                self.db.scalars(
                    select(GpsPoint)
                    .where(GpsPoint.shift_id == shift_id)
                    .order_by(GpsPoint.recorded_at)
                ).all()
            )
        return self._tracks[shift_id]

    def batches(self) -> dict[uuid.UUID, list[GpsUploadBatch]]:
        """Upload batches of the window's shifts, in the order the server received them."""
        if self._batches is None:
            ids = [s.id for s in self.shifts()]
            grouped: dict[uuid.UUID, list[GpsUploadBatch]] = defaultdict(list)
            if ids:
                for b in self.db.scalars(
                    select(GpsUploadBatch)
                    .where(GpsUploadBatch.shift_id.in_(ids))
                    .order_by(GpsUploadBatch.received_at, GpsUploadBatch.id)
                ):
                    grouped[b.shift_id].append(b)
            self._batches = dict(grouped)
        return self._batches

    def track(self, shift_id: uuid.UUID) -> list[TrackPoint]:
        return [
            TrackPoint(p.recorded_at, p.latitude, p.longitude, p.accuracy_m, p.speed_mps)
            for p in self.points(shift_id)
            if p.quality is PointQuality.VALID
        ]


def _minutes(a: datetime, b: datetime) -> int:
    return max(0, int((b - a).total_seconds() // 60))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _shift_links(shift: Shift) -> dict[str, Any]:
    return {"vehicle_id": shift.vehicle_id, "driver_id": shift.driver_id, "shift_id": shift.id}


@dataclass
class _Run:
    start: datetime
    end: datetime
    peak_m: float


def _runs_outside(
    track: list[TrackPoint],
    distance: Callable[[TrackPoint], float],
    *,
    limit_m: float,
    min_seconds: int,
    max_gap_seconds: int,
) -> list[_Run]:
    """Consecutive points farther than `limit_m`, lasting at least `min_seconds`.

    A GPS gap ends a run: time without points is never counted as time away.
    """
    runs: list[_Run] = []
    current: _Run | None = None
    prev: TrackPoint | None = None
    for p in track:
        d = distance(p)
        broken = prev is not None and (
            (p.recorded_at - prev.recorded_at).total_seconds() > max_gap_seconds
        )
        if current and (broken or d <= limit_m):
            runs.append(current)
            current = None
        if d > limit_m:
            if current is None:
                current = _Run(p.recorded_at, p.recorded_at, d)
            else:
                current.end = p.recorded_at
                current.peak_m = max(current.peak_m, d)
        prev = p
    if current:
        runs.append(current)
    return [r for r in runs if (r.end - r.start).total_seconds() >= min_seconds]


# --- Tracking ---------------------------------------------------------------

_DISABLE_RESTORE = {
    TrackingEventType.LOCATION_DISABLED: (
        TrackingEventType.LOCATION_ENABLED,
        "إيقاف خدمة الموقع على الهاتف",
    ),
    TrackingEventType.PERMISSION_DENIED: (
        TrackingEventType.PERMISSION_GRANTED,
        "سحب إذن الموقع من التطبيق",
    ),
}


def gps_disabled(ctx: Context) -> RuleResult:
    shifts = {s.id: s for s in ctx.shifts()}
    result = RuleResult()
    if not shifts:
        return result
    events = list(
        ctx.db.scalars(
            select(TrackingEvent)
            .where(TrackingEvent.shift_id.in_(shifts))
            .order_by(TrackingEvent.occurred_at)
        ).all()
    )
    now = utcnow()
    by_shift: dict[uuid.UUID, list[TrackingEvent]] = defaultdict(list)
    for ev in events:
        if ev.shift_id:
            by_shift[ev.shift_id].append(ev)
    for shift_id, shift_events in by_shift.items():
        shift = shifts[shift_id]
        for i, ev in enumerate(shift_events):
            if ev.event_type not in _DISABLE_RESTORE:
                continue
            restore_type, what = _DISABLE_RESTORE[ev.event_type]
            restored = next(
                (e for e in shift_events[i + 1 :] if e.event_type is restore_type), None
            )
            until = restored.occurred_at if restored else (shift.ended_at or now)
            minutes = _minutes(ev.occurred_at, until)
            key = f"GPS_DISABLED:{ev.id}"
            result.scopes.add(key)
            if minutes < ctx.settings.exception_gps_disabled_minutes:
                continue
            severity = HIGH if restored is None or minutes >= 60 else MEDIUM
            restored_text = "" if restored else " ولم يُسترجع حتى نهاية الوردية"
            result.candidates.append(
                Candidate(
                    rule_code="GPS_DISABLED",
                    severity=severity,
                    summary=f"{what} أثناء الوردية لمدة {minutes} دقيقة{restored_text}",
                    evidence={
                        "event": ev.event_type.value,
                        "disabled_at": _iso(ev.occurred_at),
                        "reported_at": _iso(ev.received_at),
                        "restored_at": _iso(restored.occurred_at if restored else None),
                        "minutes": minutes,
                        "shift_still_active": shift.ended_at is None,
                        "threshold_minutes": ctx.settings.exception_gps_disabled_minutes,
                    },
                    occurred_at=ev.occurred_at,
                    occurred_until=until,
                    dedupe_key=key,
                    **_shift_links(shift),
                )
            )
    return result


def gps_gaps(ctx: Context) -> RuleResult:
    s = ctx.settings
    result = RuleResult()
    threshold = s.exception_gps_gap_minutes * 60
    for shift in ctx.completed():
        if shift.started_at is None or shift.ended_at is None:
            continue
        key = f"GPS_GAP:{shift.id}"
        result.scopes.add(key)
        gaps = find_gaps(
            ctx.track(shift.id),
            window_start=shift.started_at,
            window_end=shift.ended_at,
            max_gap_seconds=threshold,
        )
        if not gaps:
            continue
        events = ctx.db.execute(
            select(TrackingEvent.event_type, TrackingEvent.occurred_at).where(
                TrackingEvent.shift_id == shift.id
            )
        ).all()
        items: list[dict[str, Any]] = []
        for g in gaps:
            items.append(
                {
                    "start": _iso(g.start),
                    "end": _iso(g.end),
                    "minutes": g.seconds // 60,
                    "moved_m": round(g.displacement_m) if g.displacement_m is not None else None,
                    "device_events": sorted(
                        {e.value for e, at in events if g.start <= at <= g.end}
                    ),
                }
            )
        total = sum(i["minutes"] for i in items)
        moved = any(
            g.displacement_m is not None and g.displacement_m >= s.exception_gps_gap_moved_m
            for g in gaps
        )
        result.candidates.append(
            Candidate(
                rule_code="GPS_GAP",
                severity=MEDIUM if moved else LOW,
                summary=(
                    f"انقطاع بيانات الموقع {len(gaps)} مرة بإجمالي {total} دقيقة"
                    + (" وتغيّر موقع المركبة خلال الانقطاع" if moved else "")
                ),
                evidence={
                    "gaps": items,
                    "total_minutes": total,
                    "shift_minutes": _minutes(shift.started_at, shift.ended_at),
                    "threshold_minutes": s.exception_gps_gap_minutes,
                    "moved_threshold_m": s.exception_gps_gap_moved_m,
                },
                occurred_at=gaps[0].start,
                occurred_until=gaps[-1].end,
                dedupe_key=key,
                **_shift_links(shift),
            )
        )
    return result


def mock_location(ctx: Context) -> RuleResult:
    result = RuleResult()
    shifts = {s.id: s for s in ctx.shifts()}
    if not shifts:
        return result
    rows = ctx.db.execute(
        select(
            GpsPoint.shift_id,
            func.count(),
            func.min(GpsPoint.recorded_at),
            func.max(GpsPoint.recorded_at),
        )
        .where(GpsPoint.shift_id.in_(shifts), GpsPoint.is_mock.is_(True))
        .group_by(GpsPoint.shift_id)
    ).all()
    for shift_id in shifts:
        result.scopes.add(f"MOCK_LOCATION:{shift_id}")
    for shift_id, count, first, last in rows:
        shift = shifts[shift_id]
        result.candidates.append(
            Candidate(
                rule_code="MOCK_LOCATION",
                severity=HIGH,
                summary=f"الهاتف أبلغ عن مصدر موقع وهمي في {count} نقطة أثناء الوردية",
                evidence={"points": count, "first": _iso(first), "last": _iso(last)},
                occurred_at=first,
                occurred_until=last,
                dedupe_key=f"MOCK_LOCATION:{shift_id}",
                **_shift_links(shift),
            )
        )
    return result


# --- GPS integrity (U02) ------------------------------------------------------
# Each finding is evidence for a reviewer, never a conclusion: a phone can
# restart, lose internet or have a wrong clock for ordinary reasons.


def _boot_count(ev: TrackingEvent) -> int | None:
    raw = (ev.details or {}).get("boot_count")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


@dataclass
class _Interruption:
    event: TrackingEvent
    start: datetime
    restarted_at: datetime | None
    detected_by: str
    reboot: bool | None


def _interruptions(
    shift: Shift, events: list[TrackingEvent], times: list[datetime]
) -> list[_Interruption]:
    """Walk a shift's start/stop/restart events and work out each tracking outage.

    The outage starts at an explicit "service stopped" event when the phone
    sent one (a killed process cannot), otherwise at the last point before
    the restart. A changed boot counter between two starts means a reboot.
    """
    assert shift.started_at is not None  # noqa: S101
    found: list[_Interruption] = []
    pending_stop: TrackingEvent | None = None
    last_boot: int | None = None
    for ev in events:
        if ev.event_type is TrackingEventType.TRACKING_STOPPED:
            # "shift_ended" is the normal end of tracking, not an interruption.
            if (ev.details or {}).get("reason") == "service_stopped":
                pending_stop = ev
            continue
        boot = _boot_count(ev)
        if ev.event_type is TrackingEventType.SERVICE_RESTARTED:
            before = [t for t in times if t < ev.occurred_at]
            if pending_stop is not None:
                start, how = pending_stop.occurred_at, "stop_event"
            elif before:
                start, how = before[-1], "last_point"
            else:
                start, how = shift.started_at, "shift_start"
            reboot = None if boot is None or last_boot is None else boot != last_boot
            found.append(_Interruption(ev, start, ev.occurred_at, how, reboot))
            pending_stop = None
        if boot is not None:
            last_boot = boot
    if pending_stop is not None:
        # Stopped and never restarted: lost until points resume or the shift ends.
        after = [t for t in times if t > pending_stop.occurred_at]
        found.append(
            _Interruption(
                pending_stop,
                pending_stop.occurred_at,
                after[0] if after else None,
                "stop_event",
                None,
            )
        )
    return found


def tracking_interrupted(ctx: Context) -> RuleResult:
    """Tracking service stopped or restarted during a shift, with the time lost."""
    s = ctx.settings
    result = RuleResult()
    shifts = {sh.id: sh for sh in ctx.shifts()}
    if not shifts:
        return result
    events = ctx.db.scalars(
        select(TrackingEvent)
        .where(
            TrackingEvent.shift_id.in_(shifts),
            TrackingEvent.event_type.in_(
                (
                    TrackingEventType.TRACKING_STARTED,
                    TrackingEventType.SERVICE_RESTARTED,
                    TrackingEventType.TRACKING_STOPPED,
                )
            ),
        )
        .order_by(TrackingEvent.occurred_at)
    ).all()
    by_shift: dict[uuid.UUID, list[TrackingEvent]] = defaultdict(list)
    for ev in events:
        if ev.shift_id:
            by_shift[ev.shift_id].append(ev)
    now = utcnow()
    for shift_id, shift_events in by_shift.items():
        shift = shifts[shift_id]
        if shift.started_at is None:
            continue
        times = [p.recorded_at for p in ctx.points(shift_id)]
        for it in _interruptions(shift, shift_events, times):
            key = f"TRACKING_INTERRUPTED:{it.event.id}"
            result.scopes.add(key)
            never_restarted = it.event.event_type is TrackingEventType.TRACKING_STOPPED
            end = it.restarted_at or shift.ended_at or now
            minutes = _minutes(it.start, end) if end > it.start else 0
            if minutes < s.exception_tracking_interrupted_minutes:
                continue
            if never_restarted:
                summary = f"توقف التتبع أثناء الوردية ولم يُستأنف لمدة {minutes} دقيقة"
            elif it.reboot:
                summary = f"توقف التتبع {minutes} دقيقة بسبب إعادة تشغيل الهاتف على الأرجح"
            else:
                summary = f"توقف التتبع {minutes} دقيقة ثم أعيد تشغيله أثناء الوردية"
            result.candidates.append(
                Candidate(
                    rule_code="TRACKING_INTERRUPTED",
                    severity=MEDIUM if never_restarted or minutes >= 60 else LOW,
                    summary=summary,
                    evidence={
                        "event": it.event.event_type.value,
                        "stopped_at": _iso(it.start),
                        "restarted_at": _iso(None if never_restarted else it.restarted_at),
                        "minutes": minutes,
                        "detected_by": it.detected_by,
                        "device_time": _iso(it.event.occurred_at),
                        "reported_at": _iso(it.event.received_at),
                        "reboot_detected": it.reboot,
                        "shift_still_active": shift.ended_at is None,
                        "threshold_minutes": s.exception_tracking_interrupted_minutes,
                    },
                    occurred_at=it.start,
                    occurred_until=end,
                    dedupe_key=key,
                    **_shift_links(shift),
                )
            )
    return result


def impossible_jumps(ctx: Context) -> RuleResult:
    """Points the server flagged because reaching them needed an impossible speed."""
    s = ctx.settings
    result = RuleResult()
    for shift in ctx.shifts():
        key = f"IMPOSSIBLE_JUMP:{shift.id}"
        result.scopes.add(key)
        prev: GpsPoint | None = None
        jumps: list[dict[str, Any]] = []
        jump_times: list[datetime] = []
        for p in ctx.points(shift.id):
            if p.quality is PointQuality.IMPLAUSIBLE_SPEED:
                jump_times.append(p.recorded_at)
                if prev is not None:
                    seconds = (p.recorded_at - prev.recorded_at).total_seconds()
                    dist = haversine_m(prev.latitude, prev.longitude, p.latitude, p.longitude)
                    jumps.append(
                        {
                            "at": _iso(p.recorded_at),
                            "distance_m": round(dist),
                            "seconds": round(seconds),
                            "speed_kmh": round(dist / seconds * 3.6) if seconds > 0 else None,
                        }
                    )
            elif p.quality is PointQuality.VALID:
                prev = p
        if not jump_times:
            continue
        speeds = [j["speed_kmh"] for j in jumps if j["speed_kmh"] is not None]
        result.candidates.append(
            Candidate(
                rule_code="IMPOSSIBLE_JUMP",
                severity=MEDIUM if len(jump_times) >= 3 else LOW,
                summary=(
                    f"قفزات غير ممكنة في الموقع: {len(jump_times)} نقطة تتطلب سرعة أعلى من "
                    f"{round(s.gps_max_speed_kmh)} كم/س (لم تُحسب في المسافة)"
                ),
                evidence={
                    "points": len(jump_times),
                    "first": _iso(jump_times[0]),
                    "last": _iso(jump_times[-1]),
                    "max_speed_kmh": max(speeds) if speeds else None,
                    "speed_limit_kmh": s.gps_max_speed_kmh,
                    "examples": jumps[:5],
                },
                occurred_at=jump_times[0],
                occurred_until=jump_times[-1],
                dedupe_key=key,
                **_shift_links(shift),
            )
        )
    return result


def late_uploads(ctx: Context) -> RuleResult:
    """Points that reached the server long after the phone recorded them."""
    s = ctx.settings
    result = RuleResult()
    shifts = {sh.id: sh for sh in ctx.shifts()}
    if not shifts:
        return result
    delay = GpsPoint.received_at - GpsPoint.recorded_at
    rows = ctx.db.execute(
        select(
            GpsPoint.shift_id,
            func.count(),
            func.min(GpsPoint.recorded_at),
            func.max(GpsPoint.recorded_at),
            func.max(delay),
            func.max(GpsPoint.received_at),
        )
        .where(
            GpsPoint.shift_id.in_(shifts),
            delay > timedelta(hours=s.exception_late_upload_hours),
        )
        .group_by(GpsPoint.shift_id)
    ).all()
    for shift_id in shifts:
        result.scopes.add(f"LATE_GPS_UPLOAD:{shift_id}")
    for shift_id, count, first, last, max_delay, last_received in rows:
        shift = shifts[shift_id]
        hours = round(cast("timedelta", max_delay).total_seconds() / 3600, 1)
        result.candidates.append(
            Candidate(
                rule_code="LATE_GPS_UPLOAD",
                severity=LOW,
                summary=(
                    f"وصلت {count} نقطة موقع بعد أكثر من {s.exception_late_upload_hours} ساعة "
                    "من تسجيلها (قد يكون الهاتف بلا إنترنت)"
                ),
                evidence={
                    "points": count,
                    "first": _iso(first),
                    "last": _iso(last),
                    "max_delay_hours": hours,
                    "last_received_at": _iso(last_received),
                    "shift_end": _iso(shift.ended_at),
                    "threshold_hours": s.exception_late_upload_hours,
                },
                occurred_at=first,
                occurred_until=last,
                dedupe_key=f"LATE_GPS_UPLOAD:{shift_id}",
                **_shift_links(shift),
            )
        )
    return result


def out_of_shift_points(ctx: Context) -> RuleResult:
    """The phone sent points recorded outside the shift (refused, not stored)."""
    result = RuleResult()
    batches = ctx.batches()
    for shift in ctx.shifts():
        key = f"OUT_OF_SHIFT_GPS:{shift.id}"
        result.scopes.add(key)
        hits = [b for b in batches.get(shift.id, []) if b.rejected_outside_shift > 0]
        if not hits:
            continue
        count = sum(b.rejected_outside_shift for b in hits)
        first = min(b.outside_shift_first_at or b.received_at for b in hits)
        last = max(b.outside_shift_last_at or b.received_at for b in hits)
        result.candidates.append(
            Candidate(
                rule_code="OUT_OF_SHIFT_GPS",
                severity=LOW,
                summary=f"أرسل الهاتف {count} نقطة موقع مسجلة خارج وقت الوردية ولم تُحفظ",
                evidence={
                    "points": count,
                    "first": _iso(first),
                    "last": _iso(last),
                    "shift_start": _iso(shift.started_at),
                    "shift_end": _iso(shift.ended_at),
                    "batches": len(hits),
                    "note": "تُحفظ الأوقات فقط؛ مواقع خارج الوردية لا تُخزن",
                },
                occurred_at=first,
                occurred_until=last,
                dedupe_key=key,
                **_shift_links(shift),
            )
        )
    return result


def timestamp_anomalies(ctx: Context) -> RuleResult:
    """Phone clock far from the server's, future points, or batches going back in time."""
    s = ctx.settings
    result = RuleResult()
    skew_limit = s.exception_clock_skew_minutes * 60
    back_limit = timedelta(minutes=s.exception_backwards_minutes)
    for shift in ctx.shifts():
        key = f"TIMESTAMP_ANOMALY:{shift.id}"
        result.scopes.add(key)
        batches = ctx.batches().get(shift.id, [])
        future_points = sum(b.rejected_future for b in batches)
        future_max = max((b.future_max_seconds or 0 for b in batches), default=0)
        offsets: list[float] = []
        backwards: list[float] = []
        flagged_at: list[datetime] = []
        newest: datetime | None = None
        for b in batches:
            if b.device_time is not None:
                # Positive: the phone's clock is ahead of the server's.
                offset = (b.device_time - b.received_at).total_seconds()
                if abs(offset) >= skew_limit:
                    offsets.append(offset)
                    flagged_at.append(b.received_at)
            if b.first_recorded_at is None or b.last_recorded_at is None:
                continue
            if newest is not None and b.first_recorded_at < newest - back_limit:
                backwards.append((newest - b.first_recorded_at).total_seconds())
                flagged_at.append(b.received_at)
            newest = max(newest, b.last_recorded_at) if newest else b.last_recorded_at
        if future_points:
            flagged_at.extend(b.received_at for b in batches if b.rejected_future)
        if not (future_points or offsets or backwards):
            continue
        max_offset = max(offsets, key=abs) if offsets else None
        max_back = max(backwards) if backwards else None
        parts: list[str] = []
        if max_offset is not None:
            parts.append(f"ساعة الهاتف تختلف عن الخادم بنحو {round(abs(max_offset) / 60)} دقيقة")
        if max_back is not None:
            parts.append(f"نقاط وصلت بأوقات تعود للخلف حتى {round(max_back / 60)} دقيقة")
        if future_points:
            parts.append(f"{future_points} نقطة بتاريخ مستقبلي رُفضت")
        serious = (max_back or 0) >= 600 or abs(max_offset or 0) >= 1800 or future_max >= 1800
        result.candidates.append(
            Candidate(
                rule_code="TIMESTAMP_ANOMALY",
                severity=MEDIUM if serious else LOW,
                summary="توقيت غير معتاد لبيانات الموقع: " + "، ".join(parts),
                evidence={
                    "batches": len(batches),
                    "clock_offset_batches": len(offsets),
                    "max_clock_offset_minutes": (
                        round(max_offset / 60, 1) if max_offset is not None else None
                    ),
                    "backwards_batches": len(backwards),
                    "max_backwards_minutes": round(max_back / 60, 1) if max_back else None,
                    "future_points": future_points,
                    "future_max_minutes": round(future_max / 60, 1) if future_points else None,
                    "clock_threshold_minutes": s.exception_clock_skew_minutes,
                    "backwards_threshold_minutes": s.exception_backwards_minutes,
                },
                occurred_at=min(flagged_at),
                occurred_until=max(flagged_at),
                dedupe_key=key,
                **_shift_links(shift),
            )
        )
    return result


def _route_stops(route: RouteDefinition | None) -> list[tuple[float, float, int]]:
    if route is None:
        return []
    return [
        (float(st.latitude), float(st.longitude), st.radius_m)
        for st in route.stops
        if st.latitude is not None and st.longitude is not None
    ]


def long_stops(ctx: Context) -> RuleResult:
    s = ctx.settings
    result = RuleResult()
    for shift in ctx.completed():
        key = f"LONG_STOP:{shift.id}"
        result.scopes.add(key)
        stops = find_stops(
            ctx.track(shift.id),
            radius_m=s.gps_stop_radius_m,
            min_seconds=s.exception_long_stop_minutes * 60,
        )
        items: list[dict[str, Any]] = []
        for st in stops:
            session = next(
                (
                    se
                    for se in shift.sessions
                    if se.status is not SessionStatus.CANCELLED
                    and se.started_at <= st.start
                    and (se.ended_at is None or st.start <= se.ended_at)
                ),
                None,
            )
            # Waiting at a route's own stops (terminal, school) is expected.
            expected = any(
                haversine_m(st.latitude, st.longitude, lat, lng) <= radius + s.gps_stop_radius_m
                for lat, lng, radius in _route_stops(session.route if session else None)
            )
            if expected:
                continue
            items.append(
                {
                    "start": _iso(st.start),
                    "end": _iso(st.end),
                    "minutes": st.seconds // 60,
                    "lat": round(st.latitude, 6),
                    "lng": round(st.longitude, 6),
                    "operation": session.operation_type.name_ar if session else None,
                }
            )
        if not items:
            continue
        longest = max(i["minutes"] for i in items)
        result.candidates.append(
            Candidate(
                rule_code="LONG_STOP",
                severity=LOW,
                summary=f"توقف طويل خارج نقاط المسار ({len(items)} مرة، أطولها {longest} دقيقة)",
                evidence={"stops": items, "threshold_minutes": s.exception_long_stop_minutes},
                occurred_at=datetime.fromisoformat(items[0]["start"]),
                occurred_until=datetime.fromisoformat(items[-1]["end"]),
                dedupe_key=key,
                **_shift_links(shift),
            )
        )
    return result


def route_deviation(ctx: Context) -> RuleResult:
    s = ctx.settings
    result = RuleResult()
    for shift in ctx.completed():
        for session in shift.sessions:
            stops = _route_stops(session.route)
            if session.status is SessionStatus.CANCELLED or len(stops) < 2:
                continue
            key = f"ROUTE_DEVIATION:{session.id}"
            result.scopes.add(key)
            line = [(lat, lng) for lat, lng, _ in stops]
            until = session.ended_at or shift.ended_at
            if until is None:
                continue
            track = [p for p in ctx.track(shift.id) if session.started_at <= p.recorded_at <= until]

            def off_route(p: TrackPoint, line: list[tuple[float, float]] = line) -> float:
                return point_to_polyline_m(p.latitude, p.longitude, line)

            runs = _runs_outside(
                track,
                off_route,
                limit_m=s.exception_route_corridor_m,
                min_seconds=s.exception_route_min_minutes * 60,
                max_gap_seconds=s.gps_gap_seconds,
            )
            if not runs:
                continue
            peak = max(r.peak_m for r in runs)
            if session.route is None:
                continue
            result.candidates.append(
                Candidate(
                    rule_code="ROUTE_DEVIATION",
                    severity=MEDIUM if peak >= 2 * s.exception_route_corridor_m else LOW,
                    summary=(
                        f"ابتعاد عن مسار «{session.route.name}» حتى "
                        f"{peak / 1000:.1f} كم ({len(runs)} مرة)"
                    ),
                    evidence={
                        "route": session.route.name,
                        "segments": [
                            {
                                "start": _iso(r.start),
                                "end": _iso(r.end),
                                "minutes": _minutes(r.start, r.end),
                                "max_distance_m": round(r.peak_m),
                            }
                            for r in runs
                        ],
                        "corridor_m": s.exception_route_corridor_m,
                        "min_minutes": s.exception_route_min_minutes,
                        "method": "خطوط مستقيمة بين نقاط المسار وليست شبكة الطرق",
                    },
                    occurred_at=runs[0].start,
                    occurred_until=runs[-1].end,
                    dedupe_key=key,
                    **_shift_links(shift),
                )
            )
    return result


def parse_areas(raw: str) -> list[tuple[float, float, float]]:
    """`lat,lng,radius_km;...` -> [(lat, lng, radius_m)]. Invalid entries are skipped."""
    areas: list[tuple[float, float, float]] = []
    for part in raw.split(";"):
        bits = [b.strip() for b in part.split(",")]
        if len(bits) != 3:
            continue
        try:
            lat, lng, radius_km = (float(b) for b in bits)
        except ValueError:
            continue
        if -90 <= lat <= 90 and -180 <= lng <= 180 and radius_km > 0:
            areas.append((lat, lng, radius_km * 1000))
    return areas


def outside_area(ctx: Context) -> RuleResult:
    s = ctx.settings
    result = RuleResult()
    areas = parse_areas(s.exception_operating_areas)
    if not areas:
        return result

    def beyond(p: TrackPoint) -> float:
        # Distance past the edge of the nearest area (<= 0 means inside one).
        return min(haversine_m(p.latitude, p.longitude, a, b) - r for a, b, r in areas)

    for shift in ctx.completed():
        key = f"OUTSIDE_AREA:{shift.id}"
        result.scopes.add(key)
        runs = _runs_outside(
            ctx.track(shift.id),
            beyond,
            limit_m=0.0,
            min_seconds=s.exception_outside_area_minutes * 60,
            max_gap_seconds=s.gps_gap_seconds,
        )
        if not runs:
            continue
        minutes = sum(_minutes(r.start, r.end) for r in runs)
        result.candidates.append(
            Candidate(
                rule_code="OUTSIDE_AREA",
                severity=MEDIUM,
                summary=f"تشغيل خارج نطاق العمل المحدد لمدة {minutes} دقيقة",
                evidence={
                    "segments": [
                        {
                            "start": _iso(r.start),
                            "end": _iso(r.end),
                            "minutes": _minutes(r.start, r.end),
                            "max_beyond_m": round(r.peak_m),
                        }
                        for r in runs
                    ],
                    "areas": [{"lat": a, "lng": b, "radius_km": r / 1000} for a, b, r in areas],
                },
                occurred_at=runs[0].start,
                occurred_until=runs[-1].end,
                dedupe_key=key,
                **_shift_links(shift),
            )
        )
    return result


# --- Odometer ---------------------------------------------------------------


def _vehicle_sequences(ctx: Context) -> list[tuple[Shift, Shift]]:
    """(previous, next) shift pairs of the same vehicle where `next` starts in the window."""
    in_window = [s for s in ctx.shifts() if s.started_at and s.started_at >= ctx.start]
    pairs: list[tuple[Shift, Shift]] = []
    for nxt in in_window:
        if nxt.started_at is None:
            continue
        prev = ctx.db.scalars(
            select(Shift)
            .where(
                Shift.vehicle_id == nxt.vehicle_id,
                Shift.status == ShiftStatus.COMPLETED,
                Shift.ended_at <= nxt.started_at,
                Shift.id != nxt.id,
            )
            .order_by(Shift.ended_at.desc())
            .limit(1)
        ).first()
        if prev is not None:
            pairs.append((prev, nxt))
    return pairs


def moved_between_shifts(ctx: Context) -> RuleResult:
    s = ctx.settings
    result = RuleResult()
    for prev, nxt in _vehicle_sequences(ctx):
        key = f"MOVED_BETWEEN_SHIFTS:{nxt.id}"
        result.scopes.add(key)
        if prev.end_odometer_km is None or nxt.start_odometer_km is None:
            continue
        diff = nxt.start_odometer_km - prev.end_odometer_km
        if diff <= s.exception_moved_between_shifts_km:
            continue
        if prev.ended_at is None or nxt.started_at is None:
            continue
        result.candidates.append(
            Candidate(
                rule_code="MOVED_BETWEEN_SHIFTS",
                severity=HIGH if diff > 50 else MEDIUM,
                summary=f"العداد زاد {diff} كم بين نهاية وردية وبداية الوردية التالية",
                evidence={
                    "previous_shift_id": str(prev.id),
                    "previous_driver": prev.driver.full_name,
                    "previous_end_at": _iso(prev.ended_at),
                    "previous_end_odometer_km": prev.end_odometer_km,
                    "next_shift_id": str(nxt.id),
                    "next_driver": nxt.driver.full_name,
                    "next_start_at": _iso(nxt.started_at),
                    "next_start_odometer_km": nxt.start_odometer_km,
                    "difference_km": diff,
                    "hours_between": round(
                        (nxt.started_at - prev.ended_at).total_seconds() / 3600, 1
                    ),
                    "threshold_km": s.exception_moved_between_shifts_km,
                    "note": "لا يُسجل الموقع خارج الورديات؛ المصدر قراءات العداد",
                },
                occurred_at=prev.ended_at,
                occurred_until=nxt.started_at,
                dedupe_key=key,
                # The vehicle was in the previous driver's hands after that shift.
                vehicle_id=nxt.vehicle_id,
                driver_id=prev.driver_id,
                shift_id=nxt.id,
            )
        )
    return result


def implausible_odometer(ctx: Context) -> RuleResult:
    s = ctx.settings
    result = RuleResult()
    for shift in ctx.completed():
        if shift.started_at is None or shift.ended_at is None:
            continue
        key = f"IMPLAUSIBLE_ODOMETER:{shift.id}"
        result.scopes.add(key)
        distance = shift.odometer_distance_km
        if distance is None:
            continue
        hours = max((shift.ended_at - shift.started_at).total_seconds() / 3600, 0.25)
        limit = s.exception_max_avg_speed_kmh * hours
        if distance <= limit:
            continue
        result.candidates.append(
            Candidate(
                rule_code="IMPLAUSIBLE_ODOMETER",
                severity=HIGH,
                summary=(
                    f"مسافة العداد {distance} كم خلال "
                    f"{_minutes(shift.started_at, shift.ended_at)} دقيقة "
                    "أكبر من الممكن — قد تكون قراءة خاطئة"
                ),
                evidence={
                    "start_odometer_km": shift.start_odometer_km,
                    "end_odometer_km": shift.end_odometer_km,
                    "distance_km": distance,
                    "shift_hours": round(hours, 2),
                    "max_avg_speed_kmh": s.exception_max_avg_speed_kmh,
                    "max_plausible_km": round(limit),
                },
                occurred_at=shift.started_at,
                occurred_until=shift.ended_at,
                dedupe_key=key,
                **_shift_links(shift),
            )
        )
    for prev, nxt in _vehicle_sequences(ctx):
        key = f"IMPLAUSIBLE_ODOMETER:{nxt.id}:backwards"
        result.scopes.add(key)
        if prev.end_odometer_km is None or nxt.start_odometer_km is None:
            continue
        if nxt.start_odometer_km >= prev.end_odometer_km:
            continue
        if prev.ended_at is None or nxt.started_at is None:
            continue
        result.candidates.append(
            Candidate(
                rule_code="IMPLAUSIBLE_ODOMETER",
                severity=HIGH,
                summary=(
                    f"عداد بداية الوردية ({nxt.start_odometer_km}) أقل من عداد نهاية "
                    f"الوردية السابقة ({prev.end_odometer_km})"
                ),
                evidence={
                    "previous_shift_id": str(prev.id),
                    "previous_end_odometer_km": prev.end_odometer_km,
                    "next_start_odometer_km": nxt.start_odometer_km,
                    "difference_km": nxt.start_odometer_km - prev.end_odometer_km,
                },
                occurred_at=nxt.started_at,
                dedupe_key=key,
                **_shift_links(nxt),
            )
        )
    return result


def gps_odometer_mismatch(ctx: Context) -> RuleResult:
    """Odometer and GPS distances differ beyond the tolerance (U04 reconciliation).

    Only shifts with both readings and enough GPS coverage are compared;
    missing data is never treated as a difference.
    """
    s = ctx.settings
    result = RuleResult()
    for shift in ctx.completed():
        if shift.started_at is None or shift.ended_at is None:
            continue
        key = f"GPS_ODOMETER_MISMATCH:{shift.id}"
        result.scopes.add(key)
        rec = reconcile(shift, ctx.track(shift.id), s)
        if rec.status is not ReconciliationStatus.REVIEW:
            continue
        assert rec.odometer_km is not None and rec.gps_km is not None  # noqa: S101
        assert rec.difference_km is not None  # noqa: S101
        diff, odometer, gps_km = rec.difference_km, rec.odometer_km, rec.gps_km
        direction = "أكبر" if diff > 0 else "أقل"
        big = abs(diff) > 50 and abs(diff) > 0.5 * max(odometer, gps_km)
        result.candidates.append(
            Candidate(
                rule_code="GPS_ODOMETER_MISMATCH",
                severity=HIGH if big else MEDIUM,
                summary=(
                    f"مسافة العداد ({odometer} كم) {direction} من مسافة GPS "
                    f"({gps_km:.1f} كم) بفارق {abs(diff):.1f} كم"
                ),
                evidence={
                    "odometer_km": odometer,
                    "gps_km": gps_km,
                    "difference_km": diff,
                    "difference_pct": rec.difference_pct,
                    "allowed_km": rec.allowed_km,
                    "gps_coverage_pct": rec.gps_coverage_pct,
                    "tolerance_pct": rec.tolerance_pct,
                    "tolerance_km": rec.tolerance_km,
                    "odometer_corrected": rec.odometer_corrected,
                },
                occurred_at=shift.started_at,
                occurred_until=shift.ended_at,
                dedupe_key=key,
                **_shift_links(shift),
            )
        )
    return result


# --- Fuel -------------------------------------------------------------------


_week_start = week_start  # weeks start on Saturday (Egyptian working week)


def _week_figures(
    ctx: Context, vehicle_id: uuid.UUID, week: date
) -> tuple[Decimal, int, dict[str, dict[str, str]]]:
    start = local_day_bounds_utc(week)[0]
    end = local_day_bounds_utc(week + timedelta(days=6))[1]
    rows = ctx.db.execute(
        select(FuelType.code, FuelTransaction.quantity, FuelTransaction.total_amount)
        .join(FuelType, FuelType.id == FuelTransaction.fuel_type_id)
        .where(
            FuelTransaction.vehicle_id == vehicle_id,
            FuelType.category == FuelCategory.FUEL,
            FuelTransaction.status.in_(LIVE),
            FuelTransaction.occurred_at >= start,
            FuelTransaction.occurred_at < end,
        )
    ).all()
    cost = Decimal("0")
    by_type: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"quantity": Decimal("0"), "cost": Decimal("0")}
    )
    for code, quantity, amount in rows:
        cost += amount
        by_type[code]["quantity"] += quantity
        by_type[code]["cost"] += amount
    km = 0
    for shift in ctx.db.scalars(
        select(Shift).where(
            Shift.vehicle_id == vehicle_id,
            Shift.status == ShiftStatus.COMPLETED,
            Shift.started_at >= start,
            Shift.started_at < end,
        )
    ).all():
        km += shift.odometer_distance_km or 0
    return (
        cost,
        km,
        {
            k: {"quantity": str(v["quantity"]), "cost": str(fc.money(v["cost"]))}
            for k, v in by_type.items()
        },
    )


def fuel_consumption(ctx: Context) -> RuleResult:
    s = ctx.settings
    result = RuleResult()
    # Whole weeks (Saturday-Friday) that ended during or just before the window.
    last = _week_start(to_local_date(ctx.end)) - timedelta(days=7)
    week = _week_start(to_local_date(ctx.start)) - timedelta(days=7)
    weeks: list[date] = []
    while week <= last:
        weeks.append(week)
        week += timedelta(days=7)
    if not weeks:
        return result
    vehicles = set(
        ctx.db.scalars(
            select(FuelTransaction.vehicle_id)
            .where(
                FuelTransaction.status.in_(LIVE),
                FuelTransaction.occurred_at >= local_day_bounds_utc(weeks[0])[0],
            )
            .distinct()
        ).all()
    )
    for vehicle_id in vehicles:
        for week in weeks:
            key = f"FUEL_CONSUMPTION:{vehicle_id}:{week.isoformat()}"
            result.scopes.add(key)
            cost, km, by_type = _week_figures(ctx, vehicle_id, week)
            if km < s.exception_fuel_min_week_km or cost <= 0:
                continue
            history: list[Decimal] = []
            for back in range(1, s.exception_fuel_history_weeks + 1):
                h_cost, h_km, _ = _week_figures(ctx, vehicle_id, week - timedelta(days=7 * back))
                if h_km >= s.exception_fuel_min_week_km and h_cost > 0:
                    history.append(h_cost / h_km)
            if len(history) < 3:
                continue
            baseline = Decimal(str(statistics.median(history)))
            current = cost / km
            ratio = current / baseline
            if ratio < Decimal(str(s.exception_fuel_ratio)):
                continue
            start = local_day_bounds_utc(week)[0]
            result.candidates.append(
                Candidate(
                    rule_code="FUEL_CONSUMPTION",
                    severity=MEDIUM if ratio >= 2 else LOW,
                    summary=(
                        f"تكلفة الوقود لكل كم {fc.money(current)} أعلى "
                        f"{ratio:.1f}× من المعتاد للمركبة ({fc.money(baseline)})"
                    ),
                    evidence={
                        "week_start": week.isoformat(),
                        "week_end": (week + timedelta(days=6)).isoformat(),
                        "fuel_cost": str(fc.money(cost)),
                        "odometer_km": km,
                        "cost_per_km": str(fc.money(current)),
                        "baseline_cost_per_km": str(fc.money(baseline)),
                        "baseline_weeks": len(history),
                        "ratio": str(ratio.quantize(Decimal("0.01"))),
                        "threshold_ratio": s.exception_fuel_ratio,
                        "by_type": by_type,
                        "basis": "سجلات الوقود المقدمة والمعتمدة (بدون الزيوت)",
                    },
                    occurred_at=start,
                    occurred_until=local_day_bounds_utc(week + timedelta(days=6))[1],
                    dedupe_key=key,
                    vehicle_id=vehicle_id,
                )
            )
    return result


def _fuel_in_window(ctx: Context) -> list[FuelTransaction]:
    return list(
        ctx.db.scalars(
            select(FuelTransaction).where(
                FuelTransaction.status.in_(LIVE),
                FuelTransaction.occurred_at >= ctx.start,
                FuelTransaction.occurred_at < ctx.end,
            )
        ).all()
    )


def fuel_far_from_vehicle(ctx: Context) -> RuleResult:
    s = ctx.settings
    result = RuleResult(scopes=ctx.active_keys("FUEL_FAR"))
    window = timedelta(minutes=10)
    for tx in _fuel_in_window(ctx):
        if tx.latitude is None or tx.longitude is None:
            continue
        key = f"FUEL_FAR:{tx.id}"
        result.scopes.add(key)
        points = ctx.db.scalars(
            select(GpsPoint).where(
                GpsPoint.vehicle_id == tx.vehicle_id,
                GpsPoint.quality == PointQuality.VALID,
                GpsPoint.recorded_at.between(tx.occurred_at - window, tx.occurred_at + window),
            )
        ).all()
        if not points:
            continue  # no vehicle position to compare with
        nearest = min(points, key=lambda p: abs((p.recorded_at - tx.occurred_at).total_seconds()))
        distance = haversine_m(tx.latitude, tx.longitude, nearest.latitude, nearest.longitude)
        if distance <= s.exception_fuel_distance_m:
            continue
        result.candidates.append(
            Candidate(
                rule_code="FUEL_FAR",
                severity=MEDIUM,
                summary=f"موقع تسجيل الوقود يبعد {distance / 1000:.1f} كم عن موقع المركبة",
                evidence={
                    "fuel_at": _iso(tx.occurred_at),
                    "amount": str(fc.money(tx.total_amount)),
                    "vehicle_point_at": _iso(nearest.recorded_at),
                    "distance_m": round(distance),
                    "threshold_m": s.exception_fuel_distance_m,
                },
                occurred_at=tx.occurred_at,
                dedupe_key=key,
                vehicle_id=tx.vehicle_id,
                driver_id=tx.driver_id,
                shift_id=tx.shift_id,
                subject_type="fuel_transaction",
                subject_id=tx.id,
            )
        )
    return result


def fuel_outside_shift(ctx: Context) -> RuleResult:
    s = ctx.settings
    result = RuleResult(scopes=ctx.active_keys("FUEL_OUTSIDE_SHIFT"))
    grace = timedelta(minutes=s.exception_fuel_outside_shift_minutes)
    now = utcnow()
    for tx in _fuel_in_window(ctx):
        # Office purchases outside shifts are normal; driver purchases are not.
        if tx.driver_id is None and tx.paid_by is not PaidBy.DRIVER:
            continue
        key = f"FUEL_OUTSIDE_SHIFT:{tx.id}"
        result.scopes.add(key)
        covering = ctx.db.scalar(
            select(func.count())
            .select_from(Shift)
            .where(
                Shift.vehicle_id == tx.vehicle_id,
                Shift.status.in_((ShiftStatus.ACTIVE, ShiftStatus.COMPLETED)),
                Shift.started_at <= tx.occurred_at + grace,
                func.coalesce(Shift.ended_at, now) >= tx.occurred_at - grace,
            )
        )
        if covering:
            continue
        result.candidates.append(
            Candidate(
                rule_code="FUEL_OUTSIDE_SHIFT",
                severity=LOW,
                summary="شراء وقود بواسطة السائق في وقت لا توجد فيه وردية للمركبة",
                evidence={
                    "fuel_at": _iso(tx.occurred_at),
                    "amount": str(fc.money(tx.total_amount)),
                    "paid_by": tx.paid_by.value,
                    "grace_minutes": s.exception_fuel_outside_shift_minutes,
                },
                occurred_at=tx.occurred_at,
                dedupe_key=key,
                vehicle_id=tx.vehicle_id,
                driver_id=tx.driver_id,
                subject_type="fuel_transaction",
                subject_id=tx.id,
            )
        )
    return result


# --- Duplicates & revenue ---------------------------------------------------


def duplicate_files(ctx: Context) -> RuleResult:
    result = RuleResult(scopes=ctx.active_keys("DUPLICATE_FILE"))
    recent = (
        select(Attachment.sha256)
        .where(
            Attachment.deleted_at.is_(None),
            Attachment.created_at >= ctx.start,
            Attachment.created_at < ctx.end,
        )
        .distinct()
    )
    groups: dict[str, list[Attachment]] = defaultdict(list)
    for a in ctx.db.scalars(
        select(Attachment)
        .where(Attachment.deleted_at.is_(None), Attachment.sha256.in_(recent))
        .order_by(Attachment.created_at)
    ).all():
        groups[a.sha256].append(a)
    for sha, items in groups.items():
        key = f"DUPLICATE_FILE:{sha}"
        result.scopes.add(key)
        if len({(a.owner_type, a.owner_id) for a in items}) < 2:
            continue
        latest = items[-1]
        result.candidates.append(
            Candidate(
                rule_code="DUPLICATE_FILE",
                severity=MEDIUM,
                summary=f"نفس الملف مرفوع على {len({a.owner_id for a in items})} سجلات مختلفة",
                evidence={
                    "files": [
                        {
                            "attachment_id": str(a.id),
                            "owner_type": a.owner_type.value,
                            "owner_id": str(a.owner_id),
                            "uploaded_at": _iso(a.created_at),
                        }
                        for a in items
                    ],
                },
                occurred_at=items[0].created_at,
                occurred_until=latest.created_at,
                dedupe_key=key,
                subject_type=latest.owner_type.value,
                subject_id=latest.owner_id,
            )
        )
    return result


def duplicate_transactions(ctx: Context) -> RuleResult:
    s = ctx.settings
    result = RuleResult(scopes=ctx.active_keys("DUPLICATE_TRANSACTION"))
    window = timedelta(minutes=s.exception_duplicate_window_minutes)
    a, b = aliased(FuelTransaction), aliased(FuelTransaction)
    fuel_pairs = ctx.db.execute(
        select(a, b)
        .join(
            b,
            and_(
                a.vehicle_id == b.vehicle_id,
                a.fuel_type_id == b.fuel_type_id,
                a.total_amount == b.total_amount,
                a.id < b.id,
                b.occurred_at.between(a.occurred_at - window, a.occurred_at + window),
                b.status.in_(LIVE),
            ),
        )
        .where(
            a.status.in_(LIVE),
            or_(
                a.occurred_at.between(ctx.start, ctx.end),
                b.occurred_at.between(ctx.start, ctx.end),
            ),
        )
    ).all()
    for first, second in fuel_pairs:
        key = f"DUPLICATE_TRANSACTION:fuel:{first.id}:{second.id}"
        result.scopes.add(key)
        result.candidates.append(
            Candidate(
                rule_code="DUPLICATE_TRANSACTION",
                severity=MEDIUM,
                summary=(
                    f"سجلا وقود بنفس المبلغ ({fc.money(first.total_amount)}) والنوع للمركبة "
                    "في وقت متقارب"
                ),
                evidence={
                    "kind": "fuel",
                    "records": [
                        {"id": str(r.id), "at": _iso(r.occurred_at), "status": r.status.value}
                        for r in (first, second)
                    ],
                    "amount": str(fc.money(first.total_amount)),
                    "window_minutes": s.exception_duplicate_window_minutes,
                },
                occurred_at=min(first.occurred_at, second.occurred_at),
                occurred_until=max(first.occurred_at, second.occurred_at),
                dedupe_key=key,
                vehicle_id=first.vehicle_id,
                driver_id=second.driver_id or first.driver_id,
                subject_type="fuel_transaction",
                subject_id=second.id,
            )
        )
    ea, eb = aliased(Expense), aliased(Expense)
    expense_pairs = ctx.db.execute(
        select(ea, eb)
        .join(
            eb,
            and_(
                ea.vehicle_id == eb.vehicle_id,
                ea.category_id == eb.category_id,
                ea.amount == eb.amount,
                ea.id < eb.id,
                eb.occurred_at.between(ea.occurred_at - window, ea.occurred_at + window),
                eb.status.in_(LIVE),
            ),
        )
        .where(
            ea.status.in_(LIVE),
            or_(
                ea.occurred_at.between(ctx.start, ctx.end),
                eb.occurred_at.between(ctx.start, ctx.end),
            ),
        )
    ).all()
    for exp_a, exp_b in expense_pairs:
        key = f"DUPLICATE_TRANSACTION:expense:{exp_a.id}:{exp_b.id}"
        result.scopes.add(key)
        result.candidates.append(
            Candidate(
                rule_code="DUPLICATE_TRANSACTION",
                severity=MEDIUM,
                summary=(
                    f"مصروفان بنفس المبلغ ({fc.money(exp_a.amount)}) والتصنيف للمركبة في وقت متقارب"
                ),
                evidence={
                    "kind": "expense",
                    "records": [
                        {"id": str(r.id), "at": _iso(r.occurred_at), "status": r.status.value}
                        for r in (exp_a, exp_b)
                    ],
                    "amount": str(fc.money(exp_a.amount)),
                    "window_minutes": s.exception_duplicate_window_minutes,
                },
                occurred_at=min(exp_a.occurred_at, exp_b.occurred_at),
                occurred_until=max(exp_a.occurred_at, exp_b.occurred_at),
                dedupe_key=key,
                vehicle_id=exp_a.vehicle_id,
                driver_id=exp_b.driver_id or exp_a.driver_id,
                subject_type="expense",
                subject_id=exp_b.id,
            )
        )
    return result


def revenue_inconsistent(ctx: Context) -> RuleResult:
    s = ctx.settings
    result = RuleResult(scopes=ctx.active_keys("REVENUE_INCONSISTENT"))
    today = to_local_date(ctx.end)
    rows, _ = ride_hailing.reconciliation(
        ctx.db, date_from=today - timedelta(days=90), date_to=today
    )
    rates = [r.net_per_hour for r in rows if r.net_per_hour and r.ride_hailing_minutes >= 60]
    median = (
        Decimal(str(statistics.median(rates)))
        if len(rates) >= s.exception_revenue_min_statements
        else None
    )
    recent_from = to_local_date(ctx.start) - timedelta(days=30)
    ratio = Decimal(str(s.exception_revenue_ratio))
    for row in rows:
        st = row.statement
        if st is None or st.period_end < recent_from:
            continue
        key = f"REVENUE_INCONSISTENT:{st.id}"
        result.scopes.add(key)
        codes = {code for code, _ in row.flags}
        reason: str | None = None
        severity = LOW
        extra: dict[str, Any] = {}
        if "NO_SHIFTS" in codes:
            reason, severity = "كشف منصة بدون ورديات نقل ذكي مسجلة في فترته", MEDIUM
        elif "TRIPS_WITHOUT_TIME" in codes:
            reason, severity = "رحلات في الكشف بدون وقت تشغيل مسجل", MEDIUM
        elif (
            median
            and row.net_per_hour is not None
            and row.ride_hailing_minutes >= 60
            and (row.net_per_hour > median * ratio or row.net_per_hour < median / ratio)
        ):
            direction = "أعلى" if row.net_per_hour > median else "أقل"
            reason = (
                f"صافي الدخل لكل ساعة تشغيل ({row.net_per_hour}) {direction} "
                f"كثيرًا من المعتاد ({fc.money(median)})"
            )
            extra = {
                "fleet_median_per_hour": str(fc.money(median)),
                "ratio": s.exception_revenue_ratio,
            }
        if reason is None:
            continue
        start, _ = local_day_bounds_utc(st.period_start)
        _, end = local_day_bounds_utc(st.period_end)
        result.candidates.append(
            Candidate(
                rule_code="REVENUE_INCONSISTENT",
                severity=severity,
                summary=reason,
                evidence={
                    "statement_id": str(st.id),
                    "platform": st.platform.name,
                    "period_start": st.period_start.isoformat(),
                    "period_end": st.period_end.isoformat(),
                    "net_earnings": str(fc.money(st.net_earnings)),
                    "trips": st.trips_count,
                    "ride_hailing_minutes": row.ride_hailing_minutes,
                    "shifts": row.shifts_count,
                    "odometer_km": row.odometer_km,
                    "net_per_hour": str(row.net_per_hour) if row.net_per_hour is not None else None,
                    **extra,
                },
                occurred_at=start,
                occurred_until=end,
                dedupe_key=key,
                vehicle_id=st.vehicle_id,
                driver_id=st.driver_id,
                subject_type="ride_hailing_statement",
                subject_id=st.id,
            )
        )
    return result


def collection_gap(ctx: Context) -> RuleResult:
    """Recorded fixed-route collection below what the detected loops imply (U10)."""
    s = ctx.settings
    result = RuleResult()
    first = to_local_date(ctx.start)
    last = min(to_local_date(ctx.end), local_today() - timedelta(days=1))
    # Cases whose day is re-checked here and no longer short are cleared.
    result.scopes |= ctx.active_keys("COLLECTION_GAP")
    if last < first:
        return result
    for row in expected_revenue.compare(ctx.db, first, last):
        key = f"COLLECTION_GAP:{row.vehicle_id}:{row.day.isoformat()}"
        result.scopes.add(key)
        if row.status is not expected_revenue.CollectionStatus.SHORTFALL:
            continue
        expected = row.expected or Decimal("0")
        recorded = row.recorded
        severity = HIGH if expected > 0 and recorded * 2 < expected else MEDIUM
        start, end = local_day_bounds_utc(row.day)
        result.candidates.append(
            Candidate(
                rule_code="COLLECTION_GAP",
                severity=severity,
                summary=(
                    f"{expected_revenue.SHORTFALL_LABEL}: المتوقع {expected:,.2f} ج.م من "
                    f"{row.loops} دورة و{row.legs} اتجاه، والمسجل {recorded:,.2f} ج.م"
                ),
                evidence={
                    "day": row.day,
                    "routes": row.routes,
                    "loops": row.loops,
                    "legs": row.legs,
                    "rate_models": row.models,
                    "expected": expected,
                    "approved": row.approved,
                    "pending": row.pending,
                    "difference": row.difference,
                    "difference_pct": row.difference_pct,
                    "allowed": row.allowed,
                    "tolerance_pct": s.collection_tolerance_pct,
                    "tolerance_amount": s.collection_tolerance_amount,
                },
                occurred_at=start,
                occurred_until=end,
                dedupe_key=key,
                vehicle_id=row.vehicle_id,
                subject_type="vehicle",
                subject_id=row.vehicle_id,
            )
        )
    return result


Rule = Callable[[Context], RuleResult]

RULES: list[tuple[RuleInfo, Rule]] = [
    (
        RuleInfo(
            "GPS_DISABLED",
            "إيقاف الموقع أثناء الوردية",
            "الهاتف أبلغ عن إيقاف خدمة الموقع أو سحب الإذن أثناء وردية لمدة تتجاوز الحد.",
            R,
        ),
        gps_disabled,
    ),
    (
        RuleInfo(
            "GPS_GAP",
            "انقطاع بيانات الموقع",
            "فترات بدون نقاط موقع داخل وردية منتهية، مع المسافة التي تغيرت خلالها.",
            U,
        ),
        gps_gaps,
    ),
    (
        RuleInfo(
            "MOCK_LOCATION",
            "مصدر موقع وهمي",
            "الهاتف أبلغ أن الموقع صادر عن تطبيق محاكاة (Mock).",
            R,
        ),
        mock_location,
    ),
    (
        RuleInfo(
            "TRACKING_INTERRUPTED",
            "توقف خدمة التتبع أثناء الوردية",
            "توقف التتبع أو إعادة تشغيله (إغلاق التطبيق، إعادة تشغيل الهاتف) ومدة غياب التتبع.",
            R,
        ),
        tracking_interrupted,
    ),
    (
        RuleInfo(
            "IMPOSSIBLE_JUMP",
            "قفزة غير ممكنة في الموقع",
            "نقاط تتطلب سرعة أعلى من الحد للوصول إليها من النقطة السابقة؛ لا تُحسب في المسافة.",
            U,
        ),
        impossible_jumps,
    ),
    (
        RuleInfo(
            "LATE_GPS_UPLOAD",
            "وصول متأخر لبيانات الموقع",
            "نقاط وصلت للخادم بعد ساعات من تسجيلها؛ غالبًا بسبب انقطاع الإنترنت.",
            U,
        ),
        late_uploads,
    ),
    (
        RuleInfo(
            "OUT_OF_SHIFT_GPS",
            "نقاط موقع خارج وقت الوردية",
            "الهاتف أرسل نقاطًا مسجلة قبل بداية الوردية أو بعد نهايتها؛ رُفضت ولم تُخزن مواقعها.",
            U,
        ),
        out_of_shift_points,
    ),
    (
        RuleInfo(
            "TIMESTAMP_ANOMALY",
            "توقيت غير معتاد لبيانات الموقع",
            "ساعة الهاتف بعيدة عن ساعة الخادم، أو نقاط بتاريخ مستقبلي، أو دفعات تعود للخلف زمنيًا.",
            U,
        ),
        timestamp_anomalies,
    ),
    (
        RuleInfo(
            "LONG_STOP",
            "توقف طويل غير متوقع",
            "توقف أطول من الحد بعيدًا عن نقاط المسار المسجلة.",
            U,
        ),
        long_stops,
    ),
    (
        RuleInfo(
            "ROUTE_DEVIATION",
            "ابتعاد عن المسار",
            "ابتعاد عن الخطوط الواصلة بين نقاط المسار لأكثر من الحد ولمدة متصلة.",
            U,
        ),
        route_deviation,
    ),
    (
        RuleInfo(
            "OUTSIDE_AREA",
            "تشغيل خارج نطاق العمل",
            "نقاط موقع خارج نطاقات العمل المحددة في الإعدادات (معطلة إن لم تُحدد).",
            U,
        ),
        outside_area,
    ),
    (
        RuleInfo(
            "MOVED_BETWEEN_SHIFTS",
            "حركة المركبة بين الورديات",
            "زيادة العداد بين نهاية وردية وبداية التالية (بدون تتبع خارج الوردية).",
            R,
        ),
        moved_between_shifts,
    ),
    (
        RuleInfo(
            "IMPLAUSIBLE_ODOMETER",
            "قراءة عداد غير منطقية",
            "مسافة أكبر من الممكن خلال مدة الوردية، أو عداد يرجع للخلف.",
            R,
        ),
        implausible_odometer,
    ),
    (
        RuleInfo(
            "GPS_ODOMETER_MISMATCH",
            "فرق بين العداد وGPS",
            "فرق بين مسافة العداد ومسافة GPS يتجاوز الحد عند توفر تغطية GPS كافية.",
            R,
        ),
        gps_odometer_mismatch,
    ),
    (
        RuleInfo(
            "FUEL_CONSUMPTION",
            "استهلاك وقود غير معتاد",
            "تكلفة الوقود لكل كم في أسبوع أعلى من المعتاد للمركبة نفسها.",
            U,
        ),
        fuel_consumption,
    ),
    (
        RuleInfo(
            "FUEL_FAR",
            "وقود بعيد عن المركبة",
            "موقع تسجيل الوقود بعيد عن موقع المركبة في نفس الوقت (عند توفر الموقعين).",
            R,
        ),
        fuel_far_from_vehicle,
    ),
    (
        RuleInfo(
            "FUEL_OUTSIDE_SHIFT",
            "وقود خارج الوردية",
            "شراء وقود بواسطة السائق في وقت لا توجد فيه وردية للمركبة.",
            U,
        ),
        fuel_outside_shift,
    ),
    (
        RuleInfo(
            "DUPLICATE_FILE",
            "إيصال مكرر",
            "نفس الملف (نفس البصمة) مرفوع على أكثر من سجل.",
            R,
        ),
        duplicate_files,
    ),
    (
        RuleInfo(
            "DUPLICATE_TRANSACTION",
            "سجل مكرر محتمل",
            "سجلان بنفس المبلغ والنوع والمركبة في وقت متقارب.",
            R,
        ),
        duplicate_transactions,
    ),
    (
        RuleInfo(
            "COLLECTION_GAP",
            "فرق تحصيل",
            "التحصيل المسجل لخط ثابت أقل من المتوقع من الدورات المكتشفة بأكثر من الحد المسموح.",
            R,
        ),
        collection_gap,
    ),
    (
        RuleInfo(
            "REVENUE_INCONSISTENT",
            "إيراد غير متسق مع التشغيل",
            "كشف منصة بلا تشغيل مسجل، أو دخل لكل ساعة بعيد جدًا عن المعتاد.",
            U,
        ),
        revenue_inconsistent,
    ),
]

RULE_INFO: dict[str, RuleInfo] = {info.code: info for info, _ in RULES}


def rule_codes() -> Iterable[str]:
    return RULE_INFO.keys()


def is_enabled(code: str, settings: Settings) -> bool:
    if code == "OUTSIDE_AREA":
        return bool(parse_areas(settings.exception_operating_areas))
    return True


__all__ = [
    "RULES",
    "RULE_INFO",
    "Candidate",
    "Context",
    "RuleInfo",
    "RuleResult",
    "is_enabled",
    "parse_areas",
]
