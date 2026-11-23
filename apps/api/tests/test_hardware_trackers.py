"""Hardware GPS tracker ingestion (U05). No real provider: the generic format only."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import UserRole
from app.core.time import utcnow
from app.models.trackers import TrackerLocation, TrackerRawEvent
from tests.factories import login_as, make_vehicle

URL = "/api/v1/trackers"
SECRET = "test-tracker-secret"


@pytest.fixture()
def secret(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(get_settings(), "tracker_webhook_secret", SecretStr(SECRET))
    return SECRET


def _send(client: TestClient, events: list[dict[str, Any]], key: str = SECRET) -> Any:
    body = json.dumps({"events": events}).encode()
    sig = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        f"{URL}/generic/events",
        content=body,
        headers={"x-godaily-signature": f"sha256={sig}", "content-type": "application/json"},
    )


def _event(n: int, device: str = "TRK-1", minutes_ago: int = 5, **extra: Any) -> dict[str, Any]:
    return {
        "event_id": f"e-{device}-{n}",
        "device_id": device,
        "recorded_at": (utcnow() - timedelta(minutes=minutes_ago)).isoformat(),
        "lat": 30.05,
        "lon": 31.24,
        "speed_kmh": 36,
        "ignition": True,
        **extra,
    }


def test_webhook_is_off_without_a_secret_and_needs_a_signature(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert get_settings().tracker_webhook_secret is None
    off = client.post(f"{URL}/generic/events", json={"events": []})
    assert off.status_code == 503
    assert off.json()["error"]["code"] == "tracker_ingestion_disabled"
    monkeypatch.setattr(get_settings(), "tracker_webhook_secret", SecretStr(SECRET))
    assert _send(client, [], key="wrong").status_code == 401
    unknown = client.post(
        f"{URL}/acme/events",
        content=b'{"events": []}',
        headers={
            "x-godaily-signature": "sha256="
            + hmac.new(SECRET.encode(), b'{"events": []}', hashlib.sha256).hexdigest()
        },
    )
    assert unknown.status_code == 404  # no adapter is faked for a vendor


def test_events_are_accepted_quarantined_and_reprocessed(
    client: TestClient, db: Session, secret: str
) -> None:
    _, admin = login_as(client, db, UserRole.ADMIN)
    vehicle = make_vehicle(db)

    # Unknown device: kept, quarantined, not dropped.
    res = _send(client, [_event(1, "TRK-9")])
    assert res.status_code == 200, res.text
    assert res.json()["quarantined"] == {"UNKNOWN_DEVICE": 1}

    device = client.post(
        f"{URL}/devices", headers=admin, json={"provider": "generic", "external_id": "TRK-9"}
    ).json()
    # Registered but not fitted to a vehicle.
    assert _send(client, [_event(2, "TRK-9")]).json()["quarantined"] == {"NO_VEHICLE_BINDING": 1}
    bound = client.post(
        f"{URL}/devices/{device['id']}/bind",
        headers=admin,
        json={
            "vehicle_id": str(vehicle.id),
            "starts_at": (utcnow() - timedelta(hours=1)).isoformat(),
        },
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["vehicle"]["name"] == vehicle.internal_code

    batch = [
        _event(3, "TRK-9"),
        _event(3, "TRK-9"),  # the same event twice in one body
        _event(4, "TRK-9", lat=0, lon=0),
        _event(5, "TRK-9", minutes_ago=-60),  # an hour in the future
        _event(6, "TRK-9", minutes_ago=60 * 24 * 40),  # older than 30 days
        {"event_id": "bad-1", "device_id": "TRK-9", "recorded_at": "yesterday"},
    ]
    res = _send(client, batch).json()
    assert res["accepted"] == 1 and res["duplicates"] == 1
    assert res["quarantined"] == {
        "INVALID_COORDINATES": 1,
        "FUTURE_TIME": 1,
        "TOO_OLD": 1,
        "INVALID_EVENT": 1,
    }
    # Resending the whole body changes nothing (idempotent).
    again = _send(client, batch).json()
    assert again["accepted"] == 0 and again["duplicates"] == len(batch)

    # Events quarantined for a device reason are accepted once it is fitted.
    out = client.post(f"{URL}/events/reprocess", headers=admin)
    assert out.status_code == 200, out.text
    assert out.json() == {"accepted": 2, "still_quarantined": 0}
    locations = db.scalars(
        select(TrackerLocation).where(TrackerLocation.vehicle_id == vehicle.id)
    ).all()
    assert len(locations) == 3
    assert all(abs((loc.speed_mps or 0) - 10) < 1e-9 for loc in locations)  # 36 km/h

    listed = client.get(f"{URL}/events", headers=admin, params={"status": "QUARANTINED"}).json()
    assert {e["reason"] for e in listed} >= {"INVALID_COORDINATES", "TOO_OLD"}
    assert all(e["reason_ar"] for e in listed)
    # 2 earlier events + 5 distinct ones in the batch: every event kept once.
    assert db.scalar(select(func.count()).select_from(TrackerRawEvent)) == 7


def test_binding_history_attributes_events_to_the_vehicle_of_that_time(
    client: TestClient, db: Session, secret: str
) -> None:
    _, admin = login_as(client, db, UserRole.ADMIN)
    first, second = make_vehicle(db), make_vehicle(db)
    device = client.post(
        f"{URL}/devices", headers=admin, json={"provider": "generic", "external_id": "TRK-2"}
    ).json()
    now = utcnow()
    for vehicle, hours in ((first, 3), (second, 1)):
        res = client.post(
            f"{URL}/devices/{device['id']}/bind",
            headers=admin,
            json={
                "vehicle_id": str(vehicle.id),
                "starts_at": (now - timedelta(hours=hours)).isoformat(),
            },
        )
        assert res.status_code == 200, res.text
    _send(client, [_event(1, "TRK-2", minutes_ago=120), _event(2, "TRK-2", minutes_ago=10)])
    by_vehicle = dict(
        db.execute(
            select(TrackerLocation.vehicle_id, func.count()).group_by(TrackerLocation.vehicle_id)
        ).all()
    )
    assert by_vehicle == {first.id: 1, second.id: 1}
    # A binding cannot start before the one already in place.
    late = client.post(
        f"{URL}/devices/{device['id']}/bind",
        headers=admin,
        json={"vehicle_id": str(first.id), "starts_at": (now - timedelta(hours=2)).isoformat()},
    )
    assert late.status_code == 409
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    assert (
        client.post(
            f"{URL}/devices", headers=ops, json={"provider": "generic", "external_id": "X"}
        ).status_code
        == 403
    )


def test_tracker_data_follows_gps_retention(client: TestClient, db: Session, secret: str) -> None:
    from app.services.trackers import ingest

    _send(client, [_event(1, "TRK-OLD")])  # quarantined: unknown device
    assert db.scalar(select(func.count()).select_from(TrackerRawEvent)) == 1
    assert ingest.prune(db, older_than_days=1) == 0  # still within retention
    assert ingest.prune(db, older_than_days=0) == 1
    assert db.scalar(select(func.count()).select_from(TrackerRawEvent)) == 0
