"""Road-aware route geometry (U07): replaceable provider, cache and fallback."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import UserRole
from app.models.operations import RouteGeometry
from app.services import exception_rules as rules
from app.services import route_versions, routing
from tests.factories import login_as, make_completed_shift
from tests.test_exceptions import YESTERDAY, _route, add_points, codes, ctx_around, offset, pair

# The road goes north 4.5 km, east 10 km, then back south: far from the straight line.
DETOUR = [
    offset(),
    offset(north_m=4500),
    offset(north_m=4500, east_m=10_000),
    offset(east_m=10_000),
]


def _answer(points: list[tuple[float, float]], distance: float = 19_000) -> bytes:
    return json.dumps(
        {
            "code": "Ok",
            "routes": [
                {
                    "distance": distance,
                    "geometry": {"coordinates": [[lon, lat] for lat, lon in points]},
                }
            ],
        }
    ).encode()


class FakeServer:
    def __init__(self, body: bytes | Exception) -> None:
        self.body = body
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float) -> bytes:
        self.calls.append(url)
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


@pytest.fixture()
def osrm(monkeypatch: pytest.MonkeyPatch) -> FakeServer:
    server = FakeServer(_answer(DETOUR))
    monkeypatch.setattr(get_settings(), "routing_provider", "osrm")
    monkeypatch.setattr(get_settings(), "routing_url", "https://routing.example.invalid")
    real = routing.provider
    monkeypatch.setattr(routing, "provider", lambda settings=None: real(settings, fetch=server))
    return server


def test_straight_lines_by_default(db: Session) -> None:
    route = _route(db, [offset(), offset(east_m=10_000)])
    geo = routing.geometry(db, route)
    assert geo is not None and not geo.road_aware and geo.provider == "straight_line"
    assert geo.distance_m == pytest.approx(10_000, rel=0.005)
    assert "خطوط مستقيمة" in geo.method_ar
    assert db.scalar(select(func.count()).select_from(RouteGeometry)) == 0  # never cached


def test_provider_answer_is_cached_per_route_version(
    db: Session, osrm: FakeServer, client: TestClient
) -> None:
    route = _route(db, [offset(), offset(east_m=10_000)])
    db.commit()
    db.refresh(route)
    route_versions.record(db, route, None)
    geo = routing.geometry(db, route)
    assert geo is not None and geo.road_aware and geo.provider == "osrm"
    assert geo.distance_m == 19_000 and len(geo.points) == 4
    assert "/route/v1/driving/" in osrm.calls[0]
    routing.geometry(db, route)
    assert len(osrm.calls) == 1  # from the cache
    route_versions.record(db, route, None)  # an edit: new version, new geometry
    routing.geometry(db, route)
    assert len(osrm.calls) == 2

    _, ops = login_as(client, db, UserRole.OPERATIONS)
    body = client.get(f"/api/v1/routes/{route.id}/geometry", headers=ops)
    assert body.status_code == 200, body.text
    assert body.json()["road_aware"] is True and "شبكة الطرق" in body.json()["method"]


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("timed out"), json.dumps({"code": "NoRoute"}).encode(), b"not json"],
)
def test_failures_fall_back_to_straight_lines(db: Session, osrm: FakeServer, failure: Any) -> None:
    osrm.body = failure
    route = _route(db, [offset(), offset(east_m=10_000)])
    geo = routing.geometry(db, route)
    assert geo is not None and not geo.road_aware and geo.fallback_reason
    assert "تعذر" in geo.method_ar
    assert db.scalar(select(func.count()).select_from(RouteGeometry)) == 0


def test_misconfigured_url_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "routing_provider", "osrm")
    monkeypatch.setattr(get_settings(), "routing_url", "ftp://nope")
    assert routing.provider().code == "straight_line"


def test_deviation_follows_the_road_when_known(db: Session, osrm: FakeServer) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=60)
    assert shift.started_at
    shift.sessions[0].route = _route(db, [offset(), offset(east_m=10_000)])
    db.commit()

    # The vehicle drives the road: north, east along the top, south.
    def along_road(i: int) -> tuple[float, float]:
        if i <= 15:
            return offset(north_m=i * 300)
        if i <= 40:
            return offset(north_m=4500, east_m=(i - 15) * 400)
        return offset(north_m=max(0, 4500 - (i - 40) * 300), east_m=10_000)

    add_points(db, shift, shift.started_at, minutes=55, where=along_road)
    road = rules.route_deviation(ctx_around(db, shift))
    assert codes(road) == []  # on the road: no deviation

    osrm.body = TimeoutError("timed out")  # no provider answer and nothing cached
    db.query(RouteGeometry).delete()
    straight = rules.route_deviation(ctx_around(db, shift))
    assert codes(straight) == ["ROUTE_DEVIATION"]
    evidence = straight.candidates[0].evidence
    assert evidence["routing_provider"] == "straight_line" and evidence["routing_fallback"]
    assert "تعذر" in evidence["method"]
