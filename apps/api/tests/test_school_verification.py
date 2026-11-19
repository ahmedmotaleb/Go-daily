"""School route verification outcomes (U12)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from app.models.operations import RouteDefinition, RouteStop
from app.models.route_events import SchoolRun
from tests.factories import login_as, make_driver_account
from tests.test_route_events_api import (
    SCHOOL,
    STATION,
    _points,
    _route,
    _start_backdated,
    _upload,
)

OFF_PATH = (31.0700, 31.3740)  # ~3 km north of the station-school line


def _setup(
    client: TestClient,
    db: Session,
    *,
    start_offset_min: int = -35,
    end_offset_min: int = 30,
    extra_stop: tuple[float, float] | None = None,
) -> dict[str, Any]:
    driver, _, h, vehicle = make_driver_account(client, db)
    _, staff = login_as(client, db, UserRole.OPERATIONS)
    route = _route(db, "SCHOOL_ROUTE", STATION, SCHOOL, "مدرسة — تحقق")
    if extra_stop:
        _add_intermediate(db, route, extra_stop)
    gen = client.post(
        "/api/v1/school-runs/generate",
        headers=staff,
        json={
            "route_id": str(route.id),
            "date_from": local_today().isoformat(),
            "date_to": local_today().isoformat(),
            "start_time": "00:00:00",
            "end_time": "23:59:00",
            "vehicle_id": str(vehicle.id),
        },
    )
    assert gen.status_code == 201, gen.text
    run = db.scalars(select(SchoolRun).where(SchoolRun.vehicle_id == vehicle.id)).one()
    run.scheduled_start_at = utcnow() + timedelta(minutes=start_offset_min)
    run.scheduled_end_at = utcnow() + timedelta(minutes=end_offset_min)
    db.commit()
    ctx = _start_backdated(client, staff, driver, vehicle, 30, route)
    return {"h": h, "staff": staff, "ctx": ctx, "run_id": str(run.id)}


def _add_intermediate(db: Session, route: RouteDefinition, at: tuple[float, float]) -> None:
    dest = next(s for s in route.stops if s.kind == "DESTINATION")
    dest.sequence = 3
    db.flush()
    db.add(
        RouteStop(
            route_id=route.id,
            sequence=2,
            kind="INTERMEDIATE",
            name="محطة الحي",
            latitude=at[0],
            longitude=at[1],
            radius_m=100,
        )
    )
    db.commit()
    db.refresh(route)


def _finish(client: TestClient, s: dict[str, Any], segments: list[Any]) -> dict[str, Any]:
    if segments:
        _upload(
            client,
            s["h"],
            s["ctx"]["shift"]["id"],
            _points(utcnow() - timedelta(minutes=28), segments),
        )
    client.post(
        f"/api/v1/operation-sessions/{s['ctx']['session']['id']}/end", headers=s["staff"], json={}
    )
    run: dict[str, Any] = client.get(
        f"/api/v1/school-runs/{s['run_id']}", headers=s["staff"]
    ).json()
    return run


# Covers the whole 30-minute session: 1 min at the station, 5 min driving, 20 min at school.
TRIP = [("dwell", STATION, 60), ("drive", STATION, SCHOOL, 300), ("dwell", SCHOOL, 1200)]


def test_on_time_run_with_every_stop_is_complete(client: TestClient, db: Session) -> None:
    run = _finish(client, _setup(client, db), TRIP)
    assert run["status"] == "COMPLETED"
    v = run["verification"]
    assert len(v["reached_stops"]) == len(v["required_stops"]) == 2
    assert v["missing_stops"] == []
    assert v["arrival_delay_minutes"] < 0  # arrived before the scheduled end
    assert v["gps_coverage_pct"] > 60 and v["max_deviation_m"] is not None


def test_arriving_after_the_scheduled_end_is_complete_but_late(
    client: TestClient, db: Session
) -> None:
    # Scheduled 60 to 40 minutes ago; the trip started 30 minutes ago.
    run = _finish(client, _setup(client, db, start_offset_min=-60, end_offset_min=-40), TRIP)
    assert run["status"] == "COMPLETED_LATE"
    assert run["verification"]["arrival_delay_minutes"] > 10
    assert run["verification"]["start_delay_minutes"] >= 29


def test_a_missed_stop_with_good_gps_is_incomplete(client: TestClient, db: Session) -> None:
    run = _finish(client, _setup(client, db, extra_stop=OFF_PATH), TRIP)
    assert run["status"] == "INCOMPLETE"
    assert run["verification"]["missing_stops"] == ["محطة الحي"]
    assert run["status_reason"] == "stops_not_reached"


def test_thin_gps_needs_review_not_a_verdict(client: TestClient, db: Session) -> None:
    run = _finish(client, _setup(client, db, extra_stop=OFF_PATH), [("dwell", STATION, 60)])
    assert run["status"] == "COMPLETED_UNVERIFIED"
    assert run["verification"]["gps_coverage_pct"] < 60


def test_a_staff_correction_is_audited_and_kept_when_more_gps_arrives(
    client: TestClient, db: Session
) -> None:
    s = _setup(client, db, extra_stop=OFF_PATH)
    run = _finish(client, s, TRIP)
    assert run["status"] == "INCOMPLETE"
    fixed = client.post(
        f"/api/v1/school-runs/{s['run_id']}/status",
        headers=s["staff"],
        json={"status": "COMPLETED", "reason": "الطالب غائب ولم يلزم المرور بالمحطة"},
    )
    assert fixed.status_code == 200, fixed.text
    # Late points re-run detection, but a staff decision is never overwritten.
    _upload(
        client,
        s["h"],
        s["ctx"]["shift"]["id"],
        _points(utcnow() - timedelta(minutes=29), [("dwell", STATION, 30)]),
    )
    run = client.get(f"/api/v1/school-runs/{s['run_id']}", headers=s["staff"]).json()
    assert run["status"] == "COMPLETED"
    assert run["status_reason"].startswith("manual:")
