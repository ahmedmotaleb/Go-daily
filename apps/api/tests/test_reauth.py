"""Re-authentication for sensitive actions (U35)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import totp
from app.core.config import get_settings
from app.core.permissions import UserRole
from app.core.security import hash_token
from app.core.time import utcnow
from app.models.audit import AuditLog
from app.models.driver import CompensationMethod
from app.models.user import AuthSession
from tests.factories import (
    DEFAULT_PASSWORD,
    login_as,
    make_completed_shift,
    make_driver,
    make_plan,
    make_vehicle,
)
from tests.test_finance_settlements import _day, _settle

A = "/api/v1/auth"


def _age(db: Session, headers: dict[str, str], minutes: int = 60) -> None:
    """Make the session look like it was opened (and confirmed) a while ago."""
    token = headers["Authorization"].removeprefix("Bearer ")
    db.execute(
        update(AuthSession)
        .where(AuthSession.token_hash == hash_token(token))
        .values(created_at=utcnow() - timedelta(minutes=minutes), reauthenticated_at=None)
    )
    db.commit()


def _new_user(client: TestClient, h: dict[str, str], phone: str) -> int:
    res = client.post(
        "/api/v1/users",
        headers=h,
        json={
            "full_name": "موظف جديد",
            "phone": phone,
            "role": "OPERATIONS",
            "password": "Another-pass-2026",
        },
    )
    return res.status_code


def test_fresh_login_counts_and_old_sessions_must_confirm(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.SUPER_ADMIN)
    assert _new_user(client, h, "01055550001") == 201  # just logged in: recent

    _age(db, h)
    blocked = client.post(
        "/api/v1/users",
        headers=h,
        json={
            "full_name": "x",
            "phone": "01055550002",
            "role": "OPERATIONS",
            "password": "Another-pass-2026",
        },
    )
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "reauth_required"
    policy = client.post(
        "/api/v1/policies",
        headers=h,
        json={"changes": {"cash_handover_days": 3}, "reason": "x y z"},
    )
    assert policy.json()["error"]["code"] == "reauth_required"
    # Reading is never blocked.
    assert client.get("/api/v1/users", headers=h).status_code == 200

    wrong = client.post(f"{A}/reauth", headers=h, json={"password": "not-the-password"})
    assert wrong.status_code == 422
    ok = client.post(f"{A}/reauth", headers=h, json={"password": DEFAULT_PASSWORD})
    assert ok.status_code == 200
    assert _new_user(client, h, "01055550003") == 201
    assert db.scalar(select(AuditLog).where(AuditLog.action == "auth.reauth")) is not None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "auth.reauth.failed")) is not None


def test_reauth_needs_the_code_when_2fa_is_on(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ADMIN)
    secret = client.post(f"{A}/2fa/setup", headers=h).json()["secret"]
    step = totp.step_at(utcnow())
    client.post(f"{A}/2fa/enable", headers=h, json={"code": totp.code_for(secret, step)})
    _age(db, h)
    no_code = client.post(f"{A}/reauth", headers=h, json={"password": DEFAULT_PASSWORD})
    assert no_code.status_code == 422 and "code" in str(no_code.json())
    ok = client.post(
        f"{A}/reauth",
        headers=h,
        json={"password": DEFAULT_PASSWORD, "code": totp.code_for(secret, step + 1)},
    )
    assert ok.status_code == 200, ok.text


def test_only_large_settlements_need_confirmation(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver = make_vehicle(db), make_driver(db)
    make_plan(
        db,
        driver,
        CompensationMethod.DAILY_WAGE,
        effective_from=_day(60),
        daily_wage_amount=Decimal("250"),
    )
    for days_ago in (10, 9):
        make_completed_shift(db, driver, vehicle, day=_day(days_ago), minutes=240)
    draft = _settle(client, h, str(driver.id), _day(14), _day(1))  # 500 EGP
    _age(db, h)

    monkeypatch.setattr(get_settings(), "reauth_settlement_amount", Decimal("400"))
    blocked = client.post(f"/api/v1/settlements/{draft['id']}/finalize", headers=h)
    assert blocked.json()["error"]["code"] == "reauth_required"

    monkeypatch.setattr(get_settings(), "reauth_settlement_amount", Decimal("10000"))
    small = client.post(f"/api/v1/settlements/{draft['id']}/finalize", headers=h)
    assert small.status_code == 200, small.text
