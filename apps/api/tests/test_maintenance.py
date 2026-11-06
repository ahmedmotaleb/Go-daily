"""Maintenance schedules, service records, due status and P&L (Task 21)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from app.models.maintenance import MaintenanceType
from tests.factories import fuel_type_id, login_as, make_vehicle


def _type_id(db: Session, code: str) -> str:
    return str(db.scalar(select(MaintenanceType.id).where(MaintenanceType.code == code)))


def _day(days_ago: int) -> date:
    return local_today() - timedelta(days=days_ago)


def _record(client: TestClient, h: dict[str, str], vehicle_id: str, **body: Any) -> Any:
    res = client.post(
        "/api/v1/maintenance/records",
        json={"vehicle_id": vehicle_id, **body},
        headers=h,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _due(client: TestClient, h: dict[str, str], vehicle_id: str) -> dict[str, Any]:
    rows = client.get(
        "/api/v1/maintenance/due", params={"vehicle_id": vehicle_id}, headers=h
    ).json()
    return {row["type"]["code"]: row for row in rows}


def test_schedule_due_soon_overdue_and_reset_by_service(client: TestClient, db: Session) -> None:
    _, admin = login_as(client, db, UserRole.ADMIN)
    vehicle = make_vehicle(db, current_odometer_km=104_700)
    v = str(vehicle.id)
    oil = _type_id(db, "ENGINE_OIL_CHANGE")  # 5000 km / 90 days by default
    res = client.put(
        f"/api/v1/maintenance/vehicles/{v}/schedules",
        json={"type_id": oil, "baseline_km": 100_000, "baseline_date": _day(30).isoformat()},
        headers=admin,
    )
    assert res.status_code == 200, res.text
    row = _due(client, admin, v)["ENGINE_OIL_CHANGE"]
    assert row["next_due_km"] == 105_000
    assert row["km_left"] == 300
    assert row["state"] == "DUE_SOON"

    # Days can make it overdue even when kilometres do not.
    client.put(
        f"/api/v1/maintenance/vehicles/{v}/schedules",
        json={
            "type_id": oil,
            "interval_km": 20_000,
            "baseline_km": 100_000,
            "baseline_date": _day(120).isoformat(),
        },
        headers=admin,
    )
    assert _due(client, admin, v)["ENGINE_OIL_CHANGE"]["state"] == "OVERDUE"

    # An approved service resets the schedule from its own date and odometer.
    _record(
        client,
        admin,
        v,
        type_id=oil,
        performed_on=_day(1).isoformat(),
        odometer_km=104_650,
        parts_cost="450",
        labor_cost="100",
        approve_now=True,
    )
    row = _due(client, admin, v)["ENGINE_OIL_CHANGE"]
    assert row["last_odometer_km"] == 104_650
    assert row["next_due_km"] == 124_650
    assert row["state"] == "OK"


def test_schedule_needs_some_interval(client: TestClient, db: Session) -> None:
    _, admin = login_as(client, db, UserRole.ADMIN)
    vehicle = make_vehicle(db)
    res = client.put(
        f"/api/v1/maintenance/vehicles/{vehicle.id}/schedules",
        json={"type_id": _type_id(db, "OTHER")},
        headers=admin,
    )
    assert res.status_code == 422


def test_service_record_lifecycle_and_costs(client: TestClient, db: Session) -> None:
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    _, accountant = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    record = _record(
        client,
        ops,
        str(vehicle.id),
        type_id=_type_id(db, "BRAKES"),
        performed_on=_day(2).isoformat(),
        parts_cost="800",
        labor_cost="250",
        other_cost="50",
        vendor="ورشة الأمانة",
        approve_now=True,
        downtime_start=(utcnow() - timedelta(days=2, hours=6)).isoformat(),
        downtime_end=(utcnow() - timedelta(days=2)).isoformat(),
    )
    assert record["status"] == "SUBMITTED"  # operations cannot approve costs
    assert record["total_cost"] == "1100.00"
    assert record["downtime_hours"] == 6.0
    url = f"/api/v1/maintenance/records/{record['id']}"
    assert client.post(f"{url}/approve", json={}, headers=ops).status_code == 403
    approved = client.post(f"{url}/approve", json={}, headers=accountant).json()
    assert approved["status"] == "APPROVED"
    locked = client.put(
        url,
        json={
            **{k: record[k] for k in ("performed_on",)},
            "vehicle_id": str(vehicle.id),
            "type_id": record["type"]["id"],
        },
        headers=ops,
    )
    assert locked.status_code == 409


def test_oil_change_links_only_to_an_oil_purchase(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ADMIN)
    vehicle = make_vehicle(db)
    v = str(vehicle.id)

    def purchase(code: str) -> str:
        res = client.post(
            "/api/v1/fuel",
            json={
                "vehicle_id": v,
                "fuel_type_id": fuel_type_id(db, code),
                "quantity": "4",
                "total_amount": "600",
                "occurred_at": (utcnow() - timedelta(days=1)).isoformat(),
            },
            headers=h,
        )
        return str(res.json()["id"])

    oil_purchase, cng_fill = purchase("ENGINE_OIL"), purchase("CNG")
    base = {
        "type_id": _type_id(db, "ENGINE_OIL_CHANGE"),
        "performed_on": _day(1).isoformat(),
        "labor_cost": "100",
    }
    bad = client.post(
        "/api/v1/maintenance/records",
        json={"vehicle_id": v, **base, "fuel_transaction_id": cng_fill},
        headers=h,
    )
    assert bad.status_code == 422
    ok = _record(client, h, v, **base, fuel_transaction_id=oil_purchase)
    assert ok["fuel_transaction_id"] == oil_purchase
    # The purchase itself stays a consumable cost, separate from the service labour.
    assert ok["total_cost"] == "100.00"


def test_correction_replaces_an_approved_record(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ADMIN)
    vehicle = make_vehicle(db)
    original = _record(
        client,
        h,
        str(vehicle.id),
        type_id=_type_id(db, "TIRES"),
        performed_on=_day(3).isoformat(),
        parts_cost="3000",
        approve_now=True,
    )
    res = client.post(
        f"/api/v1/maintenance/records/{original['id']}/correct",
        json={
            "vehicle_id": str(vehicle.id),
            "type_id": _type_id(db, "TIRES"),
            "performed_on": _day(3).isoformat(),
            "parts_cost": "3200",
            "reason": "فاتورة الإطارات النهائية",
            "approve_now": True,
        },
        headers=h,
    )
    assert res.status_code == 201, res.text
    assert res.json()["corrects_id"] == original["id"]
    old = client.get(f"/api/v1/maintenance/records/{original['id']}", headers=h).json()
    assert old["status"] == "VOIDED"
    assert old["corrected_by_id"] == res.json()["id"]


def test_approved_maintenance_counts_in_vehicle_pnl(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ADMIN)
    vehicle = make_vehicle(db)
    v = str(vehicle.id)
    _record(
        client,
        h,
        v,
        type_id=_type_id(db, "BRAKES"),
        performed_on=_day(2).isoformat(),
        parts_cost="500",
        approve_now=True,
    )
    _record(
        client,
        h,
        v,
        type_id=_type_id(db, "BRAKES"),
        performed_on=_day(2).isoformat(),
        parts_cost="999",
    )  # pending: excluded
    pnl = client.get(
        "/api/v1/profitability/vehicles",
        params={"date_from": _day(7).isoformat(), "date_to": _day(0).isoformat(), "vehicle_id": v},
        headers=h,
    ).json()["vehicles"][0]
    assert pnl["maintenance_cost"] == "500.00"
    codes = {w["code"]: w for w in pnl["warnings"]}
    assert codes["PENDING_RECORDS"]["count"] == 1
