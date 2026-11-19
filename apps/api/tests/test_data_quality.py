"""Data quality dashboard (U49): missing data, kept apart from review cases."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from app.models.shift import Shift
from tests.factories import fuel_type_id, login_as, make_driver_account
from tests.test_driver_cash import _start

URL = "/api/v1/data-quality"


def _check(body: dict[str, Any], code: str) -> dict[str, Any]:
    found: dict[str, Any] = next(c for c in body["missing"] if c["code"] == code)
    return found


def test_missing_closeout_gps_and_odometer_are_listed(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    started = _start(client, h, vehicle)
    client.post(
        "/api/v1/driver/fuel",
        headers=h,
        json={"fuel_type_id": fuel_type_id(db, "CNG"), "quantity": "20", "total_amount": "200"},
    )
    # End the shift a day ago without a close-out and without any GPS point.
    ended = client.post(
        f"/api/v1/driver/shifts/{started['id']}/end", headers=h, json={"end_odometer_km": 50_050}
    )
    assert ended.status_code == 200, ended.text
    shift = db.get(Shift, started["id"])
    assert shift is not None and shift.ended_at is not None
    shift.ended_at = utcnow() - timedelta(days=1)
    shift.started_at = shift.ended_at - timedelta(hours=8)
    db.commit()

    _, admin = login_as(client, db, UserRole.ADMIN)
    body = client.get(URL, headers=admin).json()
    closeout = _check(body, "CLOSEOUT_MISSING")
    assert any(e["link"] == f"/shifts/{started['id']}" for e in closeout["examples"])
    gps = _check(body, "GPS_UNSYNCED")
    assert any(e["link"] == f"/shifts/{started['id']}" for e in gps["examples"])
    assert _check(body, "FUEL_NO_ODOMETER")["count"] >= 1
    # Every missing-data check explains itself; review cases are a separate list.
    assert all(c["why"] for c in body["missing"])
    assert isinstance(body["review"], list)


def test_stale_assignment_for_expired_license(client: TestClient, db: Session) -> None:
    driver, _, _, vehicle = make_driver_account(client, db)
    driver.license_expiry = local_today() - timedelta(days=1)
    db.commit()
    _, admin = login_as(client, db, UserRole.ADMIN)
    stale = _check(client.get(URL, headers=admin).json(), "ASSIGNMENT_STALE")
    assert any(e["link"] == f"/vehicles/{vehicle.id}" for e in stale["examples"])


def test_needs_reports_permission(client: TestClient, db: Session) -> None:
    _, driver_h = login_as(client, db, UserRole.DRIVER)
    assert client.get(URL, headers=driver_h).status_code == 403
    assert client.get(URL).status_code == 401
