"""Pure functions over ordered GPS points: distance, gaps and stops.

These never invent data: distance only sums consecutive VALID points that
are close in time; gaps are reported, not bridged.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime

from app.core.geo import haversine_m


@dataclass(frozen=True)
class TrackPoint:
    recorded_at: datetime
    latitude: float
    longitude: float
    accuracy_m: float | None = None
    speed_mps: float | None = None


@dataclass(frozen=True)
class Gap:
    start: datetime
    end: datetime
    seconds: int
    # Straight-line displacement across the gap (informational, NOT counted).
    displacement_m: float | None


@dataclass(frozen=True)
class Stop:
    start: datetime
    end: datetime
    seconds: int
    latitude: float
    longitude: float


def recorded_distance_m(points: list[TrackPoint], *, max_gap_seconds: int) -> float:
    total = 0.0
    for prev, cur in itertools.pairwise(points):
        if (cur.recorded_at - prev.recorded_at).total_seconds() > max_gap_seconds:
            continue
        total += haversine_m(prev.latitude, prev.longitude, cur.latitude, cur.longitude)
    return total


def find_gaps(
    points: list[TrackPoint],
    *,
    window_start: datetime,
    window_end: datetime,
    max_gap_seconds: int,
) -> list[Gap]:
    """Periods inside [window_start, window_end] with no point for longer than the threshold."""
    gaps: list[Gap] = []
    if not points:
        seconds = int((window_end - window_start).total_seconds())
        if seconds > max_gap_seconds:
            gaps.append(Gap(window_start, window_end, seconds, None))
        return gaps
    first, last = points[0], points[-1]
    lead = int((first.recorded_at - window_start).total_seconds())
    if lead > max_gap_seconds:
        gaps.append(Gap(window_start, first.recorded_at, lead, None))
    for prev, cur in itertools.pairwise(points):
        seconds = int((cur.recorded_at - prev.recorded_at).total_seconds())
        if seconds > max_gap_seconds:
            gaps.append(
                Gap(
                    prev.recorded_at,
                    cur.recorded_at,
                    seconds,
                    haversine_m(prev.latitude, prev.longitude, cur.latitude, cur.longitude),
                )
            )
    tail = int((window_end - last.recorded_at).total_seconds())
    if tail > max_gap_seconds:
        gaps.append(Gap(last.recorded_at, window_end, tail, None))
    return gaps


def find_stops(points: list[TrackPoint], *, radius_m: float, min_seconds: int) -> list[Stop]:
    """Clusters where the vehicle stayed within `radius_m` for at least `min_seconds`."""
    stops: list[Stop] = []
    i, n = 0, len(points)
    while i < n:
        anchor = points[i]
        j = i + 1
        while (
            j < n
            and haversine_m(
                anchor.latitude, anchor.longitude, points[j].latitude, points[j].longitude
            )
            <= radius_m
        ):
            j += 1
        cluster = points[i:j]
        seconds = int((cluster[-1].recorded_at - cluster[0].recorded_at).total_seconds())
        if len(cluster) >= 2 and seconds >= min_seconds:
            lat = sum(p.latitude for p in cluster) / len(cluster)
            lon = sum(p.longitude for p in cluster) / len(cluster)
            stops.append(Stop(cluster[0].recorded_at, cluster[-1].recorded_at, seconds, lat, lon))
            i = j
        else:
            i += 1
    return stops
