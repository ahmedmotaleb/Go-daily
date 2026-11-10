"""Driver daily timeline (U25): the driver's day across vehicles, with strict RBAC."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today
from tests.factories import fuel_type_id, login_as, make_driver_account
from tests.test_driver_cash import _close, _start


def test_driver_day_in_order_with_account_entries(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle)
    client.post(
        "/api/v1/driver/fuel",
        headers=h,
        json={"fuel_type_id": fuel_type_id(db, "CNG"), "quantity": "20", "total_amount": "200"},
    )
    _close(client, h, shift["id"])
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    client.post(
        "/api/v1/cash/collections", headers=acc, json={"driver_id": str(driver.id), "amount": "500"}
    )
    client.post(
        f"/api/v1/drivers/{driver.id}/ledger",
        headers=acc,
        json={
            "entry_type": "ADVANCE",
            "amount": "300",
            "occurred_on": local_today().isoformat(),
            "description": "سلفة",
        },
    )

    _, admin = login_as(client, db, UserRole.ADMIN)
    items = client.get(f"/api/v1/drivers/{driver.id}/timeline", headers=admin).json()
    kinds = [i["kind"] for i in items]
    for kind in ("SHIFT_START", "FUEL", "SHIFT_END", "CLOSEOUT", "CASH", "LEDGER", "REVENUE"):
        assert kind in kinds, kind
    timed = [i["at"] for i in items if i["at"]]
    assert timed == sorted(timed)
    assert any(i["kind"] == "LEDGER" and i["title"] == "سلفة" for i in items)
    # Cash mirrored in the account is not listed twice.
    assert not any(i["kind"] == "LEDGER" and i["title"] == "تسليم نقدية" for i in items)

    # Operations: no money of the driver (revenue, account entries).
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    seen = {
        i["kind"] for i in client.get(f"/api/v1/drivers/{driver.id}/timeline", headers=ops).json()
    }
    assert "LEDGER" not in seen and "REVENUE" not in seen
    assert {"SHIFT_START", "FUEL"} <= seen


def test_day_off_is_shown(client: TestClient, db: Session) -> None:
    driver, _, h, _ = make_driver_account(client, db)
    res = client.post("/api/v1/driver/day-off", headers=h, json={"note": "ظرف عائلي"})
    assert res.status_code in (200, 201), res.text
    _, admin = login_as(client, db, UserRole.ADMIN)
    items = client.get(f"/api/v1/drivers/{driver.id}/timeline", headers=admin).json()
    assert items[0]["kind"] == "DAY_OFF" and items[0]["detail"] == "ظرف عائلي"
