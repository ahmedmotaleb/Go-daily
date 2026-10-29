from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import ROLE_PERMISSIONS, Permission, UserRole
from app.models.audit import AuditLog
from tests.factories import DEFAULT_PASSWORD, auth, login, login_as, make_user

USERS = "/api/v1/users"


def _new_user_body(role: str = "OPERATIONS", phone: str = "01155550001") -> dict[str, object]:
    return {
        "full_name": "موظف تشغيل",
        "phone": phone,
        "role": role,
        "password": "Op3rations-pass",
    }


@pytest.mark.parametrize("role", [UserRole.OPERATIONS, UserRole.ACCOUNTANT])
def test_non_admin_staff_cannot_manage_users(
    client: TestClient, db: Session, role: UserRole
) -> None:
    _, headers = login_as(client, db, role)
    assert client.get(USERS, headers=headers).status_code == 403
    res = client.post(USERS, headers=headers, json=_new_user_body())
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "forbidden"


def test_driver_cannot_reach_staff_endpoints(client: TestClient, db: Session) -> None:
    _, headers = login_as(client, db, UserRole.DRIVER)
    assert client.get(USERS, headers=headers).status_code == 403
    assert client.get("/api/v1/audit-logs", headers=headers).status_code == 403


def test_admin_creates_and_lists_users(client: TestClient, db: Session) -> None:
    _, headers = login_as(client, db, UserRole.ADMIN)
    res = client.post(USERS, headers=headers, json=_new_user_body(phone="+201155550002"))
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["phone"] == "01155550002"
    assert "password" not in created and "password_hash" not in created

    listing = client.get(USERS, headers=headers, params={"q": "01155550002"})
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "user.created", AuditLog.entity_id == created["id"]
        )
    )
    assert audit is not None and "password_hash" not in (audit.changes or {})


def test_admin_cannot_create_or_promote_to_admin_roles(client: TestClient, db: Session) -> None:
    _, headers = login_as(client, db, UserRole.ADMIN)
    for role in ("ADMIN", "SUPER_ADMIN"):
        res = client.post(USERS, headers=headers, json=_new_user_body(role=role))
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "role_not_manageable"

    target = make_user(db, role=UserRole.OPERATIONS)
    res = client.patch(f"{USERS}/{target.id}", headers=headers, json={"role": "ADMIN"})
    assert res.status_code == 403


def test_admin_cannot_modify_super_admin(client: TestClient, db: Session) -> None:
    _, headers = login_as(client, db, UserRole.ADMIN)
    boss = make_user(db, role=UserRole.SUPER_ADMIN)
    res = client.patch(f"{USERS}/{boss.id}", headers=headers, json={"is_active": False})
    assert res.status_code == 403


def test_super_admin_can_create_admin(client: TestClient, db: Session) -> None:
    _, headers = login_as(client, db, UserRole.SUPER_ADMIN)
    res = client.post(USERS, headers=headers, json=_new_user_body(role="ADMIN"))
    assert res.status_code == 201


def test_duplicate_phone_and_email_conflict(client: TestClient, db: Session) -> None:
    _, headers = login_as(client, db, UserRole.ADMIN)
    existing = make_user(db)
    res = client.post(USERS, headers=headers, json=_new_user_body(phone=existing.phone))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "phone_taken"

    body = _new_user_body(phone="01155550003") | {"email": "Ops@Example.com"}
    assert client.post(USERS, headers=headers, json=body).status_code == 201
    body2 = _new_user_body(phone="01155550004") | {"email": "ops@example.com"}
    res = client.post(USERS, headers=headers, json=body2)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "email_taken"


def test_validation_errors(client: TestClient, db: Session) -> None:
    _, headers = login_as(client, db, UserRole.ADMIN)
    bad_phone = client.post(USERS, headers=headers, json=_new_user_body(phone="12345"))
    assert bad_phone.status_code == 422
    assert bad_phone.json()["error"]["code"] == "validation_error"

    weak = client.post(USERS, headers=headers, json=_new_user_body() | {"password": "123"})
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "weak_password"


