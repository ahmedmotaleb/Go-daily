"""Fuel/CNG/oil ledger, general expenses and driver reimbursements (Tasks 15-16)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from app.models.audit import AuditLog
from tests.factories import (
    expense_category_id,
    fuel_type_id,
    login_as,
    make_completed_shift,
    make_driver,
    make_driver_account,
    make_vehicle,
)


def _iso(days_ago: int = 0, hours: int = 1) -> str:
    return (utcnow() - timedelta(days=days_ago, hours=hours)).isoformat()


def _fuel(client: TestClient, headers: dict[str, str], **body: object) -> Any:
    res = client.post("/api/v1/fuel", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_cng_gasoline_and_oil_are_separate_and_oil_is_not_fuel(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    common = {"vehicle_id": str(vehicle.id), "occurred_at": _iso(), "approve_now": True}
    cng = _fuel(
        client,
        h,
        fuel_type_id=fuel_type_id(db, "CNG"),
        quantity="20.5",
        unit_price="7.000",
        **common,
    )
    assert cng["total_amount"] == "143.50"  # computed from quantity x unit price
    assert cng["unit"] == "CUBIC_METER"  # type default
    assert cng["status"] == "APPROVED"
    _fuel(
        client,
        h,
        fuel_type_id=fuel_type_id(db, "GASOLINE"),
        quantity="10",
        total_amount="155",
        **common,
    )
    _fuel(
        client,
        h,
        fuel_type_id=fuel_type_id(db, "ENGINE_OIL"),
        quantity="4",
        total_amount="600",
        **common,
    )

    summary = client.get(
        "/api/v1/fuel/summary", params={"vehicle_id": str(vehicle.id)}, headers=h
    ).json()
    by_code = {row["fuel_type"]["code"]: row for row in summary["by_type"]}
    assert set(by_code) == {"CNG", "GASOLINE", "ENGINE_OIL"}
    assert summary["fuel_amount"] == "298.50"
    assert summary["consumables_amount"] == "600.00"


def test_total_must_match_quantity_times_price(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    res = client.post(
        "/api/v1/fuel",
        json={
            "vehicle_id": str(vehicle.id),
            "fuel_type_id": fuel_type_id(db, "GASOLINE"),
            "quantity": "10",
            "unit_price": "15.50",
            "total_amount": "200",
            "occurred_at": _iso(),
        },
        headers=h,
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "total_mismatch"
    assert res.json()["error"]["details"]["fields"][0]["loc"] == ["total_amount"]


def test_future_dates_are_refused(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    res = client.post(
        "/api/v1/fuel",
        json={
            "vehicle_id": str(make_vehicle(db).id),
            "fuel_type_id": fuel_type_id(db, "CNG"),
            "quantity": "10",
            "total_amount": "70",
            "occurred_at": (utcnow() + timedelta(days=1)).isoformat(),
        },
        headers=h,
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "time_in_future"


def test_lifecycle_edit_reject_resubmit_approve_and_lock(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    tx = _fuel(
        client,
        h,
        vehicle_id=str(vehicle.id),
        fuel_type_id=fuel_type_id(db, "CNG"),
        quantity="10",
        total_amount="70",
        occurred_at=_iso(),
    )
    assert tx["status"] == "SUBMITTED"
    url = f"/api/v1/fuel/{tx['id']}"

    rejected = client.post(f"{url}/reject", json={"reason": "الإيصال غير واضح"}, headers=h)
    assert rejected.json()["status"] == "REJECTED"
    edited = client.patch(url, json={"total_amount": "72", "vendor": "محطة الطريق"}, headers=h)
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "SUBMITTED"  # resubmitted by the edit
    approved = client.post(f"{url}/approve", json={"note": "مطابق"}, headers=h).json()
    assert approved["status"] == "APPROVED"
    assert approved["reviewed_by"] is not None

    locked = client.patch(url, json={"total_amount": "80"}, headers=h)
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "record_locked"

    actions = set(db.scalars(select(AuditLog.action).where(AuditLog.entity_id == tx["id"])).all())
    assert {
        "fuel_transaction.created",
        "fuel_transaction.rejected",
        "fuel_transaction.updated",
        "fuel_transaction.approved",
    } <= actions


def test_correction_voids_original_and_links_replacement(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    original = _fuel(
        client,
        h,
        vehicle_id=str(vehicle.id),
        fuel_type_id=fuel_type_id(db, "GASOLINE"),
        quantity="10",
        total_amount="150",
        occurred_at=_iso(),
        approve_now=True,
    )
    res = client.post(
        f"/api/v1/fuel/{original['id']}/correct",
        json={
            "vehicle_id": str(vehicle.id),
            "fuel_type_id": fuel_type_id(db, "GASOLINE"),
            "quantity": "10",
            "total_amount": "155",
            "occurred_at": original["occurred_at"],
            "reason": "خطأ في إدخال المبلغ",
        },
        headers=h,
    )
    assert res.status_code == 201, res.text
    replacement = res.json()
    assert replacement["corrects_id"] == original["id"]
    assert replacement["status"] == "SUBMITTED"
    old = client.get(f"/api/v1/fuel/{original['id']}", headers=h).json()
    assert old["status"] == "VOIDED"
    assert old["corrected_by_id"] == replacement["id"]
    assert "خطأ في إدخال المبلغ" in old["void_reason"]


def test_driver_paid_fuel_becomes_reimbursement_and_void_reverses_it(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    driver = make_driver(db)
    base = {
        "vehicle_id": str(vehicle.id),
        "fuel_type_id": fuel_type_id(db, "CNG"),
        "quantity": "10",
        "total_amount": "70",
        "occurred_at": _iso(),
        "paid_by": "DRIVER",
    }
    missing_driver = client.post("/api/v1/fuel", json=base, headers=h)
    assert missing_driver.status_code == 422
    tx = _fuel(client, h, driver_id=str(driver.id), **base)
    statement_url = f"/api/v1/drivers/{driver.id}/statement"
    params = {"date_from": (local_today() - timedelta(days=5)).isoformat()}
    assert client.get(statement_url, params=params, headers=h).json()["reimbursements"] == "0.00"

    client.post(f"/api/v1/fuel/{tx['id']}/approve", json={}, headers=h)
    statement = client.get(statement_url, params=params, headers=h).json()
    assert Decimal(statement["reimbursements"]) == Decimal("70")
    assert Decimal(statement["closing_balance"]) == Decimal("70")

    client.post(f"/api/v1/fuel/{tx['id']}/void", json={"reason": "إيصال مكرر"}, headers=h)
    statement = client.get(statement_url, params=params, headers=h).json()
    assert Decimal(statement["closing_balance"]) == 0
    assert statement["entries"][0]["voided_at"] is not None


def test_operations_can_read_but_not_enter_fuel(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    assert client.get("/api/v1/fuel", headers=h).status_code == 200
    res = client.post(
        "/api/v1/fuel",
        json={
            "vehicle_id": str(make_vehicle(db).id),
            "fuel_type_id": fuel_type_id(db, "CNG"),
            "quantity": "1",
            "total_amount": "7",
            "occurred_at": _iso(),
        },
        headers=h,
    )
    assert res.status_code == 403


def test_driver_fuel_entry_needs_active_shift_and_is_idempotent(
    client: TestClient, db: Session
) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    catalog = client.get("/api/v1/driver/catalog", headers=h).json()
    assert {t["code"] for t in catalog["fuel_types"]} >= {"CNG", "GASOLINE", "ENGINE_OIL"}
    body = {
        "fuel_type_id": fuel_type_id(db, "CNG"),
        "quantity": "12",
        "total_amount": "84",
        "latitude": 31.04,
        "longitude": 31.37,
        "location_accuracy_m": 9,
    }
    no_shift = client.post("/api/v1/driver/fuel", json=body, headers=h)
    assert no_shift.status_code == 409
    assert no_shift.json()["error"]["code"] == "no_active_shift"

    started = client.post(
        "/api/v1/driver/shifts/start",
        json={"vehicle_id": str(vehicle.id), "start_odometer_km": 50_000},
        headers=h,
    )
    assert started.status_code == 201, started.text
    key = {**h, "Idempotency-Key": "fuel-1"}
    first = client.post("/api/v1/driver/fuel", json=body, headers=key)
    again = client.post("/api/v1/driver/fuel", json=body, headers=key)
    assert first.status_code == 201, first.text
    assert again.json()["id"] == first.json()["id"]
    assert first.json()["status"] == "SUBMITTED"
    assert first.json()["paid_by"] == "DRIVER"

    _, staff = login_as(client, db, UserRole.ACCOUNTANT)
    tx = client.get(f"/api/v1/fuel/{first.json()['id']}", headers=staff).json()
    assert tx["source"] == "DRIVER_APP"
    assert tx["driver"]["id"] == str(driver.id)
    assert tx["shift_id"] == started.json()["id"]
    assert tx["latitude"] == 31.04
    assert len(client.get("/api/v1/driver/fuel", headers=h).json()) == 1
    # Staff endpoints stay closed to drivers.
    assert client.get("/api/v1/fuel", headers=h).status_code == 403


def test_expenses_by_category_and_validation(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    for code, amount in (("TOLL", "15"), ("TOLL", "15"), ("REPAIR", "450")):
        res = client.post(
            "/api/v1/expenses",
            json={
                "vehicle_id": str(vehicle.id),
                "category_id": expense_category_id(db, code),
                "amount": amount,
                "occurred_at": _iso(),
                "approve_now": True,
            },
            headers=h,
        )
        assert res.status_code == 201, res.text
    summary = client.get(
        "/api/v1/expenses/summary", params={"vehicle_id": str(vehicle.id)}, headers=h
    ).json()
    assert summary["total_amount"] == "480.00"
    totals = {r["category"]["code"]: r["amount"] for r in summary["by_category"]}
    assert totals == {"TOLL": "30.00", "REPAIR": "450.00"}
    maintenance = client.get(
        "/api/v1/expenses",
        params={"vehicle_id": str(vehicle.id), "group": "MAINTENANCE"},
        headers=h,
    ).json()
    assert maintenance["total"] == 1

    other_vehicle = make_vehicle(db)
    driver = make_driver(db)
    shift = make_completed_shift(db, driver, other_vehicle, day=local_today() - timedelta(days=1))
    mismatch = client.post(
        "/api/v1/expenses",
        json={
            "vehicle_id": str(vehicle.id),
            "shift_id": str(shift.id),
            "category_id": expense_category_id(db, "PARKING"),
            "amount": "10",
            "occurred_at": _iso(),
        },
        headers=h,
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["details"]["fields"][0]["loc"] == ["shift_id"]


def test_new_expense_category_needs_settings_permission(client: TestClient, db: Session) -> None:
    _, accountant = login_as(client, db, UserRole.ACCOUNTANT)
    body = {"code": "INSURANCE_FEES", "name_ar": "رسوم تأمين", "pnl_group": "OTHER"}
    assert (
        client.post("/api/v1/expense-categories", json=body, headers=accountant).status_code == 403
    )
    _, admin = login_as(client, db, UserRole.ADMIN)
    res = client.post("/api/v1/expense-categories", json=body, headers=admin)
    assert res.status_code == 201
    dup = client.post("/api/v1/expense-categories", json=body, headers=admin)
    assert dup.status_code == 422
