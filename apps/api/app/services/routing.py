"""Road-aware route geometry (U07), with a replaceable provider.

A route is a list of stops. To judge whether a vehicle left its route, the
system needs the line the vehicle is expected to follow:

- `straight_line` (default): straight lines between the stops, as before.
  Honest but crude: a road that curves away from the straight line looks
  like a deviation, so the corridor must be wide.
- `osrm`: the road path from a routing server speaking the OSRM route API
  (`ROUTING_URL`; self-hosted OSRM or a licensed provider compatible with
  it). Answers are cached per route version.

Any provider failure (not configured, timeout, error, bad answer) falls back
to straight lines for that call, and the result says so; nothing pretends to
be road-aware when it is not. Snapping GPS points to roads (map matching) is
not done: no provider is configured, and raw points stay as recorded.
"""

from __future__ import annotations

import itertools
import json
import logging
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.geo import haversine_m
from app.models.operations import RouteDefinition, RouteGeometry, RouteVersion

logger = logging.getLogger(__name__)

Point = tuple[float, float]


class RoutingError(Exception):
    """The provider could not give a route (the caller falls back)."""


@dataclass(frozen=True)
class Geometry:
    points: list[Point]
    distance_m: float
    provider: str
    road_aware: bool
    fallback_reason: str | None = None

    @property
    def method_ar(self) -> str:
        if self.road_aware:
            return f"مسار على شبكة الطرق ({self.provider})"
        if self.fallback_reason:
            return "خطوط مستقيمة بين نقاط المسار (تعذر الحصول على مسار الطرق)"
        return "خطوط مستقيمة بين نقاط المسار وليست شبكة الطرق"


class RoutingProvider(Protocol):
    code: str

    def route(self, stops: list[Point]) -> Geometry: ...


def _length(points: list[Point]) -> float:
    return sum(haversine_m(a[0], a[1], b[0], b[1]) for a, b in itertools.pairwise(points))


class StraightLine:
    code = "straight_line"

    def route(self, stops: list[Point]) -> Geometry:
        return Geometry(list(stops), _length(stops), self.code, road_aware=False)


Fetch = Callable[[str, float], bytes]


def _fetch(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "go-daily-routing"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        body: bytes = response.read(5_000_000)
        return body


class OsrmRoute:
    """`GET {base}/route/v1/{profile}/{lon,lat;...}?overview=full&geometries=geojson`."""

    code = "osrm"

    def __init__(self, base_url: str, profile: str, timeout: float, fetch: Fetch = _fetch) -> None:
        if not base_url.startswith(("https://", "http://")):
            raise RoutingError("ROUTING_URL must be an http(s) URL")
        self.base_url = base_url.rstrip("/")
        self.profile = profile
        self.timeout = timeout
        self.fetch = fetch

    def route(self, stops: list[Point]) -> Geometry:
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in stops)
        url = (
            f"{self.base_url}/route/v1/{self.profile}/{coords}"
            "?overview=full&geometries=geojson&steps=false"
        )
        try:
            data = json.loads(self.fetch(url, self.timeout))
            if data.get("code") != "Ok" or not data.get("routes"):
                raise RoutingError(f"provider answered {data.get('code')}")
            best = data["routes"][0]
            points = [(float(lat), float(lon)) for lon, lat in best["geometry"]["coordinates"]]
            distance = float(best["distance"])
        except RoutingError:
            raise
        except Exception as exc:  # timeout, network, malformed answer
            raise RoutingError(type(exc).__name__) from exc
        if len(points) < 2 or distance <= 0:
            raise RoutingError("empty geometry")
        return Geometry(points, distance, self.code, road_aware=True)


def provider(settings: Settings | None = None, fetch: Fetch = _fetch) -> RoutingProvider:
    s = settings or get_settings()
    if s.routing_provider == "osrm" and s.routing_url:
        try:
            return OsrmRoute(s.routing_url, s.routing_profile, s.routing_timeout_seconds, fetch)
        except RoutingError:
            logger.warning("routing_misconfigured", extra={"provider": "osrm"})
    return StraightLine()


def _stops(route: RouteDefinition) -> list[Point]:
    return [
        (float(st.latitude), float(st.longitude))
        for st in route.stops
        if st.latitude is not None and st.longitude is not None
    ]


def _latest_version(db: Session, route_id: object) -> int:
    version = db.scalar(
        select(RouteVersion.version)
        .where(RouteVersion.route_id == route_id)
        .order_by(RouteVersion.version.desc())
        .limit(1)
    )
    return int(version or 0)


def geometry(
    db: Session, route: RouteDefinition, *, source: RoutingProvider | None = None
) -> Geometry | None:
    """The expected line of a route's current version; None with fewer than 2 located stops."""
    stops = _stops(route)
    if len(stops) < 2:
        return None
    chosen = source or provider()
    straight = StraightLine().route(stops)
    if chosen.code == StraightLine.code:
        return straight
    version = _latest_version(db, route.id)
    cached = db.scalar(
        select(RouteGeometry).where(
            RouteGeometry.route_id == route.id,
            RouteGeometry.route_version == version,
            RouteGeometry.provider == chosen.code,
        )
    )
    if cached is not None:
        return Geometry(
            [(p[0], p[1]) for p in cached.points], cached.distance_m, cached.provider, True
        )
    try:
        found = chosen.route(stops)
    except RoutingError as exc:
        logger.warning("routing_fallback", extra={"provider": chosen.code, "reason": str(exc)})
        return Geometry(
            straight.points,
            straight.distance_m,
            StraightLine.code,
            road_aware=False,
            fallback_reason=str(exc)[:120],
        )
    try:
        with db.begin_nested():
            db.add(
                RouteGeometry(
                    route_id=route.id,
                    route_version=version,
                    provider=found.provider,
                    points=[[lat, lon] for lat, lon in found.points],
                    distance_m=found.distance_m,
                )
            )
    except IntegrityError:
        pass  # cached concurrently by another request: same answer
    return found


__all__ = ["Geometry", "OsrmRoute", "RoutingError", "StraightLine", "geometry", "provider"]