def test_deactivation_revokes_sessions_and_is_audited(client: TestClient, db: Session) -> None:
    _, headers = login_as(client, db, UserRole.ADMIN)
    target = make_user(db, role=UserRole.ACCOUNTANT)
    target_token = login(client, target)

    res = client.patch(f"{USERS}/{target.id}", headers=headers, json={"is_active": False})
    assert res.status_code == 200
    assert res.json()["is_active"] is False
    assert client.get("/api/v1/auth/me", headers=auth(target_token)).status_code == 401

    entry = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "user.deactivated", AuditLog.entity_id == str(target.id)
        )
    )
    assert entry is not None
    assert entry.changes == {"is_active": {"old": True, "new": False}}


def test_cannot_deactivate_self_or_change_own_role(client: TestClient, db: Session) -> None:
    me, headers = login_as(client, db, UserRole.SUPER_ADMIN)
    make_user(db, role=UserRole.SUPER_ADMIN)  # not the last one
    res = client.patch(f"{USERS}/{me.id}", headers=headers, json={"is_active": False})
    assert res.json()["error"]["code"] == "cannot_deactivate_self"
    res = client.patch(f"{USERS}/{me.id}", headers=headers, json={"role": "ADMIN"})
    assert res.json()["error"]["code"] == "cannot_change_own_role"


def test_last_super_admin_is_protected(db: Session) -> None:
    from app.core.errors import ValidationFailed
    from app.schemas.user import UserUpdate
    from app.services.users import update_user

    only = make_user(db, role=UserRole.SUPER_ADMIN)
    other_actor = make_user(db, role=UserRole.SUPER_ADMIN, is_active=False)
    with pytest.raises(ValidationFailed) as exc:
        update_user(db, actor=other_actor, user_id=only.id, data=UserUpdate(is_active=False))
    assert exc.value.code == "last_super_admin"


def test_reset_password_revokes_target_sessions(client: TestClient, db: Session) -> None:
    _, headers = login_as(client, db, UserRole.ADMIN)
    target = make_user(db, role=UserRole.DRIVER)
    driver_token = login(client, target)
    res = client.post(
        f"{USERS}/{target.id}/reset-password",
        headers=headers,
        json={"new_password": "Driver-new-pass-1"},
    )
    assert res.status_code == 200
    assert client.get("/api/v1/auth/me", headers=auth(driver_token)).status_code == 401
    login(client, target, password="Driver-new-pass-1")
    res = client.post(
        "/api/v1/auth/login",
        json={"phone": target.phone, "password": DEFAULT_PASSWORD, "client": "mobile"},
    )
    assert res.status_code == 401


def test_audit_log_listing_requires_permission(client: TestClient, db: Session) -> None:
    _, admin = login_as(client, db, UserRole.ADMIN)
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    assert client.get("/api/v1/audit-logs", headers=ops).status_code == 403
    res = client.get("/api/v1/audit-logs", headers=admin, params={"action": "auth.login"})
    assert res.status_code == 200
    assert res.json()["total"] >= 2


def test_role_permission_matrix_least_privilege() -> None:
    ops = ROLE_PERMISSIONS[UserRole.OPERATIONS]
    acc = ROLE_PERMISSIONS[UserRole.ACCOUNTANT]
    assert Permission.USERS_MANAGE not in ops | acc
    assert Permission.AUDIT_READ not in ops | acc
    assert Permission.DRIVERS_READ_SENSITIVE not in ops | acc
    assert Permission.SETTLEMENTS_FINALIZE not in ops
    assert Permission.REVENUE_WRITE not in ops
    assert Permission.VEHICLES_WRITE not in acc
    assert ROLE_PERMISSIONS[UserRole.DRIVER] == frozenset()
