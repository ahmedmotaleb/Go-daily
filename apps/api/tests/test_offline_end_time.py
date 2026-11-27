"""Security audit M4: a shift ended offline ends when the driver ended it, not at the sync.

The app sends the phone's end time; the server accepts it only when it is
plausible (after the start, the last GPS point received and the last
session start; not in the future; within the backfill window), else it
keeps its own clock.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.shift import Shift
from tests.factories import make_driver_account, start_photo

DA = "/api/v1/driver"


def _shift_started_hours_ago(client: TestClient, db: Session, hours: int) -> tuple[Any, str]:
    _, _, h, vehicle = make_driver_account(client, db)
    res = client.post(
        f"{DA}/shifts/start",
        headers=h,
        json={
            "vehicle_id": str(vehicle.id),
            "start_odometer_km": 50_000,
            "start_odometer_photo_id": start_photo(client, h),
        },
    )
    assert res.status_code == 201, res.text
    shift = db.get(Shift, uuid.UUID(res.json()["id"]))
    assert shift is not None
    shift.started_at = utcnow() - timedelta(hours=hours)
    for s in shift.sessions:
        s.started_at = shift.started_at
    db.commit()
    return h, res.json()["id"]


def _points(client: TestClient, h: dict[str, str], shift_id: str, at: datetime) -> None:
    res = client.post(
        f"{DA}/tracking/points",
        headers=h,
        json={
            "batch_id": str(uuid.uuid4()),
            "shift_id": shift_id,
            "points": [
                {
                    "client_point_id": str(uuid.uuid4()),
                    "recorded_at": at.isoformat(),
                    "latitude": 31.04,
                    "longitude": 31.37,
                    "accuracy_m": 8,
                    "source": "GPS",
                }
            ],
        },
    )
    assert res.status_code in (200, 201), res.text


def test_an_offline_end_keeps_the_phone_time(client: TestClient, db: Session) -> None:
    h, sid = _shift_started_hours_ago(client, db, 14)
    ended = utcnow() - timedelta(hours=6)  # the driver ended at 18:00, synced next morning
    _points(client, h, sid, ended - timedelta(minutes=5))
    res = client.post(
        f"{DA}/shifts/{sid}/end",
        headers=h,
        json={"end_odometer_km": 50_120, "ended_at": ended.isoformat()},
    )
    assert res.status_code == 200, res.text
    assert datetime.fromisoformat(res.json()["ended_at"]) == ended


def test_implausible_phone_times_fall_back_to_the_server_clock(
    client: TestClient, db: Session
) -> None:
    h, sid = _shift_started_hours_ago(client, db, 14)
    last_point = utcnow() - timedelta(hours=2)
    _points(client, h, sid, last_point)
    before_points = last_point - timedelta(hours=1)  # earlier than data already received
    res = client.post(
        f"{DA}/shifts/{sid}/end",
        headers=h,
        json={"end_odometer_km": 50_120, "ended_at": before_points.isoformat()},
    )
    assert res.status_code == 200, res.text
    assert datetime.fromisoformat(res.json()["ended_at"]) > utcnow() - timedelta(minutes=1)

    h2, sid2 = _shift_started_hours_ago(client, db, 3)
    future = utcnow() + timedelta(hours=1)
    res2 = client.post(
        f"{DA}/shifts/{sid2}/end",
        headers=h2,
        json={"end_odometer_km": 50_050, "ended_at": future.isoformat()},
    )
    assert datetime.fromisoformat(res2.json()["ended_at"]) < utcnow() + timedelta(seconds=5)


def test_an_offline_closeout_ends_the_shift_at_the_phone_time(
    client: TestClient, db: Session
) -> None:
    h, sid = _shift_started_hours_ago(client, db, 14)
    recorded = utcnow() - timedelta(hours=5)
    res = client.post(
        f"{DA}/shifts/{sid}/closeout",
        headers=h,
        json={
            "end_odometer_km": 50_120,
            "collection_amount": "900",
            "toll_amount": "0",
            "client_entry_id": str(uuid.uuid4()),
            "recorded_at": recorded.isoformat(),
        },
    )
    assert res.status_code == 201, res.text
    shift = db.get(Shift, uuid.UUID(sid))
    assert shift is not None
    db.refresh(shift)
    assert shift.ended_at == recorded
