"""Security event dashboard (U36)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.services import security_events
from tests.factories import login_as, make_user

URL = "/api/v1/security/events"


def test_failures_lockouts_and_denials_are_summarised(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = make_user(db)
    for _ in range(5):  # locks the account on the fifth failure
        client.post("/api/v1/auth/login", json={"phone": target.phone, "password": "wrong-pass-1"})
    client.post("/api/v1/auth/login", json={"phone": "01099999998", "password": "wrong-pass-1"})
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    assert client.get("/api/v1/users", headers=ops).status_code == 403  # denied, audited

    _, admin = login_as(client, db, UserRole.SUPER_ADMIN)
    body = client.get(URL, headers=admin).json()
    assert body["counts"]["failed_logins"] >= 6
    assert body["counts"]["lockouts"] >= 1
    assert body["counts"]["permission_denied"] >= 1
    assert body["unknown_number_attempts"] >= 1
    assert body["top_accounts"][0]["label"] == target.full_name
    assert any(e["action"] == "auth.permission_denied" for e in body["recent"])
    assert sum(h["count"] for h in body["hourly_failures"]) >= 6
    assert body["spike"] is False
    # Never secrets: no passwords or the unknown number in clear.
    text = str(body)
    assert "wrong-pass-1" not in text and "01099999998" not in text
    # Configuration warnings are listed (development settings here).
    codes = {w["code"] for w in body["warnings"]}
    assert {"ENVIRONMENT", "TWOFA_NOT_ENFORCED"} <= codes

    monkeypatch.setattr(security_events, "SPIKE_PER_HOUR", 3)
    assert client.get(URL, headers=admin).json()["spike"] is True


def test_only_settings_managers(client: TestClient, db: Session) -> None:
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    assert client.get(URL, headers=acc).status_code == 403
