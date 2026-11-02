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

Legs (U09):
- a leg faster than `min_leg_seconds` is not counted (two terminals that
  are close or overlap can make GPS noise look like a trip); it is kept
  as LEG_REJECTED with the measured time, so nothing disappears silently;
- a leg that returns to its own terminal after at least `min_leg_seconds`,
  or is still open when the session has ended, is LEG_INCOMPLETE;
- every leg carries its evidence: duration, start and end terminal, the
  intermediate stops visited and whether they were visited in route order.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

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
    # Position in the route (1 = origin); used to check intermediate stop order.
    sequence: int = 0


@dataclass(frozen=True)
class DetectionParams:
    max_accuracy_m: float = 50.0
    dwell_seconds: int = 20
    min_points: int = 2
    # Minimum travel time between the two terminals for a leg to count.
    min_leg_seconds: int = 180


@dataclass(frozen=True)
class DetectedEvent:
    event_type: RouteEventType
    occurred_at: datetime
    stop_id: uuid.UUID | None = None
    direction: LegDirection | None = None
    sequence_no: int | None = None
    details: dict[str, Any] | None = None


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
    leg_from: Geofence | None = None
    leg_started_at: datetime | None = None
    visited: list[Geofence] = field(default_factory=list)
    unpaired_leg: LegDirection | None = None
    legs: int = 0
    loops: int = 0
    events: list[DetectedEvent] = field(default_factory=list)

    def reset_leg(self) -> None:
        self.leg_start = None
        self.leg_from = None
        self.leg_started_at = None
        self.visited = []


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


def _leg_details(state: _State, end: Geofence | None, at: datetime) -> dict[str, Any]:
    started = state.leg_started_at
    visited = [f.sequence for f in state.visited]
    outbound = state.leg_start is StopKind.ORIGIN
    expected = sorted(visited) if outbound else sorted(visited, reverse=True)
    return {
        "started_at": started.isoformat() if started else None,
        "seconds": int((at - started).total_seconds()) if started else None,
        "from_stop_id": str(state.leg_from.stop_id) if state.leg_from else None,
        "to_stop_id": str(end.stop_id) if end else None,
        "visited_stop_ids": [str(f.stop_id) for f in state.visited],
        "in_route_order": visited == expected,
    }


def _on_enter(
    state: _State, fence: Geofence, at: datetime, pattern: TripPattern, params: DetectionParams
) -> None:
    state.events.append(DetectedEvent(RouteEventType.ENTERED, at, fence.stop_id))
    if fence.kind is StopKind.INTERMEDIATE:
        if state.leg_start is not None and fence not in state.visited:
            state.visited.append(fence)
        return
    reached = (
        RouteEventType.REACHED_ORIGIN
        if fence.kind is StopKind.ORIGIN
        else RouteEventType.REACHED_DESTINATION
    )
    state.events.append(DetectedEvent(reached, at, fence.stop_id))
    if state.leg_start is None or state.leg_started_at is None:
        return
    seconds = (at - state.leg_started_at).total_seconds()
    direction = (
        LegDirection.OUTBOUND if state.leg_start is StopKind.ORIGIN else LegDirection.INBOUND
    )
    if state.leg_start is fence.kind:
        # Back at the terminal it left. A short excursion is GPS noise or
        # manoeuvring; a real trip that never reached the other end is kept.
        if seconds >= params.min_leg_seconds:
            details = {**_leg_details(state, fence, at), "reason": "returned_to_start"}
            state.events.append(
                DetectedEvent(
                    RouteEventType.LEG_INCOMPLETE,
                    state.leg_started_at,
                    None,
                    direction,
                    None,
                    details,
                )
            )
        state.reset_leg()
        return
    details = _leg_details(state, fence, at)
    if seconds < params.min_leg_seconds:
        details["reason"] = "faster_than_minimum"
        details["min_seconds"] = params.min_leg_seconds
        state.events.append(
            DetectedEvent(RouteEventType.LEG_REJECTED, at, None, direction, None, details)
        )
        state.reset_leg()
        return
    state.legs += 1
    state.events.append(
        DetectedEvent(RouteEventType.LEG_COMPLETED, at, None, direction, state.legs, details)
    )
    state.reset_leg()
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
        state.leg_from = fence
        state.leg_started_at = at
        state.visited = []


def detect_route_events(
    points: list[TrackPoint],
    fences: list[Geofence],
    *,
    pattern: TripPattern,
    params: DetectionParams | None = None,
    ended_at: datetime | None = None,
) -> list[DetectedEvent]:
    """Detect events; pass `ended_at` once the session has ended to close open legs."""
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
                _on_enter(state, fence, state.pending.first, pattern, params)
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
    if (
        ended_at is not None
        and state.leg_start is not None
        and state.leg_started_at is not None
        and (ended_at - state.leg_started_at).total_seconds() >= params.min_leg_seconds
    ):
        direction = (
            LegDirection.OUTBOUND if state.leg_start is StopKind.ORIGIN else LegDirection.INBOUND
        )
        details = {**_leg_details(state, None, ended_at), "reason": "session_ended"}
        state.events.append(
            DetectedEvent(
                RouteEventType.LEG_INCOMPLETE, state.leg_started_at, None, direction, None, details
            )
        )
    return state.events
