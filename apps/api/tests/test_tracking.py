from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import utcnow
from app.models.tracking import GpsPoint
from app.services.track_analysis import TrackPoint, find_gaps, find_stops, recorded_distance_m
from tests.factories import login_as, make_driver_account

DA = "/api/v1/driver"
BASE = (31.0409, 31.3785)


def _start(client: TestClient, h: dict[str, str], vehicle_id: object) -> dict[str, Any]:
    res = client.post(
        f"{DA}/shifts/start",
        headers=h,
        json={"vehicle_id": str(vehicle_id), "start_odometer_km": 50_000},
    )
    assert res.status_code == 201, res.text
    body: dict[str, Any] = res.json()
    return body


def _point(t: datetime, lat: float, lng: float, **kw: object) -> dict[str, object]:
    return {
        "client_point_id": str(uuid.uuid4()),
        "recorded_at": t.isoformat(),
        "latitude": lat,
        "longitude": lng,
        "accuracy_m": 8,
        "speed_mps": 10,
        "source": "GPS",
        **kw,
    }


def _upload(client, h, shift_id, points, batch_id=None):
    return client.post(
        f"{DA}/tracking/points",
        headers=h,
        json={"batch_id": batch_id or str(uuid.uuid4()), "shift_id": shift_id, "points": points},
    )


def test_ingestion_is_idempotent_and_flags_quality(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle.id)
    t0 = utcnow()
    points = [
        _point(t0 + timedelta(seconds=1), BASE[0], BASE[1]),
        _point(t0 + timedelta(seconds=11), BASE[0] + 0.0009, BASE[1]),  # ~100 m in 10 s
        _point(t0 + timedelta(seconds=21), BASE[0] + 0.0018, BASE[1], accuracy_m=350),
        _point(t0 + timedelta(seconds=31), BASE[0] + 0.2, BASE[1]),  # ~22 km in 10 s
        _point(t0 + timedelta(seconds=41), BASE[0] + 0.0027, BASE[1], is_mock=True),
    ]
    batch_id = str(uuid.uuid4())
    res = _upload(client, h, shift["id"], points, batch_id)
    assert res.status_code == 200, res.text
    assert res.json()["accepted"] == 5 and res.json()["duplicates"] == 0

    replay = _upload(client, h, shift["id"], points, batch_id)
    assert replay.json()["replayed"] is True
    again_new_batch = _upload(client, h, shift["id"], points)
    assert again_new_batch.json()["accepted"] == 0 and again_new_batch.json()["duplicates"] == 5

    qualities = db.scalars(
        select(GpsPoint.quality)
        .where(GpsPoint.shift_id == shift["id"])
        .order_by(GpsPoint.recorded_at)
    ).all()
    assert [q.value for q in qualities] == [
        "VALID",
        "VALID",
        "LOW_ACCURACY",
        "IMPLAUSIBLE_SPEED",
        "MOCK",
    ]


def test_points_outside_the_shift_are_never_stored(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle.id)
    now = utcnow()
    res = _upload(
        client,
        h,
        shift["id"],
        [
            _point(now - timedelta(hours=3), *BASE),
            _point(now + timedelta(hours=1), *BASE),
            _point(now, *BASE),
        ],
    )
    body = res.json()
    assert body["accepted"] == 1
    assert sorted(r["reason"] for r in body["rejected"]) == ["future_timestamp", "outside_shift"]
    assert (
        db.scalar(
            select(func.count()).select_from(GpsPoint).where(GpsPoint.shift_id == shift["id"])
        )
        == 1
    )


def test_late_sync_after_shift_end_is_accepted(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle.id)
    recorded = utcnow()
    client.post(f"{DA}/shifts/{shift['id']}/end", headers=h, json={"end_odometer_km": 50_010})
    res = _upload(client, h, shift["id"], [_point(recorded, *BASE)])
    assert res.json()["accepted"] == 1


def test_driver_cannot_upload_to_another_drivers_shift(client: TestClient, db: Session) -> None:
    _, _, h1, v1 = make_driver_account(client, db)
    _, _, h2, _ = make_driver_account(client, db)
    shift = _start(client, h1, v1.id)
    res = _upload(client, h2, shift["id"], [_point(utcnow(), *BASE)])
    assert res.status_code == 404


