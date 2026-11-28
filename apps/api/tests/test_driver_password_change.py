"""Security audit L10: opt-in forced password change for driver accounts.

With DRIVER_FORCE_PASSWORD_CHANGE on, a password set by staff (account
creation or reset) must be changed by the driver before any driver-app
write; reads stay open so the app can show the change screen.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import UserRole
from tests.factories import login_as, make_driver

STAFF_SET = "Staff-set-pass-77"
OWN = "Drivers-own-pass-88"


def _driver_login(client: TestClient, phone: str, password: str) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login", json={"phone": phone, "password": password, "client": "mobile"}
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_staff_set_password_must_be_changed_when_enabled(
    client: TestClient, db: Session, monkeypatch: Any
) -> None:
    monkeypatch.setattr(get_settings(), "driver_force_password_change", True)
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    driver = make_driver(db)
    created = client.post(
        f"/api/v1/drivers/{driver.id}/account", headers=ops, json={"password": STAFF_SET}
    )
    assert created.status_code in (200, 201), created.text
    h = _driver_login(client, driver.phone, STAFF_SET)

    me = client.get("/api/v1/driver/me", headers=h)
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    blocked = client.post("/api/v1/driver/day-off", headers=h, json={})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "password_change_required"

    changed = client.post(
        "/api/v1/auth/change-password",
        headers=h,
        json={"current_password": STAFF_SET, "new_password": OWN},
    )
    assert changed.status_code == 200, changed.text
    assert client.get("/api/v1/driver/me", headers=h).json()["must_change_password"] is False
    assert client.post("/api/v1/driver/day-off", headers=h, json={}).status_code == 201

    reset = client.post(
        f"/api/v1/drivers/{driver.id}/account/reset-password",
        headers=ops,
        json={"new_password": STAFF_SET},
    )
    assert reset.status_code == 200, reset.text
    again = _driver_login(client, driver.phone, STAFF_SET)
    assert client.get("/api/v1/driver/me", headers=again).json()["must_change_password"] is True


def test_off_by_default(client: TestClient, db: Session) -> None:
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    driver = make_driver(db)
    client.post(f"/api/v1/drivers/{driver.id}/account", headers=ops, json={"password": STAFF_SET})
    h = _driver_login(client, driver.phone, STAFF_SET)
    assert client.get("/api/v1/driver/me", headers=h).json()["must_change_password"] is False
    assert client.post("/api/v1/driver/day-off", headers=h, json={}).status_code == 201
