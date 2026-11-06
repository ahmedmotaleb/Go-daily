from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today
from app.models.audit import AuditLog
from app.models.driver import Driver
from app.models.user import User
from tests.factories import auth, login_as, make_driver, make_vehicle

D = "/api/v1/drivers"
NID = "29001011234567"


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "full_name": "محمود السائق",
        "phone": "01234567890",
        "national_id": NID,
        "license_number": "LIC-778899",
        "license_expiry": (local_today() + timedelta(days=400)).isoformat(),
        "hire_date": "2024-02-01",
    }
    body.update(overrides)
    return body


def test_create_driver_masks_and_encrypts_national_id(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    res = client.post(D, headers=h, json=_body())
    assert res.status_code == 201, res.text
    out = res.json()
    assert out["national_id_masked"] == "**********4567"
    assert "national_id" not in out
    assert out["employment_status"] == "ACTIVE"
    assert out["license_status"] == "OK"

    stored = db.scalar(select(Driver).where(Driver.id == out["id"]))
    assert stored is not None
    assert stored.national_id_encrypted and NID not in stored.national_id_encrypted
    assert stored.national_id_hash and NID not in stored.national_id_hash

    dump = " ".join(
        str(r) for r in db.execute(text("SELECT changes, details FROM audit_logs")).all()
    )
    assert NID not in dump


def test_sensitive_national_id_requires_permission_and_is_audited(
    client: TestClient, db: Session
) -> None:
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    _, admin = login_as(client, db, UserRole.ADMIN)
    driver_id = client.post(D, headers=ops, json=_body()).json()["id"]
    assert client.get(f"{D}/{driver_id}/sensitive", headers=ops).status_code == 403
    res = client.get(f"{D}/{driver_id}/sensitive", headers=admin)
    assert res.status_code == 200
    assert res.json() == {"national_id": NID}
    assert db.scalar(
        select(AuditLog).where(
            AuditLog.action == "driver.sensitive_viewed", AuditLog.entity_id == driver_id
        )
    )


def test_driver_uniqueness_and_validation(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    assert client.post(D, headers=h, json=_body()).status_code == 201
    dup_phone = client.post(D, headers=h, json=_body(national_id=None))
    assert dup_phone.json()["error"]["code"] == "driver_phone_taken"
    dup_nid = client.post(
        D, headers=h, json=_body(phone="01234567891", national_id="٢٩٠٠١٠١١٢٣٤٥٦٧")
    )
    assert dup_nid.status_code == 409
    assert dup_nid.json()["error"]["code"] == "driver_national_id_taken"
    bad_nid = client.post(D, headers=h, json=_body(phone="01234567892", national_id="123"))
    assert bad_nid.status_code == 422


def test_license_expiry_warning(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    make_driver(db, full_name="ر1", license_expiry=local_today() - timedelta(days=3))
    make_driver(db, full_name="ر2", license_expiry=local_today() + timedelta(days=5))
    res = client.get(D, headers=h, params={"license": "attention"})
    statuses = {d["full_name"]: d["license_status"] for d in res.json()["items"]}
    assert statuses == {"ر1": "EXPIRED", "ر2": "EXPIRING_SOON"}


def test_search_and_status_filters(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    make_driver(db, full_name="كريم عادل", license_number="AB-1")
    make_driver(db, full_name="كريم سعيد", employment_status="ON_LEAVE")
    assert client.get(D, headers=h, params={"q": "كريم"}).json()["total"] == 2
    assert (
        client.get(D, headers=h, params={"q": "كريم", "employment_status": "ON_LEAVE"}).json()[
            "total"
        ]
        == 1
    )
    assert client.get(D, headers=h, params={"q": "ab-1"}).json()["total"] == 1
    assert client.post(D, headers=h, json=_body()).status_code == 403


def test_app_account_lifecycle_and_termination(client: TestClient, db: Session) -> None:
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    driver_id = client.post(D, headers=ops, json=_body()).json()["id"]
    res = client.post(f"{D}/{driver_id}/account", headers=ops, json={"password": "Driver-pass-1"})
    assert res.status_code == 201, res.text
    assert res.json()["app_account_active"] is True
    user = db.scalar(select(User).where(User.phone == "01234567890"))
    assert user is not None and user.role is UserRole.DRIVER

    login = client.post(
        "/api/v1/auth/login",
        json={"phone": "01234567890", "password": "Driver-pass-1", "client": "mobile"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    again = client.post(f"{D}/{driver_id}/account", headers=ops, json={"password": "Driver-pass-1"})
    assert again.status_code == 409

    vehicle = make_vehicle(db)
    assert (
        client.post(
            "/api/v1/assignments",
            headers=ops,
            json={"driver_id": driver_id, "vehicle_id": str(vehicle.id)},
        ).status_code
        == 201
    )

    term = client.patch(f"{D}/{driver_id}", headers=ops, json={"employment_status": "TERMINATED"})
    assert term.status_code == 200
    body = term.json()
    assert body["employment_status"] == "TERMINATED"
    assert body["app_account_active"] is False
    assert body["current_assignments"] == []
    assert body["end_date"] == local_today().isoformat()
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 401
    history = client.get(f"{D}/{driver_id}/assignments", headers=ops).json()
    assert history["total"] == 1 and history["items"][0]["ends_at"] is not None


def test_profile_changes_sync_to_app_account(client: TestClient, db: Session) -> None:
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    driver_id = client.post(D, headers=ops, json=_body(national_id=None)).json()["id"]
    client.post(f"{D}/{driver_id}/account", headers=ops, json={"password": "Driver-pass-1"})
    client.patch(
        f"{D}/{driver_id}", headers=ops, json={"full_name": "محمود علي", "phone": "01234567899"}
    )
    user = db.scalar(select(User).where(User.phone == "01234567899"))
    assert user is not None and user.full_name == "محمود علي"


def test_compensation_plans_are_versioned(client: TestClient, db: Session) -> None:
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    driver = make_driver(db)
    url = f"{D}/{driver.id}/compensation-plans"

    assert client.get(url, headers=ops).status_code == 403
    assert (
        client.post(
            url,
            headers=ops,
            json={
                "method": "DAILY_WAGE",
                "daily_wage_amount": "300",
                "effective_from": "2026-01-01",
            },
        ).status_code
        == 403
    )

    first = client.post(
        url,
        headers=acc,
        json={
            "method": "DAILY_WAGE",
            "daily_wage_amount": "300.00",
            "effective_from": "2026-01-01",
        },
    )
    assert first.status_code == 201, first.text
    second = client.post(
        url,
        headers=acc,
        json={
            "method": "FIXED_PLUS_INCENTIVE",
            "fixed_monthly_amount": "6000",
            "incentive_percentage": "5",
            "effective_from": "2026-06-01",
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["incentive_threshold_amount"] == "0.00"

    plans = client.get(url, headers=acc).json()
    assert [p["method"] for p in plans] == ["FIXED_PLUS_INCENTIVE", "DAILY_WAGE"]
    assert plans[1]["effective_to"] == "2026-05-31"
    assert plans[1]["daily_wage_amount"] == "300.00"
    assert plans[0]["effective_to"] is None

    back_dated = client.post(
        url,
        headers=acc,
        json={"method": "DAILY_WAGE", "daily_wage_amount": "350", "effective_from": "2026-03-01"},
    )
    assert back_dated.status_code == 409


def test_compensation_validation_per_method(client: TestClient, db: Session) -> None:
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    url = f"{D}/{make_driver(db).id}/compensation-plans"
    cases = [
        {"method": "FIXED_MONTHLY", "effective_from": "2026-01-01"},
        {
            "method": "REVENUE_PERCENTAGE",
            "revenue_percentage": "120",
            "effective_from": "2026-01-01",
        },
        {
            "method": "DAILY_WAGE",
            "daily_wage_amount": "300",
            "revenue_percentage": "10",
            "effective_from": "2026-01-01",
        },
        {"method": "DAILY_WAGE", "daily_wage_amount": "0", "effective_from": "2026-01-01"},
    ]
    for body in cases:
        assert client.post(url, headers=acc, json=body).status_code == 422, body


def test_inactive_status_blocks_new_account(client: TestClient, db: Session) -> None:
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    driver = make_driver(db, employment_status="SUSPENDED")
    res = client.post(f"{D}/{driver.id}/account", headers=ops, json={"password": "Driver-pass-1"})
    assert res.status_code == 422
