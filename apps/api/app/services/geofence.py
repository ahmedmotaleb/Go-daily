"""Geofence and fixed-route loop detection (pure, deterministic).

Input: time-ordered VALID GPS points of one operation session and the
route's stops (each a circular geofence). Output: entry/exit, terminal
arrival, leg and loop events.

Noise protection:
- points whose reported accuracy is worse than `max_accuracy_m`, or worse
  than the geofence radius itself, are ignored;
- an entry (or exit) is confirmed only after `min_points` consecutive
  points AND `dwell_seconds` inside (or outside) the geofence;
- events are timestamped at the first point of the confirmed run, so
  re-running over the same points always yields the same events.

Loops (ROUND_TRIP routes): a leg is a trip from one terminal (origin or
destination) to the other. A loop completes when a leg ends at the
terminal where the previous uncounted leg started (A->B then B->A).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.core.geo import haversine_m
from app.models.operations import StopKind, TripPattern
from app.models.route_events import LegDirection, RouteEventType
from app.services.track_analysis import TrackPoint


@dataclass(frozen=True)
class Geofence:
    stop_id: uuid.UUID
    kind: StopKind
    latitude: float
    longitude: float
    radius_m: float


@dataclass(frozen=True)
class DetectionParams:
    max_accuracy_m: float = 50.0
    dwell_seconds: int = 20
    min_points: int = 2


@dataclass(frozen=True)
class DetectedEvent:
    event_type: RouteEventType
    occurred_at: datetime
    stop_id: uuid.UUID | None = None
    direction: LegDirection | None = None
    sequence_no: int | None = None


@dataclass
class _Run:
    """A run of consecutive points supporting an entry or exit."""

    target: uuid.UUID | None
    first: datetime
    count: int = 1


@dataclass
class _State:
    inside: Geofence | None = None
    pending: _Run | None = None
    leg_start: StopKind | None = None
    unpaired_leg: LegDirection | None = None
    legs: int = 0
    loops: int = 0
    events: list[DetectedEvent] = field(default_factory=list)


def _containing(point: TrackPoint, fences: list[Geofence]) -> Geofence | None:
    best: tuple[float, Geofence] | None = None
    for fence in fences:
        if point.accuracy_m is not None and point.accuracy_m > fence.radius_m:
            continue  # too imprecise to decide membership of this geofence
        d = haversine_m(point.latitude, point.longitude, fence.latitude, fence.longitude)
        if d <= fence.radius_m and (best is None or d < best[0]):
            best = (d, fence)
    return best[1] if best else None


def _confirmed(run: _Run, now: datetime, params: DetectionParams) -> bool:
    return (
        run.count >= params.min_points and (now - run.first).total_seconds() >= params.dwell_seconds
    )


def _on_enter(state: _State, fence: Geofence, at: datetime, pattern: TripPattern) -> None:
    state.events.append(DetectedEvent(RouteEventType.ENTERED, at, fence.stop_id))
    if fence.kind is StopKind.INTERMEDIATE:
        return
    reached = (
        RouteEventType.REACHED_ORIGIN
        if fence.kind is StopKind.ORIGIN
        else RouteEventType.REACHED_DESTINATION
    )
    state.events.append(DetectedEvent(reached, at, fence.stop_id))
    if state.leg_start is None or state.leg_start is fence.kind:
        return
    direction = (
        LegDirection.OUTBOUND if state.leg_start is StopKind.ORIGIN else LegDirection.INBOUND
    )
    state.legs += 1
    state.events.append(
        DetectedEvent(RouteEventType.LEG_COMPLETED, at, None, direction, state.legs)
    )
    state.leg_start = None
    if pattern is not TripPattern.ROUND_TRIP:
        return
    if state.unpaired_leg is not None and state.unpaired_leg is not direction:
        state.loops += 1
        state.events.append(
            DetectedEvent(RouteEventType.LOOP_COMPLETED, at, None, direction, state.loops)
        )
        state.unpaired_leg = None
    else:
        state.unpaired_leg = direction


def _on_exit(state: _State, fence: Geofence, at: datetime) -> None:
    state.events.append(DetectedEvent(RouteEventType.EXITED, at, fence.stop_id))
    if fence.kind is not StopKind.INTERMEDIATE:
        state.leg_start = fence.kind


def detect_route_events(
    points: list[TrackPoint],
    fences: list[Geofence],
    *,
    pattern: TripPattern,
    params: DetectionParams | None = None,
) -> list[DetectedEvent]:
    params = params or DetectionParams()
    usable = [f for f in fences if f.radius_m > 0]
    state = _State()
    for point in points:
        if point.accuracy_m is not None and point.accuracy_m > params.max_accuracy_m:
            continue
        fence = _containing(point, usable)
        target = fence.stop_id if fence else None
        if state.inside is None:
            if fence is None:
                state.pending = None
                continue
            if state.pending is None or state.pending.target != target:
                state.pending = _Run(target, point.recorded_at)
            else:
                state.pending.count += 1
            if _confirmed(state.pending, point.recorded_at, params):
                state.inside = fence
                _on_enter(state, fence, state.pending.first, pattern)
                state.pending = None
            continue

        if target == state.inside.stop_id:
            state.pending = None  # still inside; cancel any exit run
            continue
        if state.pending is None:
            state.pending = _Run(None, point.recorded_at)
        else:
            state.pending.count += 1
        if _confirmed(state.pending, point.recorded_at, params):
            _on_exit(state, state.inside, state.pending.first)
            state.inside = None
            # The point may already be inside another geofence: start its entry run.
            state.pending = _Run(target, point.recorded_at) if fence else None
    return state.events
