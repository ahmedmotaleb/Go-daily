"""Oil and service reconciliation (U17)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import utcnow
from tests.factories import expense_category_id, fuel_type_id, login_as, make_vehicle
from tests.test_maintenance import _day, _due, _record, _type_id

URL = "/api/v1/maintenance/oil-reconciliation"


def _purchase(
    client: TestClient, db: Session, h: dict[str, str], v: str, code: str, qty: str, days: int
) -> str:
    res = client.post(
        "/api/v1/fuel",
        headers=h,
        json={
            "vehicle_id": v,
            "fuel_type_id": fuel_type_id(db, code),
            "quantity": qty,
            "total_amount": "500",
            "occurred_at": (utcnow() - timedelta(days=days)).isoformat(),
            "approve_now": True,
        },
    )
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def _expense(client: TestClient, db: Session, h: dict[str, str], v: str, days: int) -> str:
    res = client.post(
        "/api/v1/expenses",
        headers=h,
        json={
            "vehicle_id": v,
            "category_id": expense_category_id(db, "OIL_CHANGE"),
            "amount": "350",
            "occurred_at": (utcnow() - timedelta(days=days)).isoformat(),
            "approve_now": True,
        },
    )
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def test_service_stores_quantity_grade_and_next_targets(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ADMIN)
    vehicle = make_vehicle(db, current_odometer_km=60_000)
    v = str(vehicle.id)
    oil = _type_id(db, "ENGINE_OIL_CHANGE")  # 5000 km / 90 days by default
    client.put(f"/api/v1/maintenance/vehicles/{v}/schedules", json={"type_id": oil}, headers=h)

    # Blank targets come from the interval.
    rec = _record(
        client,
        h,
        v,
        type_id=oil,
        performed_on=_day(10).isoformat(),
        odometer_km=59_000,
        consumable_quantity="4.5",
        consumable_spec="5W-30",
        parts_cost="400",
    )
    assert Decimal(rec["consumable_quantity"]) == Decimal("4.5")
    assert rec["consumable_spec"] == "5W-30"
    assert rec["next_due_km"] == 64_000
    assert rec["next_due_on"] == (_day(10) + timedelta(days=90)).isoformat()

    # A target decided at the service (a shorter interval for a worn engine) wins.
    rec2 = _record(
        client,
        h,
        v,
        type_id=oil,
        performed_on=_day(2).isoformat(),
        odometer_km=59_900,
        next_due_km=62_000,
        approve_now=True,
    )
    assert rec2["next_due_km"] == 62_000
    assert _due(client, h, v)["ENGINE_OIL_CHANGE"]["next_due_km"] == 62_000

    bad = client.post(
        "/api/v1/maintenance/records",
        headers=h,
        json={
            "vehicle_id": v,
            "type_id": oil,
            "performed_on": _day(1).isoformat(),
            "odometer_km": 60_000,
            "next_due_km": 59_000,
        },
    )
    assert bad.status_code == 422

    # An oil change links only to an engine-oil purchase, not another consumable.
    other = _purchase(client, db, h, v, "OTHER", "1", 1)
    wrong = client.post(
        "/api/v1/maintenance/records",
        headers=h,
        json={
            "vehicle_id": v,
            "type_id": oil,
            "performed_on": _day(1).isoformat(),
            "fuel_transaction_id": other,
        },
    )
    assert wrong.status_code == 422
    assert wrong.json()["error"]["code"] == "consumable_mismatch"


def test_reconciliation_lists_what_to_check(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ADMIN)
    v = str(make_vehicle(db).id)
    oil = _type_id(db, "ENGINE_OIL_CHANGE")

    bulk = _purchase(client, db, h, v, "ENGINE_OIL", "8", 20)
    unlinked = _purchase(client, db, h, v, "ENGINE_OIL", "4", 15)
    for days, qty in ((19, "4"), (12, "5")):
        _record(
            client,
            h,
            v,
            type_id=oil,
            performed_on=_day(days).isoformat(),
            fuel_transaction_id=bulk,
            consumable_quantity=qty,
        )
    no_quantity = _record(client, h, v, type_id=oil, performed_on=_day(5).isoformat())
    matched = _expense(client, db, h, v, 6)  # the service 5 days ago is 1 day away
    orphan = _expense(client, db, h, v, 30)

    _, ops = login_as(client, db, UserRole.OPERATIONS)
    res = client.get(URL, headers=ops, params={"vehicle_id": v, "date_from": _day(40).isoformat()})
    assert res.status_code == 200, res.text
    data = res.json()
    purchases = {p["id"]: p for p in data["purchases"]}
    assert purchases[bulk]["status"] == "OVER_USED"
    assert Decimal(purchases[bulk]["used"]) == 9 and len(purchases[bulk]["services"]) == 2
    assert purchases[unlinked]["status"] == "NOT_LINKED"
    services = {s["id"]: s for s in data["services"]}
    assert services[no_quantity["id"]]["status"] == "NO_QUANTITY"
    expenses = {e["id"]: e for e in data["expenses"]}
    assert expenses[matched]["status"] == "MATCHED"
    assert expenses[matched]["service_id"] == no_quantity["id"]
    assert expenses[orphan]["status"] == "NO_SERVICE"
    # Over-used purchase, unlinked purchase, service without quantity, orphan expense.
    assert data["to_check"] == 4
    assert "مراجعة مطلوبة" in purchases[bulk]["label"]

    too_long = client.get(URL, headers=ops, params={"date_from": _day(400).isoformat()})
    assert too_long.status_code == 422
