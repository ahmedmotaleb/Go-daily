"""Geographic helpers (WGS84)."""

from __future__ import annotations

import itertools
import math

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def point_to_segment_m(
    lat: float, lon: float, a: tuple[float, float], b: tuple[float, float]
) -> float:
    """Distance from a point to the segment a-b, in metres.

    Uses a local equirectangular projection around the point, which is
    accurate to well under 1% for the city-scale distances it is used for.
    """
    k = math.cos(math.radians(lat))

    def project(p: tuple[float, float]) -> tuple[float, float]:
        return (
            math.radians(p[1] - lon) * k * EARTH_RADIUS_M,
            math.radians(p[0] - lat) * EARTH_RADIUS_M,
        )

    ax, ay = project(a)
    bx, by = project(b)
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length2))
    return math.hypot(ax + t * dx, ay + t * dy)


def point_to_polyline_m(lat: float, lon: float, line: list[tuple[float, float]]) -> float:
    """Distance from a point to the nearest segment of a polyline (>= 1 vertex)."""
    if len(line) == 1:
        return haversine_m(lat, lon, line[0][0], line[0][1])
    return min(point_to_segment_m(lat, lon, a, b) for a, b in itertools.pairwise(line))
