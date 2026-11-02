from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from app.models.operations import StopKind, TripPattern
from app.models.route_events import LegDirection, RouteEventType
from app.services.geofence import DetectionParams, Geofence, detect_route_events
from app.services.track_analysis import TrackPoint

STATION = (31.0409, 31.3785)
UNIVERSITY = (31.0409, 31.3520)  # ~2.5 km west
MIDPOINT = (31.0409, 31.3650)
T0 = datetime(2026, 3, 1, 6, 30, tzinfo=UTC)

ORIGIN = Geofence(uuid.uuid4(), StopKind.ORIGIN, *STATION, radius_m=120)
DEST = Geofence(uuid.uuid4(), StopKind.DESTINATION, *UNIVERSITY, radius_m=150)
MID = Geofence(uuid.uuid4(), StopKind.INTERMEDIATE, *MIDPOINT, radius_m=80)


class Track:
    """Builds a synthetic track with points every `step` seconds."""

    def __init__(self, step: int = 15) -> None:
        self.t = T0
        self.step = step
        self.points: list[TrackPoint] = []

    def dwell(self, at: tuple[float, float], seconds: int, accuracy: float = 8) -> Track:
        for _ in range(seconds // self.step):
            self.points.append(TrackPoint(self.t, at[0], at[1], accuracy))
            self.t += timedelta(seconds=self.step)
        return self

    def drive(self, a: tuple[float, float], b: tuple[float, float], seconds: int) -> Track:
        n = max(2, seconds // self.step)
        for i in range(1, n + 1):
            f = i / n
            self.points.append(
                TrackPoint(self.t, a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, 8)
            )
            self.t += timedelta(seconds=self.step)
        return self


def _types(events):
    return [e.event_type for e in events]


def test_counts_repeated_station_university_loops() -> None:
    track = Track().dwell(STATION, 120)
    for _ in range(3):
        track.drive(STATION, UNIVERSITY, 300).dwell(UNIVERSITY, 120)
        track.drive(UNIVERSITY, STATION, 300).dwell(STATION, 120)
    events = detect_route_events(track.points, [ORIGIN, DEST], pattern=TripPattern.ROUND_TRIP)
    counts = Counter(_types(events))
    assert counts[RouteEventType.LOOP_COMPLETED] == 3
    assert counts[RouteEventType.LEG_COMPLETED] == 6
    assert counts[RouteEventType.REACHED_DESTINATION] == 3
    assert counts[RouteEventType.REACHED_ORIGIN] == 4  # includes the initial arrival
    legs = [e for e in events if e.event_type is RouteEventType.LEG_COMPLETED]
    assert [e.direction for e in legs] == [LegDirection.OUTBOUND, LegDirection.INBOUND] * 3
    loops = [e for e in events if e.event_type is RouteEventType.LOOP_COMPLETED]
    assert [e.sequence_no for e in loops] == [1, 2, 3]


def test_detection_is_deterministic() -> None:
    track = Track().dwell(STATION, 60).drive(STATION, UNIVERSITY, 300).dwell(UNIVERSITY, 60)
    track.drive(UNIVERSITY, STATION, 300).dwell(STATION, 60)
    a = detect_route_events(track.points, [ORIGIN, DEST], pattern=TripPattern.ROUND_TRIP)
    b = detect_route_events(track.points, [ORIGIN, DEST], pattern=TripPattern.ROUND_TRIP)
    assert a == b


def test_single_jitter_point_does_not_trigger_entry() -> None:
    track = Track().dwell(STATION, 60).drive(STATION, MIDPOINT, 150)
    # One noisy point lands inside the university geofence, then the vehicle returns.
    track.points.append(TrackPoint(track.t, *UNIVERSITY, 8))
    track.t += timedelta(seconds=15)
    track.drive(MIDPOINT, STATION, 150).dwell(STATION, 60)
    events = detect_route_events(track.points, [ORIGIN, DEST], pattern=TripPattern.ROUND_TRIP)
    assert RouteEventType.REACHED_DESTINATION not in _types(events)
    assert RouteEventType.LEG_COMPLETED not in _types(events)


def test_low_accuracy_points_are_ignored() -> None:
    track = Track().dwell(STATION, 60).drive(STATION, MIDPOINT, 150)
    track.dwell(UNIVERSITY, 120, accuracy=400)  # very imprecise fixes "at" the university
    track.drive(MIDPOINT, STATION, 150).dwell(STATION, 60)
    events = detect_route_events(track.points, [ORIGIN, DEST], pattern=TripPattern.ROUND_TRIP)
    assert RouteEventType.REACHED_DESTINATION not in _types(events)


def test_dwell_threshold_requires_time_inside() -> None:
    track = Track(step=5).dwell(STATION, 10)  # 2 points, only 5 s apart
    events = detect_route_events(
        track.points,
        [ORIGIN],
        pattern=TripPattern.ROUND_TRIP,
        params=DetectionParams(dwell_seconds=20),
    )
    assert events == []


def test_intermediate_stop_entries_and_exits() -> None:
    track = Track().dwell(STATION, 60).drive(STATION, MIDPOINT, 150).dwell(MIDPOINT, 60)
    track.drive(MIDPOINT, UNIVERSITY, 150).dwell(UNIVERSITY, 60)
    events = detect_route_events(track.points, [ORIGIN, MID, DEST], pattern=TripPattern.ROUND_TRIP)
    mid_events = [e.event_type for e in events if e.stop_id == MID.stop_id]
    assert mid_events == [RouteEventType.ENTERED, RouteEventType.EXITED]
    assert Counter(_types(events))[RouteEventType.LEG_COMPLETED] == 1


def test_session_starting_at_destination_pairs_legs() -> None:
    track = Track().dwell(UNIVERSITY, 60).drive(UNIVERSITY, STATION, 300).dwell(STATION, 60)
    track.drive(STATION, UNIVERSITY, 300).dwell(UNIVERSITY, 60)
    events = detect_route_events(track.points, [ORIGIN, DEST], pattern=TripPattern.ROUND_TRIP)
    legs = [e.direction for e in events if e.event_type is RouteEventType.LEG_COMPLETED]
    assert legs == [LegDirection.INBOUND, LegDirection.OUTBOUND]
    assert Counter(_types(events))[RouteEventType.LOOP_COMPLETED] == 1


def test_one_way_routes_count_legs_not_loops() -> None:
    track = Track().dwell(STATION, 60).drive(STATION, UNIVERSITY, 300).dwell(UNIVERSITY, 60)
    track.drive(UNIVERSITY, STATION, 300).dwell(STATION, 60)
    events = detect_route_events(track.points, [ORIGIN, DEST], pattern=TripPattern.ONE_WAY)
    counts = Counter(_types(events))
    assert counts[RouteEventType.LEG_COMPLETED] == 2
    assert counts[RouteEventType.LOOP_COMPLETED] == 0


def test_returning_to_same_terminal_is_not_a_leg() -> None:
    track = Track().dwell(STATION, 60).drive(STATION, MIDPOINT, 150).drive(MIDPOINT, STATION, 150)
    track.dwell(STATION, 60)
    events = detect_route_events(track.points, [ORIGIN, DEST], pattern=TripPattern.ROUND_TRIP)
    assert RouteEventType.LEG_COMPLETED not in _types(events)
    assert Counter(_types(events))[RouteEventType.REACHED_ORIGIN] == 2


def test_event_time_is_first_point_inside() -> None:
    track = Track().drive(MIDPOINT, STATION, 150).dwell(STATION, 60)
    events = detect_route_events(track.points, [ORIGIN], pattern=TripPattern.ROUND_TRIP)
    entered = next(e for e in events if e.event_type is RouteEventType.ENTERED)
    first_inside = next(
        p.recorded_at for p in track.points if abs(p.longitude - STATION[1]) < 0.0012
    )
    assert entered.occurred_at == first_inside


# --- U09: minimum travel time, incomplete legs, leg evidence -------------------


def _of(events, kind: RouteEventType):
    return [e for e in events if e.event_type is kind]


def test_a_leg_faster_than_the_minimum_is_kept_but_not_counted() -> None:
    track = Track().dwell(STATION, 120).drive(STATION, UNIVERSITY, 60).dwell(UNIVERSITY, 120)
    events = detect_route_events(track.points, [ORIGIN, DEST], pattern=TripPattern.ROUND_TRIP)
    assert _of(events, RouteEventType.LEG_COMPLETED) == []
    [rejected] = _of(events, RouteEventType.LEG_REJECTED)
    assert rejected.details is not None
    assert rejected.details["reason"] == "faster_than_minimum"
    assert rejected.details["seconds"] < 180 and rejected.details["min_seconds"] == 180
    # The minimum is a parameter (route_min_leg_minutes in settings).
    relaxed = detect_route_events(
        track.points,
        [ORIGIN, DEST],
        pattern=TripPattern.ROUND_TRIP,
        params=DetectionParams(min_leg_seconds=30),
    )
    assert len(_of(relaxed, RouteEventType.LEG_COMPLETED)) == 1


def test_returning_to_the_start_terminal_is_an_incomplete_leg() -> None:
    track = (
        Track()
        .dwell(STATION, 120)
        .drive(STATION, MIDPOINT, 300)
        .drive(MIDPOINT, STATION, 300)
        .dwell(STATION, 120)
    )
    events = detect_route_events(track.points, [ORIGIN, DEST], pattern=TripPattern.ROUND_TRIP)
    [leg] = _of(events, RouteEventType.LEG_INCOMPLETE)
    assert leg.details is not None and leg.details["reason"] == "returned_to_start"
    assert leg.direction is LegDirection.OUTBOUND
    assert _of(events, RouteEventType.LEG_COMPLETED) == []


def test_a_short_excursion_from_the_terminal_is_noise() -> None:
    near = (STATION[0], STATION[1] - 0.002)  # ~190 m: just outside the 120 m fence
    track = (
        Track()
        .dwell(STATION, 120)
        .drive(STATION, near, 45)
        .drive(near, STATION, 45)
        .dwell(STATION, 60)
    )
    events = detect_route_events(track.points, [ORIGIN, DEST], pattern=TripPattern.ROUND_TRIP)
    assert _of(events, RouteEventType.LEG_INCOMPLETE) == []
    assert _of(events, RouteEventType.LEG_REJECTED) == []


def test_an_open_leg_becomes_incomplete_only_when_the_session_ends() -> None:
    track = Track().dwell(STATION, 120).drive(STATION, MIDPOINT, 400)
    live = detect_route_events(track.points, [ORIGIN, DEST], pattern=TripPattern.ROUND_TRIP)
    assert _of(live, RouteEventType.LEG_INCOMPLETE) == []  # still driving
    ended = detect_route_events(
        track.points, [ORIGIN, DEST], pattern=TripPattern.ROUND_TRIP, ended_at=track.t
    )
    [leg] = _of(ended, RouteEventType.LEG_INCOMPLETE)
    assert leg.details is not None and leg.details["reason"] == "session_ended"
    assert leg.details["to_stop_id"] is None


def test_completed_legs_carry_their_evidence() -> None:
    origin = Geofence(uuid.uuid4(), StopKind.ORIGIN, *STATION, radius_m=120, sequence=1)
    mid = Geofence(uuid.uuid4(), StopKind.INTERMEDIATE, *MIDPOINT, radius_m=80, sequence=2)
    dest = Geofence(uuid.uuid4(), StopKind.DESTINATION, *UNIVERSITY, radius_m=150, sequence=3)
    track = (
        Track()
        .dwell(STATION, 120)
        .drive(STATION, MIDPOINT, 150)
        .dwell(MIDPOINT, 60)
        .drive(MIDPOINT, UNIVERSITY, 150)
        .dwell(UNIVERSITY, 120)
    )
    events = detect_route_events(track.points, [origin, mid, dest], pattern=TripPattern.ROUND_TRIP)
    [leg] = _of(events, RouteEventType.LEG_COMPLETED)
    assert leg.details is not None
    assert leg.details["from_stop_id"] == str(origin.stop_id)
    assert leg.details["to_stop_id"] == str(dest.stop_id)
    assert leg.details["visited_stop_ids"] == [str(mid.stop_id)]
    assert leg.details["in_route_order"] is True
    assert 300 <= leg.details["seconds"] <= 420
    # Same points, same result: re-running never changes the evidence.
    again = detect_route_events(track.points, [origin, mid, dest], pattern=TripPattern.ROUND_TRIP)
    assert again == events
