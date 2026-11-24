"""Two-factor login for staff (U31)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import totp
from app.core.config import get_settings
from app.core.permissions import UserRole
from app.core.time import utcnow
from app.models.audit import AuditLog
from app.models.user import User
from tests.factories import DEFAULT_PASSWORD as PASSWORD
from tests.factories import auth, login_as, make_user

A = "/api/v1/auth"


def _code(secret: str, ahead: int = 0) -> str:
    return totp.code_for(secret, totp.step_at(utcnow()) + ahead)


def _enroll(client: TestClient, h: dict[str, str]) -> tuple[str, list[str]]:
    setup = client.post(f"{A}/2fa/setup", headers=h)
    assert setup.status_code == 200, setup.text
    secret: str = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    wrong = client.post(f"{A}/2fa/enable", headers=h, json={"code": "000000"})
    assert wrong.status_code == 422
    res = client.post(f"{A}/2fa/enable", headers=h, json={"code": _code(secret)})
    assert res.status_code == 200, res.text
    codes: list[str] = res.json()["recovery_codes"]
    assert len(codes) == 10
    return secret, codes


def _password_step(client: TestClient, phone: str) -> dict[str, Any]:
    res = client.post(f"{A}/login", json={"phone": phone, "password": PASSWORD})
    assert res.status_code == 200, res.text
    body: dict[str, Any] = res.json()
    return body


def test_login_needs_the_code_once_enabled(client: TestClient, db: Session) -> None:
    user, h = login_as(client, db, UserRole.ADMIN)
    secret, codes = _enroll(client, h)

    first = _password_step(client, user.phone)
    # No session and no user details before the second step.
    assert first["twofa_required"] is True and first["access_token"] is None
    assert first["user"] is None

    bad = client.post(f"{A}/login/2fa", json={"challenge": first["challenge"], "code": "123456"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_2fa_code"

    # The code used to enable cannot be replayed; the next one works.
    ok = client.post(
        f"{A}/login/2fa", json={"challenge": first["challenge"], "code": _code(secret, 1)}
    )
    assert ok.status_code == 200, ok.text
    token = ok.json()["access_token"]
    me = client.get(f"{A}/me", headers=auth(token)).json()
    assert me["twofa_enabled"] is True and me["twofa_required"] is True

    # A recovery code works once.
    second = _password_step(client, user.phone)
    rec = client.post(f"{A}/login/2fa", json={"challenge": second["challenge"], "code": codes[0]})
    assert rec.status_code == 200
    third = _password_step(client, user.phone)
    again = client.post(f"{A}/login/2fa", json={"challenge": third["challenge"], "code": codes[0]})
    assert again.status_code == 401
    assert client.get(f"{A}/2fa", headers=h).json()["recovery_codes_left"] == 9

    # A tampered challenge is refused.
    forged = client.post(f"{A}/login/2fa", json={"challenge": "x" * 40, "code": codes[1]})
    assert forged.status_code == 401


def test_secrets_are_encrypted_and_never_audited(client: TestClient, db: Session) -> None:
    user, h = login_as(client, db, UserRole.ADMIN)
    secret, codes = _enroll(client, h)
    stored = db.get(User, user.id)
    assert stored is not None and stored.totp_secret_enc and secret not in stored.totp_secret_enc
    for entry in db.scalars(select(AuditLog).where(AuditLog.entity_id == str(user.id))).all():
        text = f"{entry.changes} {entry.details} {entry.reason}"
        assert secret not in text and codes[0] not in text


def test_disable_needs_password_and_code(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    secret, _ = _enroll(client, h)
    no = client.post(
        f"{A}/2fa/disable", headers=h, json={"password": "wrong-pass", "code": _code(secret, 1)}
    )
    assert no.status_code == 422
    yes = client.post(
        f"{A}/2fa/disable", headers=h, json={"password": PASSWORD, "code": _code(secret, 1)}
    )
    assert yes.status_code == 200, yes.text
    assert client.get(f"{A}/2fa", headers=h).json()["enabled"] is False


def test_admin_reset_ends_sessions_and_is_audited(client: TestClient, db: Session) -> None:
    user, h = login_as(client, db, UserRole.OPERATIONS)
    _enroll(client, h)
    _, manager = login_as(client, db, UserRole.SUPER_ADMIN)
    res = client.post(
        f"/api/v1/users/{user.id}/2fa/reset", headers=manager, json={"reason": "فقد الهاتف"}
    )
    assert res.status_code == 200, res.text
    assert client.get(f"{A}/me", headers=h).status_code == 401
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "auth.2fa.reset"))
    assert entry is not None and entry.reason == "فقد الهاتف"
    # The next login goes straight in (the user sets it up again).
    assert _password_step(client, user.phone)["access_token"]


def test_enforcement_blocks_work_until_enabled(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "twofa_enforce", True)
    _, h = login_as(client, db, UserRole.ADMIN)
    blocked = client.get("/api/v1/vehicles", headers=h)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "twofa_setup_required"
    assert client.get(f"{A}/me", headers=h).json()["twofa_setup_required"] is True
    _enroll(client, h)
    assert client.get("/api/v1/vehicles", headers=h).status_code == 200
    # Operations is not a required role.
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    assert client.get("/api/v1/vehicles", headers=ops).status_code == 200
    # Drivers never use 2FA.
    driver = make_user(db, role=UserRole.DRIVER)
    assert driver.twofa_enabled is False
