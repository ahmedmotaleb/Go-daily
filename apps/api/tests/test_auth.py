from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import utcnow
from app.models.audit import AuditLog
from app.models.user import AuthSession, User
from tests.factories import DEFAULT_PASSWORD, auth, login, make_user

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def _audit_actions(db: Session) -> list[str]:
    return list(db.scalars(select(AuditLog.action).order_by(AuditLog.occurred_at)).all())


def test_successful_login_returns_token_and_user(client: TestClient, db: Session) -> None:
    user = make_user(db, role=UserRole.OPERATIONS)
    res = client.post(LOGIN, json={"phone": user.phone, "password": DEFAULT_PASSWORD})
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"].startswith("gd_")
    assert body["user"]["role"] == "OPERATIONS"
    assert "vehicles:read" in body["user"]["permissions"]
    assert "users:manage" not in body["user"]["permissions"]
    assert "password_hash" not in body["user"]

    me = client.get(ME, headers=auth(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["id"] == str(user.id)

    stored = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
    assert stored is not None
    assert stored.token_hash != body["access_token"]
    assert "auth.login.success" in _audit_actions(db)


def test_login_accepts_international_phone_format(client: TestClient, db: Session) -> None:
    user = make_user(db, phone="01098765432")
    res = client.post(LOGIN, json={"phone": "+20 109 876 5432", "password": DEFAULT_PASSWORD})
    assert res.status_code == 200
    assert res.json()["user"]["id"] == str(user.id)


def test_wrong_password_is_rejected(client: TestClient, db: Session) -> None:
    user = make_user(db)
    res = client.post(LOGIN, json={"phone": user.phone, "password": "wrong-password"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_credentials"
    db.refresh(user)
    assert user.failed_login_count == 1
    assert "auth.login.failed" in _audit_actions(db)


def test_unknown_phone_gets_same_error(client: TestClient) -> None:
    for phone in ("01199999999", "not-a-phone"):
        res = client.post(LOGIN, json={"phone": phone, "password": "whatever-123"})
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "invalid_credentials"


def test_inactive_user_cannot_login(client: TestClient, db: Session) -> None:
    user = make_user(db, is_active=False)
    res = client.post(LOGIN, json={"phone": user.phone, "password": DEFAULT_PASSWORD})
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "account_inactive"


def test_inactive_user_wrong_password_reveals_nothing(client: TestClient, db: Session) -> None:
    user = make_user(db, is_active=False)
    res = client.post(LOGIN, json={"phone": user.phone, "password": "bad-password"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_credentials"


def test_repeated_failures_lock_the_account(client: TestClient, db: Session) -> None:
    user = make_user(db)
    for _ in range(5):
        assert (
            client.post(LOGIN, json={"phone": user.phone, "password": "nope-nope"}).status_code
            == 401
        )
    res = client.post(LOGIN, json={"phone": user.phone, "password": DEFAULT_PASSWORD})
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "account_locked"
    assert res.json()["error"]["details"]["retry_after_seconds"] > 0

    # After the lockout window, the correct password works again.
    db.execute(
        text("UPDATE users SET locked_until = now() - interval '1 minute' WHERE id = :id"),
        {"id": user.id},
    )
    db.commit()
    assert (
        client.post(LOGIN, json={"phone": user.phone, "password": DEFAULT_PASSWORD}).status_code
        == 200
    )


def test_driver_accounts_cannot_use_admin_web(client: TestClient, db: Session) -> None:
    driver = make_user(db, role=UserRole.DRIVER)
    res = client.post(
        LOGIN, json={"phone": driver.phone, "password": DEFAULT_PASSWORD, "client": "web"}
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "client_not_allowed"
    ok = client.post(
        LOGIN, json={"phone": driver.phone, "password": DEFAULT_PASSWORD, "client": "mobile"}
    )
    assert ok.status_code == 200


def test_staff_cannot_use_driver_app(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    res = client.post(
        LOGIN, json={"phone": admin.phone, "password": DEFAULT_PASSWORD, "client": "mobile"}
    )
    assert res.status_code == 403


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer gd_invalid"}, {"Authorization": "Basic abc"}],
)
def test_unauthorized_requests_are_rejected(client: TestClient, headers: dict[str, str]) -> None:
    res = client.get(ME, headers=headers)
    assert res.status_code in (401, 403)
    assert res.json()["error"]["code"] in ("not_authenticated", "invalid_session")


def test_logout_revokes_session(client: TestClient, db: Session) -> None:
    user = make_user(db)
    token = login(client, user)
    assert client.post("/api/v1/auth/logout", headers=auth(token)).status_code == 200
    res = client.get(ME, headers=auth(token))
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_session"


def test_expired_session_is_rejected(client: TestClient, db: Session) -> None:
    user = make_user(db)
    token = login(client, user)
    session = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
    assert session is not None
    session.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    res = client.get(ME, headers=auth(token))
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "session_expired"


def test_idle_web_session_expires(client: TestClient, db: Session) -> None:
    user = make_user(db)
    token = login(client, user)
    session = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
    assert session is not None
    session.last_used_at = utcnow() - timedelta(hours=73)
    db.commit()
    assert client.get(ME, headers=auth(token)).status_code == 401
    db.refresh(session)
    assert session.revoke_reason == "idle_timeout"


def test_deactivated_user_existing_session_is_rejected(client: TestClient, db: Session) -> None:
    user = make_user(db)
    token = login(client, user)
    user.is_active = False
    db.commit()
    res = client.get(ME, headers=auth(token))
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "account_inactive"


def test_change_password_flow(client: TestClient, db: Session) -> None:
    user = make_user(db)
    token_a = login(client, user)
    token_b = login(client, user)

    bad = client.post(
        "/api/v1/auth/change-password",
        headers=auth(token_a),
        json={"current_password": "wrong", "new_password": "N3w-password-xyz"},
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "invalid_current_password"

    weak = client.post(
        "/api/v1/auth/change-password",
        headers=auth(token_a),
        json={"current_password": DEFAULT_PASSWORD, "new_password": "short"},
    )
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "weak_password"

    ok = client.post(
        "/api/v1/auth/change-password",
        headers=auth(token_a),
        json={"current_password": DEFAULT_PASSWORD, "new_password": "N3w-password-xyz"},
    )
    assert ok.status_code == 200
    assert client.get(ME, headers=auth(token_a)).status_code == 200
    assert client.get(ME, headers=auth(token_b)).status_code == 401
    login(client, user, password="N3w-password-xyz")


def test_credentials_never_reach_the_audit_log(client: TestClient, db: Session) -> None:
    user = make_user(db)
    token = login(client, user)
    client.post(LOGIN, json={"phone": user.phone, "password": "Secret-Wrong-999"})
    client.post(
        "/api/v1/auth/change-password",
        headers=auth(token),
        json={"current_password": DEFAULT_PASSWORD, "new_password": "Brand-New-Pass-77"},
    )
    dump = " ".join(
        str(row)
        for row in db.execute(text("SELECT changes, details, reason FROM audit_logs")).all()
    )
    for secret in (DEFAULT_PASSWORD, "Secret-Wrong-999", "Brand-New-Pass-77", token):
        assert secret not in dump


def test_audit_log_is_append_only(db: Session) -> None:
    user = make_user(db)
    db.add(AuditLog(action="test.event", actor_user_id=user.id))
    db.flush()
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(text("UPDATE audit_logs SET action = 'tampered'"))
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(text("DELETE FROM audit_logs"))
    assert (
        db.scalar(select(AuditLog.action).where(AuditLog.actor_user_id == user.id)) == "test.event"
    )


def test_user_password_hash_is_argon2(db: Session) -> None:
    user = make_user(db)
    stored = db.get(User, user.id)
    assert stored is not None and stored.password_hash.startswith("$argon2id$")
