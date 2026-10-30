"""Revenue ledger, receipts/custody and ride-hailing statements (Tasks 14, 17)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from tests.factories import (
    login_as,
    make_completed_shift,
    make_driver,
    make_platform,
    make_vehicle,
)

D = Decimal


def _day(days_ago: int) -> date:
    return local_today() - timedelta(days=days_ago)


def _receipt(amount: str, received_by: str = "DRIVER", method: str = "CASH") -> Any:
    return {
        "amount": amount,
        "received_at": (utcnow() - timedelta(hours=1)).isoformat(),
        "method": method,
        "received_by": received_by,
    }


def _statement(client: TestClient, h: dict[str, str], driver_id: str) -> Any:
    return client.get(
        f"/api/v1/drivers/{driver_id}/statement",
        params={"date_from": _day(60).isoformat()},
        headers=h,
    ).json()


def test_cash_collected_by_driver_is_custody_until_handover(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver = make_vehicle(db), make_driver(db)
    res = client.post(
        "/api/v1/revenue",
        json={
            "kind": "FIXED_ROUTE_COLLECTION",
            "vehicle_id": str(vehicle.id),
            "driver_id": str(driver.id),
            "occurred_on": _day(1).isoformat(),
            "amount": "850",
            "loops_count": 6,
            "receipt": _receipt("850"),
            "approve_now": True,
        },
        headers=h,
    )
    assert res.status_code == 201, res.text
    entry = res.json()
    assert entry["outstanding_amount"] == "0.00"
    assert entry["received_cash"] == "850.00"
    statement = _statement(client, h, str(driver.id))
    assert D(statement["cash_collected"]) == D("-850")
    assert D(statement["closing_balance"]) == D("-850")  # the driver holds company money

    handover = client.post(
        f"/api/v1/drivers/{driver.id}/ledger",
        json={
            "entry_type": "CASH_HANDOVER",
            "amount": "850",
            "occurred_on": _day(0).isoformat(),
            "description": "تسليم إيراد الخط",
        },
        headers=h,
    )
    assert handover.status_code == 201, handover.text
    assert D(_statement(client, h, str(driver.id))["closing_balance"]) == 0


def test_private_trip_outstanding_and_partial_payments(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    entry = client.post(
        "/api/v1/revenue",
        json={
            "kind": "PRIVATE_TRIP",
            "vehicle_id": str(vehicle.id),
            "occurred_on": _day(2).isoformat(),
            "amount": "1500",
            "customer_name": "رحلة الإسكندرية",
            "receipt": _receipt("500", received_by="COMPANY", method="BANK_TRANSFER"),
        },
        headers=h,
    ).json()
    assert entry["outstanding_amount"] == "1000.00"
    assert entry["received_electronic"] == "500.00"

    over = client.post(
        f"/api/v1/revenue/{entry['id']}/receipts", json=_receipt("1200", "COMPANY"), headers=h
    )
    assert over.status_code == 422
    assert over.json()["error"]["code"] == "over_receipt"
    driver_without_entry_driver = client.post(
        f"/api/v1/revenue/{entry['id']}/receipts", json=_receipt("100"), headers=h
    )
    assert driver_without_entry_driver.status_code == 422

    outstanding = client.get(
        "/api/v1/revenue",
        params={"vehicle_id": str(vehicle.id), "outstanding_only": True},
        headers=h,
    ).json()
    assert outstanding["total"] == 1
    paid = client.post(
        f"/api/v1/revenue/{entry['id']}/receipts", json=_receipt("1000", "COMPANY"), headers=h
    ).json()
    assert paid["outstanding_amount"] == "0.00"
    outstanding = client.get(
        "/api/v1/revenue",
        params={"vehicle_id": str(vehicle.id), "outstanding_only": True},
        headers=h,
    ).json()
    assert outstanding["total"] == 0


def test_ride_hailing_revenue_only_from_statements(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    res = client.post(
        "/api/v1/revenue",
        json={
            "kind": "RIDE_HAILING",
            "vehicle_id": str(make_vehicle(db).id),
            "occurred_on": _day(1).isoformat(),
            "amount": "100",
        },
        headers=h,
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "use_statement"


def test_contract_revenue_needs_service_period(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    body = {
        "kind": "CONTRACT_SERVICE",
        "vehicle_id": str(make_vehicle(db).id),
        "occurred_on": _day(1).isoformat(),
        "amount": "9000",
        "customer_name": "مدرسة النور",
    }
    assert client.post("/api/v1/revenue", json=body, headers=h).status_code == 422
    body |= {"period_start": _day(30).isoformat(), "period_end": _day(1).isoformat()}
    assert client.post("/api/v1/revenue", json=body, headers=h).status_code == 201


def test_void_requires_receipts_voided_and_correction_moves_receipts(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver = make_vehicle(db), make_driver(db)
    entry = client.post(
        "/api/v1/revenue",
        json={
            "kind": "FIXED_ROUTE_COLLECTION",
            "vehicle_id": str(vehicle.id),
            "driver_id": str(driver.id),
            "occurred_on": _day(1).isoformat(),
            "amount": "700",
            "receipt": _receipt("700"),
            "approve_now": True,
        },
        headers=h,
    ).json()
    blocked = client.post(
        f"/api/v1/revenue/{entry['id']}/void", json={"reason": "سجل مكرر"}, headers=h
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "has_receipts"

    corrected = client.post(
        f"/api/v1/revenue/{entry['id']}/correct",
        json={
            "kind": "FIXED_ROUTE_COLLECTION",
            "vehicle_id": str(vehicle.id),
            "driver_id": str(driver.id),
            "occurred_on": _day(1).isoformat(),
            "amount": "750",
            "reason": "المبلغ الصحيح 750",
            "approve_now": True,
        },
        headers=h,
    )
    assert corrected.status_code == 201, corrected.text
    new = corrected.json()
    assert new["corrects_id"] == entry["id"]
    assert new["received_amount"] == "700.00"  # the receipt moved with the correction
    assert new["outstanding_amount"] == "50.00"
    old = client.get(f"/api/v1/revenue/{entry['id']}", headers=h).json()
    assert old["status"] == "VOIDED"
    assert old["receipts"] == []
    # Custody is unchanged by the correction (same cash, same driver).
    assert D(_statement(client, h, str(driver.id))["cash_collected"]) == D("-700")

    receipt_id = new["receipts"][0]["id"]
    voided = client.post(
        f"/api/v1/revenue/receipts/{receipt_id}/void", json={"reason": "لم يُستلم"}, headers=h
    ).json()
    assert voided["received_amount"] == "0.00"
    assert D(_statement(client, h, str(driver.id))["cash_collected"]) == 0
    ok = client.post(f"/api/v1/revenue/{new['id']}/void", json={"reason": "إلغاء"}, headers=h)
    assert ok.status_code == 200


def test_revenue_summary_splits_cash_and_electronic(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver = make_vehicle(db), make_driver(db)
    for amount, receipt in (
        ("400", _receipt("400")),
        ("600", _receipt("250", "COMPANY", "WALLET")),
    ):
        client.post(
            "/api/v1/revenue",
            json={
                "kind": "FIXED_ROUTE_COLLECTION",
                "vehicle_id": str(vehicle.id),
                "driver_id": str(driver.id),
                "occurred_on": _day(1).isoformat(),
                "amount": amount,
                "receipt": receipt,
                "approve_now": True,
            },
            headers=h,
        )
    client.post(  # pending: excluded from totals
        "/api/v1/revenue",
        json={
            "kind": "OTHER",
            "vehicle_id": str(vehicle.id),
            "occurred_on": _day(1).isoformat(),
            "amount": "999",
        },
        headers=h,
    )
    s = client.get(
        "/api/v1/revenue/summary", params={"vehicle_id": str(vehicle.id)}, headers=h
    ).json()
    assert s["gross_amount"] == "1000.00"
    assert s["received_cash"] == "400.00"
    assert s["received_electronic"] == "250.00"
    assert s["outstanding_amount"] == "350.00"
    assert s["pending_count"] == 1


# --- Ride-hailing ------------------------------------------------------------------


def _stmt_body(platform_id: str, driver_id: str, vehicle_id: str, **over: object) -> Any:
    body = {
        "platform_id": platform_id,
        "driver_id": driver_id,
        "vehicle_id": vehicle_id,
        "period_start": _day(7).isoformat(),
        "period_end": _day(1).isoformat(),
        "trips_count": 42,
        "gross_earnings": "3000",
        "platform_fees": "750",
        "tips": "50",
        "adjustments": "0",
        "cash_collected": "1200",
        "payout_recipient": "DRIVER",
        "statement_reference": "W-2026-41",
    }
    body.update(over)
    return body


def test_approved_statement_generates_revenue_and_driver_custody(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver, platform = make_vehicle(db), make_driver(db), make_platform(db)
    res = client.post(
        "/api/v1/ride-hailing/statements",
        json=_stmt_body(str(platform.id), str(driver.id), str(vehicle.id)),
        headers=h,
    )
    assert res.status_code == 201, res.text
    st = res.json()
    assert st["income"] == "3050.00"
    assert st["net_earnings"] == "2300.00"
    assert st["platform_payout"] == "1100.00"
    assert st["revenue_entry_id"] is None

    approved = client.post(
        f"/api/v1/ride-hailing/statements/{st['id']}/approve", json={}, headers=h
    ).json()
    entry = client.get(f"/api/v1/revenue/{approved['revenue_entry_id']}", headers=h).json()
    assert entry["kind"] == "RIDE_HAILING"
    assert entry["amount"] == "3050.00"
    assert entry["fees_withheld"] == "750.00"
    assert entry["received_cash"] == "1200.00"
    assert entry["received_electronic"] == "1100.00"
    assert entry["outstanding_amount"] == "0.00"
    assert entry["source"] == "SYSTEM"
    # Cash from riders and the payout to the driver's account are both company money.
    assert D(_statement(client, h, str(driver.id))["closing_balance"]) == D("-2300")
    # The generated entry is managed through its statement only.
    direct = client.post(
        f"/api/v1/revenue/{entry['id']}/void", json={"reason": "محاولة"}, headers=h
    )
    assert direct.json()["error"]["code"] == "statement_managed"

    voided = client.post(
        f"/api/v1/ride-hailing/statements/{st['id']}/void",
        json={"reason": "كشف خاطئ"},
        headers=h,
    )
    assert voided.status_code == 200
    entry = client.get(f"/api/v1/revenue/{entry['id']}", headers=h).json()
    assert entry["status"] == "VOIDED"
    assert all(r["voided_at"] for r in entry["receipts"])
    assert D(_statement(client, h, str(driver.id))["closing_balance"]) == 0


def test_overlapping_statements_for_same_driver_and_platform_are_refused(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver, platform = make_vehicle(db), make_driver(db), make_platform(db)
    body = _stmt_body(str(platform.id), str(driver.id), str(vehicle.id))
    assert client.post("/api/v1/ride-hailing/statements", json=body, headers=h).status_code == 201
    clash = client.post(
        "/api/v1/ride-hailing/statements",
        json=body | {"period_start": _day(3).isoformat(), "period_end": _day(0).isoformat()},
        headers=h,
    )
    assert clash.status_code == 422
    assert clash.json()["error"]["code"] == "overlapping_statement"
    other_platform = make_platform(db)
    ok = client.post(
        "/api/v1/ride-hailing/statements",
        json=body | {"platform_id": str(other_platform.id)},
        headers=h,
    )
    assert ok.status_code == 201


def test_statement_validation(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    body = _stmt_body(
        str(make_platform(db).id),
        str(make_driver(db).id),
        str(make_vehicle(db).id),
        platform_fees="5000",
    )
    assert client.post("/api/v1/ride-hailing/statements", json=body, headers=h).status_code == 422


def test_cash_above_net_is_capped_and_shown_as_owed_to_platform(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver, platform = make_vehicle(db), make_driver(db), make_platform(db)
    st = client.post(
        "/api/v1/ride-hailing/statements",
        json=_stmt_body(
            str(platform.id),
            str(driver.id),
            str(vehicle.id),
            tips="0",
            cash_collected="2600",
            approve_now=True,
        ),
        headers=h,
    ).json()
    assert st["platform_payout"] == "-350.00"
    entry = client.get(f"/api/v1/revenue/{st['revenue_entry_id']}", headers=h).json()
    assert entry["received_cash"] == "2250.00"  # capped at the net
    assert entry["received_electronic"] == "0.00"
    recon = client.get(
        "/api/v1/ride-hailing/reconciliation",
        params={
            "date_from": _day(10).isoformat(),
            "date_to": _day(0).isoformat(),
            "driver_id": str(driver.id),
        },
        headers=h,
    ).json()
    codes = {f["code"] for f in recon["rows"][0]["flags"]}
    assert {"OWED_TO_PLATFORM", "NO_SHIFTS"} <= codes


def test_reconciliation_compares_statements_with_recorded_work(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver, platform = make_vehicle(db), make_driver(db), make_platform(db)
    # Two ride-hailing shifts inside the statement period, one after it.
    make_completed_shift(
        db,
        driver,
        vehicle,
        day=_day(5),
        minutes=300,
        start_odometer_km=1000,
        end_odometer_km=1120,
        operation_code="RIDE_HAILING",
    )
    make_completed_shift(
        db,
        driver,
        vehicle,
        day=_day(3),
        minutes=300,
        start_odometer_km=1120,
        end_odometer_km=1200,
        operation_code="RIDE_HAILING",
    )
    make_completed_shift(
        db, driver, vehicle, day=_day(0), minutes=120, operation_code="RIDE_HAILING"
    )
    client.post(
        "/api/v1/ride-hailing/statements",
        json=_stmt_body(str(platform.id), str(driver.id), str(vehicle.id), approve_now=True),
        headers=h,
    )
    recon = client.get(
        "/api/v1/ride-hailing/reconciliation",
        params={"date_from": _day(10).isoformat(), "date_to": _day(0).isoformat()},
        headers=h,
    )
    assert recon.status_code == 200, recon.text
    data = recon.json()
    row = next(r for r in data["rows"] if r["driver"]["id"] == str(driver.id))
    assert row["shifts_count"] == 2
    assert row["ride_hailing_minutes"] == 600
    assert row["odometer_km"] == 200
    assert row["net_per_hour"] == "230.00"  # 2300 / 10 h
    assert row["net_per_km"] == "11.50"
    uncovered = [r for r in data["uncovered"] if r["driver"]["id"] == str(driver.id)]
    assert len(uncovered) == 1
    assert uncovered[0]["period_start"] == _day(0).isoformat()
    assert uncovered[0]["flags"][0]["code"] == "NO_STATEMENT"
    # Labels describe what to check; they never accuse.
    messages = " ".join(f["message"] for r in data["rows"] + data["uncovered"] for f in r["flags"])
    assert "سرقة" not in messages and "احتيال" not in messages


def test_operations_cannot_see_revenue(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    assert client.get("/api/v1/revenue", headers=h).status_code == 403
    assert client.get("/api/v1/ride-hailing/statements", headers=h).status_code == 403