def test_live_positions_and_tracking_state(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle.id)
    _, staff = login_as(client, db, UserRole.OPERATIONS)
    live = client.get("/api/v1/tracking/live", headers=staff).json()
    row = next(r for r in live if r["shift_id"] == shift["id"])
    assert row["state"] == "OFFLINE" and row["latitude"] is None

    _upload(client, h, shift["id"], [_point(utcnow(), *BASE, speed_mps=12.5)])
    row = next(
        r
        for r in client.get("/api/v1/tracking/live", headers=staff).json()
        if r["shift_id"] == shift["id"]
    )
    assert row["state"] == "ONLINE"
    assert row["latitude"] == BASE[0]
    assert row["speed_kmh"] == 45.0
    status = client.get(f"{DA}/tracking/status", headers=h).json()
    assert status["state"] == "ONLINE"


def test_tracking_events_are_idempotent(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle.id)
    event = {
        "client_event_id": str(uuid.uuid4()),
        "event_type": "LOCATION_DISABLED",
        "occurred_at": utcnow().isoformat(),
        "shift_id": shift["id"],
    }
    first = client.post(f"{DA}/tracking/events", headers=h, json={"events": [event]}).json()
    second = client.post(f"{DA}/tracking/events", headers=h, json={"events": [event]}).json()
    assert first == {"accepted": 1, "duplicates": 0}
    assert second == {"accepted": 0, "duplicates": 1}


def test_shift_track_distance_gaps_stops_and_timeline(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    _, staff = login_as(client, db, UserRole.OPERATIONS)
    t0 = utcnow() - timedelta(minutes=30)
    shift = client.post(
        "/api/v1/shifts",
        headers=staff,
        json={
            "driver_id": str(driver.id),
            "vehicle_id": str(vehicle.id),
            "start_now": True,
            "start_odometer_km": 50_000,
            "started_at": t0.isoformat(),
        },
    ).json()
    pts = [_point(t0 + timedelta(seconds=10 * i), BASE[0] + 0.001 * i, BASE[1]) for i in range(11)]
    stop_lat = BASE[0] + 0.0105
    pts += [
        _point(t0 + timedelta(seconds=100 + 30 * i), stop_lat, BASE[1], speed_mps=0)
        for i in range(1, 9)
    ]
    pts.append(
        _point(t0 + timedelta(seconds=940), stop_lat + 0.04, BASE[1])
    )  # after a 10-minute gap
    assert _upload(client, h, shift["id"], pts).json()["accepted"] == len(pts)
    client.post(
        f"/api/v1/shifts/{shift['id']}/end",
        headers=staff,
        json={"end_odometer_km": 50_006, "ended_at": (t0 + timedelta(seconds=1000)).isoformat()},
    )

    body = client.get(f"/api/v1/shifts/{shift['id']}/track", headers=staff).json()
    assert body["odometer_distance_km"] == 6
    # GPS distance counts only consecutive points; the jump across the gap is excluded.
    assert 1.1 < body["gps_distance_km"] < 1.25
    assert [g["seconds"] for g in body["gaps"]] == [600]
    assert body["gaps"][0]["displacement_m"] > 4000
    assert len(body["stops"]) == 1
    kinds = [t["kind"] for t in body["timeline"]]
    assert kinds[0] == "SHIFT_STARTED" and kinds[-1] == "SHIFT_ENDED"
    assert {"STOP", "GAP"} <= set(kinds)
    assert body["counts"]["VALID"] == len(pts)


def test_track_analysis_pure_functions() -> None:
    t0 = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
    moving = [TrackPoint(t0 + timedelta(seconds=10 * i), 31.0 + 0.001 * i, 31.0) for i in range(11)]
    parked = [TrackPoint(t0 + timedelta(seconds=100 + 30 * i), 31.0105, 31.0) for i in range(1, 9)]
    after_gap = [TrackPoint(t0 + timedelta(seconds=940), 31.05, 31.0)]
    track = moving + parked + after_gap

    distance = recorded_distance_m(track, max_gap_seconds=300)
    # ~1.11 km driving + ~56 m to the parking spot; the 4.4 km jump across the gap is NOT counted.
    assert 1100 < distance < 1250

    gaps = find_gaps(
        track, window_start=t0, window_end=t0 + timedelta(seconds=1000), max_gap_seconds=300
    )
    assert len(gaps) == 1 and gaps[0].seconds == 600
    assert gaps[0].displacement_m is not None and gaps[0].displacement_m > 4000

    stops = find_stops(track, radius_m=60, min_seconds=180)
    assert len(stops) == 1 and stops[0].seconds >= 180

    empty_gaps = find_gaps(
        [], window_start=t0, window_end=t0 + timedelta(minutes=20), max_gap_seconds=300
    )
    assert len(empty_gaps) == 1 and empty_gaps[0].displacement_m is None


def test_tracking_read_permission(client: TestClient, db: Session) -> None:
    _, drv = login_as(client, db, UserRole.DRIVER)
    assert client.get("/api/v1/tracking/live", headers=drv).status_code == 403
