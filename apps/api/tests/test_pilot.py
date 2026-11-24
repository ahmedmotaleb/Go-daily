"""Pilot command center and daily close (U50/U51)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from tests.factories import login_as, make_driver_account
from tests.test_driver_cash import _close, _start

URL = "/api/v1/pilot"


def _card(client: TestClient, h: dict[str, str], vehicle_id: object) -> dict[str, Any]:
    res = client.get(URL, headers=h)
    assert res.status_code == 200, res.text
    card: dict[str, Any] = next(c for c in res.json() if c["vehicle_id"] == str(vehicle_id))
    return card


def _check(card: dict[str, Any], code: str) -> dict[str, Any]:
    found: dict[str, Any] = next(c for c in card["checks"] if c["code"] == code)
    return found


def test_only_pilot_vehicles_and_the_flag_is_audited(client: TestClient, db: Session) -> None:
    _, _, _, vehicle = make_driver_account(client, db)
    _, admin = login_as(client, db, UserRole.ADMIN)
    ids = [c["vehicle_id"] for c in client.get(URL, headers=admin).json()]
    assert str(vehicle.id) not in ids
    res = client.patch(f"/api/v1/vehicles/{vehicle.id}", headers=admin, json={"pilot": True})
    assert res.status_code == 200 and res.json()["pilot"] is True
    card = _card(client, admin, vehicle.id)
    # No shift and no day-off yet: the day is not complete.
    assert card["verdict"] == "INCOMPLETE" and card["verdict_ar"] == "بيانات ناقصة"
    assert _check(card, "SHIFT")["state"] == "MISSING"
    audit = client.get(
        "/api/v1/audit-logs",
        headers=admin,
        params={"entity_type": "vehicle", "entity_id": str(vehicle.id)},
    )
    assert audit.status_code == 200, audit.text
    rows = audit.json()["items"]
    assert any("pilot" in (e.get("changes") or {}) for e in rows)


def test_daily_close_follows_the_day(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    _, admin = login_as(client, db, UserRole.ADMIN)
    client.patch(f"/api/v1/vehicles/{vehicle.id}", headers=admin, json={"pilot": True})
    shift = _start(client, h, vehicle)

    running = _card(client, admin, vehicle.id)
    assert _check(running, "SHIFT")["detail"] == "الوردية لم تنتهِ بعد"
    assert running["verdict"] == "INCOMPLETE"

    _close(client, h, shift["id"])
    closed = _card(client, admin, vehicle.id)
    assert _check(closed, "SHIFT")["state"] == "OK"
    # Close-out lines wait for office approval, and the cash is not handed over.
    assert _check(closed, "FUEL")["state"] == "REVIEW"
    cash = _check(closed, "CASH")
    assert cash["state"] == "MISSING" and closed["remaining"] == "1980.00"
    # No GPS was sent in the test: shown as missing, never estimated.
    assert _check(closed, "GPS")["state"] == "MISSING"
    assert closed["verdict"] == "INCOMPLETE"
    assert closed["shifts"][0]["gps_km"] == 0
    # A past day shows no live tracking state.
    past = client.get(URL, headers=admin, params={"day": "2026-01-01"}).json()
    assert next(c for c in past if c["vehicle_id"] == str(vehicle.id))["tracking_state"] is None

    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    r = client.post(
        "/api/v1/cash/collections",
        headers=acc,
        json={"driver_id": str(driver.id), "amount": "1980"},
    )
    assert r.status_code == 201, r.text
    assert _check(_card(client, admin, vehicle.id), "CASH")["state"] == "OK"


def test_pilot_view_needs_tracking_money_and_cash(client: TestClient, db: Session) -> None:
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    assert client.get(URL, headers=ops).status_code == 403
    assert client.get(URL, headers=acc).status_code == 403
