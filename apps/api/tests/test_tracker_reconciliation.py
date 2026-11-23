"""Phone GPS vs vehicle tracker (U06), with synthetic tracker data (no hardware exists)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, to_local_date
from app.models.shift import Shift
from app.models.trackers import (
    RawEventStatus,
    TrackerBinding,
    TrackerDevice,
    TrackerLocation,
    TrackerRawEvent,
)
from tests.factories import login_as, make_completed_shift, make_driver, make_vehicle
from tests.test_exceptions import add_points, offset

URL = "/api/v1/trackers"


def _tracker(
    db: Session, shift: Shift, start: datetime, *, minutes: int, where: Any, every_s: int = 60
) -> None:
    device = TrackerDevice(provider="generic", external_id=f"T-{uuid.uuid4().hex[:8]}")
    db.add(device)
    db.flush()
    db.add(
        TrackerBinding(
            device_id=device.id, vehicle_id=shift.vehicle_id, starts_at=start - timedelta(days=1)
        )
    )
    for i in range(minutes * 60 // every_s + 1):
        raw = TrackerRawEvent(
            provider="generic",
            provider_event_id=f"{device.external_id}-{i}",
            device_external_id=device.external_id,
            payload={},
            status=RawEventStatus.ACCEPTED,
        )
        db.add(raw)
        db.flush()
        lat, lng = where(i)
        db.add(
            TrackerLocation(
                device_id=device.id,
                vehicle_id=shift.vehicle_id,
                raw_event_id=raw.id,
                recorded_at=start + timedelta(seconds=i * every_s),
                latitude=lat,
                longitude=lng,
            )
        )
    db.commit()


def _shift(db: Session) -> Shift:
    shift = make_completed_shift(
        db, make_driver(db), make_vehicle(db), day=local_today() - timedelta(days=1), minutes=60
    )
    assert shift.started_at is not None
    return shift


def test_no_tracker_data_is_said_plainly(client: TestClient, db: Session) -> None:
    shift = _shift(db)
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    res = client.get(f"{URL}/shifts/{shift.id}/comparison", headers=ops)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "NO_TRACKER_DATA" and res.json()["pairs"] == 0


def test_matching_paths_and_a_phone_left_behind(client: TestClient, db: Session) -> None:
    shift = _shift(db)
    assert shift.started_at is not None
    t0 = shift.started_at

    def driving(i: int) -> tuple[float, float]:
        return offset(east_m=i * 400)  # 400 m a minute

    # 0-30 min: both drive together; 30-60: the vehicle drives on, the phone stays put.
    add_points(db, shift, t0, minutes=30, where=driving)
    add_points(db, shift, t0 + timedelta(minutes=31), minutes=29, where=lambda i: driving(30))
    _tracker(db, shift, t0, minutes=60, where=driving)

    _, ops = login_as(client, db, UserRole.OPERATIONS)
    body = client.get(f"{URL}/shifts/{shift.id}/comparison", headers=ops).json()
    assert body["status"] == "COMPARED"
    assert body["pairs"] == body["phone_points"]
    assert body["median_distance_m"] is not None and body["discrepancies"] > 0
    assert body["tracker_distance_km"] > body["phone_distance_km"]
    windows = body["phone_still_vehicle_moving"]
    assert windows and all(w["vehicle_m"] >= 500 and w["phone_m"] < 50 for w in windows)
    assert "مراجعة مطلوبة" in body["message"]


def test_vehicle_movement_outside_shifts(client: TestClient, db: Session) -> None:
    shift = _shift(db)
    assert shift.started_at is not None and shift.ended_at is not None
    # The tracker shows driving for 20 minutes after the shift ended.
    _tracker(
        db,
        shift,
        shift.ended_at + timedelta(minutes=5),
        minutes=20,
        where=lambda i: offset(east_m=i * 300),
    )
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    day = to_local_date(shift.started_at).isoformat()
    body = client.get(
        f"{URL}/vehicles/{shift.vehicle_id}/outside-shifts", headers=ops, params={"day": day}
    ).json()
    assert body["status"] == "CHECKED"
    [moved] = body["outside_shift"]
    assert moved["distance_km"] >= 5 and moved["positions"] == 21
    # Positions inside the shift are not "outside" movement.
    other = _shift(db)
    assert other.started_at is not None
    _tracker(db, other, other.started_at, minutes=30, where=lambda i: offset(east_m=i * 300))
    inside = client.get(
        f"{URL}/vehicles/{other.vehicle_id}/outside-shifts",
        headers=ops,
        params={"day": to_local_date(other.started_at).isoformat()},
    ).json()
    assert inside["status"] == "CHECKED" and inside["outside_shift"] == []
