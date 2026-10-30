from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from app.models.audit import AuditLog
from app.models.operations import RouteDefinition, RouteStop
from app.models.route_events import SchoolRun
from tests.factories import login_as, make_driver_account, operation_type_id

STATION = (31.0409, 31.3785)
UNIVERSITY = (31.0409, 31.3520)
SCHOOL = (31.0500, 31.3700)


def _route(
    db: Session, code: str, a: tuple[float, float], b: tuple[float, float], name: str
) -> RouteDefinition:
    route = RouteDefinition(
        name=name,
        operation_type_id=uuid.UUID(operation_type_id(db, code)),
        trip_pattern="ROUND_TRIP" if code == "FIXED_ROUTE" else "ONE_WAY",
    )
    db.add(route)
    db.flush()
    db.add_all(
        [
            RouteStop(
                route_id=route.id,
                sequence=1,
                kind="ORIGIN",
                name="A",
                latitude=a[0],
                longitude=a[1],
                radius_m=120,
            ),
            RouteStop(
                route_id=route.id,
                sequence=2,
                kind="DESTINATION",
                name="B",
                latitude=b[0],
                longitude=b[1],
                radius_m=150,
            ),
        ]
    )
    db.commit()
    return route


def _points(t0, segments) -> list[dict[str, Any]]:
    """segments: list of ("dwell", at, seconds) / ("drive", a, b, seconds); points every 15 s."""
    pts, t = [], t0
    for seg in segments:
        if seg[0] == "dwell":
            for _ in range(seg[2] // 15):
                pts.append((t, *seg[1]))
                t += timedelta(seconds=15)
        else:
            _, a, b, seconds = seg
            n = seconds // 15
            for i in range(1, n + 1):
                f = i / n
                pts.append((t, a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
                t += timedelta(seconds=15)
    return [
        {
            "client_point_id": str(uuid.uuid4()),
            "recorded_at": tt.isoformat(),
            "latitude": lat,
            "longitude": lng,
            "accuracy_m": 8,
            "source": "GPS",
        }
        for tt, lat, lng in pts
    ]


def _start_backdated(client, staff, driver, vehicle, minutes_ago: int, route) -> dict[str, Any]:
    res = client.post(
        "/api/v1/shifts",
        headers=staff,
        json={
            "driver_id": str(driver.id),
            "vehicle_id": str(vehicle.id),
            "start_now": True,
            "start_odometer_km": 50_000,
            "started_at": (utcnow() - timedelta(minutes=minutes_ago)).isoformat(),
        },
    )
    assert res.status_code == 201, res.text
    shift = res.json()
    session = client.post(
        f"/api/v1/shifts/{shift['id']}/sessions",
        headers=staff,
        json={
            "operation_type_id": str(route.operation_type_id),
            "route_id": str(route.id),
            "started_at": shift["started_at"],
        },
    )
    assert session.status_code == 201, session.text
    return {"shift": shift, "session": session.json()}


def _upload(client, h, shift_id, points) -> dict[str, Any]:
    res = client.post(
        "/api/v1/driver/tracking/points",
        headers=h,
        json={"batch_id": str(uuid.uuid4()), "shift_id": shift_id, "points": points},
    )
    assert res.status_code == 200, res.text
    body: dict[str, Any] = res.json()
    return body


def test_loops_are_counted_from_uploaded_gps(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    _, staff = login_as(client, db, UserRole.OPERATIONS)
    route = _route(db, "FIXED_ROUTE", STATION, UNIVERSITY, "موقف ⇄ جامعة")
    ctx = _start_backdated(client, staff, driver, vehicle, 60, route)
    t0 = utcnow() - timedelta(minutes=58)
    segments: list[Any] = [("dwell", STATION, 60)]
    for _ in range(2):
        segments += [("drive", STATION, UNIVERSITY, 300), ("dwell", UNIVERSITY, 60)]
        segments += [("drive", UNIVERSITY, STATION, 300), ("dwell", STATION, 60)]
    pts = _points(t0, segments)
    # Upload in two batches, as an offline queue would.
    half = len(pts) // 2
    _upload(client, h, ctx["shift"]["id"], pts[:half])
    _upload(client, h, ctx["shift"]["id"], pts[half:])

    detail = client.get(f"/api/v1/shifts/{ctx['shift']['id']}", headers=staff).json()
    session = next(s for s in detail["sessions"] if s["id"] == ctx["session"]["id"])
    assert session["loops"] == 2
    assert session["legs"] == 4

    events = client.get(
        f"/api/v1/operation-sessions/{ctx['session']['id']}/route-events", headers=staff
    ).json()
    loop_events = [e for e in events if e["event_type"] == "LOOP_COMPLETED"]
    assert [e["sequence_no"] for e in loop_events] == [1, 2]
    assert all(e["source"] == "AUTO" for e in loop_events)
    assert any(e["stop_name"] == "B" for e in events if e["event_type"] == "ENTERED")

    # Recompute is idempotent.
    again = client.post(
        f"/api/v1/operation-sessions/{ctx['session']['id']}/route-events/recompute", headers=staff
    )
    assert again.status_code == 200
    detail = client.get(f"/api/v1/shifts/{ctx['shift']['id']}", headers=staff).json()
    assert next(s for s in detail["sessions"] if s["id"] == ctx["session"]["id"])["loops"] == 2

    # Admin correction: void one loop, add a manual one; both audited and kept after recompute.
    voided = client.post(
        f"/api/v1/route-events/{loop_events[0]['id']}/void",
        headers=staff,
        json={"reason": "دورة مكررة بسبب توقف داخل الموقف"},
    )
    assert voided.json()["status"] == "VOIDED"
    manual = client.post(
        f"/api/v1/operation-sessions/{ctx['session']['id']}/route-events",
        headers=staff,
        json={
            "event_type": "LOOP_COMPLETED",
            "occurred_at": (utcnow() - timedelta(minutes=5)).isoformat(),
            "reason": "انقطاع GPS أثناء دورة مؤكدة من السائق",
        },
    )
    assert manual.status_code == 201
    client.post(
        f"/api/v1/operation-sessions/{ctx['session']['id']}/route-events/recompute", headers=staff
    )
    detail = client.get(f"/api/v1/shifts/{ctx['shift']['id']}", headers=staff).json()
    assert next(s for s in detail["sessions"] if s["id"] == ctx["session"]["id"])["loops"] == 2
    actions = set(db.scalars(select(AuditLog.action)).all())
    assert {"route_event.voided", "route_event.manual_added"} <= actions


def test_school_run_completed_with_gps_evidence(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    _, staff = login_as(client, db, UserRole.OPERATIONS)
    route = _route(db, "SCHOOL_ROUTE", STATION, SCHOOL, "مدرسة النور — صباحي")
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
            "label": "صباحي",
        },
    )
    assert gen.status_code == 201, gen.text
    assert gen.json()["created"] == 1

    ctx = _start_backdated(client, staff, driver, vehicle, 30, route)
    runs = client.get(
        "/api/v1/school-runs", headers=staff, params={"vehicle_id": str(vehicle.id)}
    ).json()
    assert runs["items"][0]["status"] == "IN_PROGRESS"
    assert runs["items"][0]["session_id"] == ctx["session"]["id"]

    pts = _points(
        utcnow() - timedelta(minutes=28),
        [("dwell", STATION, 60), ("drive", STATION, SCHOOL, 300), ("dwell", SCHOOL, 90)],
    )
    _upload(client, h, ctx["shift"]["id"], pts)
    client.post(f"/api/v1/operation-sessions/{ctx['session']['id']}/end", headers=staff, json={})

    run = client.get(f"/api/v1/school-runs/{runs['items'][0]['id']}", headers=staff).json()
    assert run["status"] == "COMPLETED"
    assert run["evidence"]["reached_destination"] is True
    assert run["shift_id"] == ctx["shift"]["id"]


def test_school_run_without_gps_needs_review_then_upgrades_on_late_sync(
    client: TestClient, db: Session
) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    _, staff = login_as(client, db, UserRole.OPERATIONS)
    route = _route(db, "SCHOOL_ROUTE", STATION, SCHOOL, "مدرسة — بعد الظهر")
    client.post(
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
    ctx = _start_backdated(client, staff, driver, vehicle, 30, route)
    client.post(f"/api/v1/operation-sessions/{ctx['session']['id']}/end", headers=staff, json={})
    run_id = client.get(
        "/api/v1/school-runs", headers=staff, params={"vehicle_id": str(vehicle.id)}
    ).json()["items"][0]["id"]
    run = client.get(f"/api/v1/school-runs/{run_id}", headers=staff).json()
    assert run["status"] == "COMPLETED_UNVERIFIED"
    assert run["status_reason"] == "no_gps_evidence"

    # The phone was offline; its queued points arrive later and prove the run.
    pts = _points(
        utcnow() - timedelta(minutes=28),
        [("dwell", STATION, 60), ("drive", STATION, SCHOOL, 300), ("dwell", SCHOOL, 90)],
    )
    _upload(client, h, ctx["shift"]["id"], pts)
    run = client.get(f"/api/v1/school-runs/{run_id}", headers=staff).json()
    assert run["status"] == "COMPLETED"

    corrected = client.post(
        f"/api/v1/school-runs/{run_id}/status",
        headers=staff,
        json={"status": "CANCELLED", "reason": "إجازة رسمية للمدرسة"},
    )
    assert corrected.json()["status"] == "CANCELLED"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "school_run.status_corrected"))


def test_school_run_missed_when_no_operation(client: TestClient, db: Session) -> None:
    _, staff = login_as(client, db, UserRole.OPERATIONS)
    _, _, _, vehicle = make_driver_account(client, db)
    route = _route(db, "SCHOOL_ROUTE", STATION, SCHOOL, "مدرسة — أمس")
    yesterday = local_today() - timedelta(days=1)
    client.post(
        "/api/v1/school-runs/generate",
        headers=staff,
        json={
            "route_id": str(route.id),
            "date_from": yesterday.isoformat(),
            "date_to": yesterday.isoformat(),
            "start_time": "06:30:00",
            "end_time": "08:00:00",
            "vehicle_id": str(vehicle.id),
        },
    )
    runs = client.get(
        "/api/v1/school-runs", headers=staff, params={"vehicle_id": str(vehicle.id)}
    ).json()
    assert runs["items"][0]["status"] == "MISSED"
    assert (
        db.scalar(select(SchoolRun.status_reason).where(SchoolRun.vehicle_id == vehicle.id))
        == "no_operation_recorded"
    )


def test_generate_rejects_non_school_route(client: TestClient, db: Session) -> None:
    _, staff = login_as(client, db, UserRole.OPERATIONS)
    _, _, _, vehicle = make_driver_account(client, db)
    route = _route(db, "FIXED_ROUTE", STATION, UNIVERSITY, "خط")
    res = client.post(
        "/api/v1/school-runs/generate",
        headers=staff,
        json={
            "route_id": str(route.id),
            "date_from": local_today().isoformat(),
            "date_to": local_today().isoformat(),
            "start_time": "06:30:00",
            "end_time": "08:00:00",
            "vehicle_id": str(vehicle.id),
        },
    )
    assert res.json()["error"]["code"] == "not_a_school_route"
