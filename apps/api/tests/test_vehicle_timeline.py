"""Vehicle daily timeline (U24): recorded items in order, filtered by permission."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from tests.factories import fuel_type_id, login_as, make_driver_account, start_photo
from tests.test_driver_cash import CLOSE


def test_timeline_lists_the_day_in_order(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = client.post(
        "/api/v1/driver/shifts/start",
        headers=h,
        json={
            "vehicle_id": str(vehicle.id),
            "start_odometer_km": 50_000,
            "start_odometer_photo_id": start_photo(client, h),
        },
    ).json()
    client.post(
        "/api/v1/driver/fuel",
        headers=h,
        json={"fuel_type_id": fuel_type_id(db, "CNG"), "quantity": "20", "total_amount": "200"},
    )
    res = client.post(f"/api/v1/driver/shifts/{shift['id']}/closeout", headers=h, json=CLOSE)
    assert res.status_code == 201, res.text

    _, admin = login_as(client, db, UserRole.ADMIN)
    items = client.get(f"/api/v1/vehicles/{vehicle.id}/timeline", headers=admin).json()
    kinds = [i["kind"] for i in items]
    # Revenue is dated by day (no time) and comes first; the rest follows the clock.
    assert kinds[0] == "REVENUE"
    timed = [i["at"] for i in items if i["at"]]
    assert timed == sorted(timed)
    for kind in ("SHIFT_START", "FUEL", "EXPENSE", "SHIFT_END", "CLOSEOUT"):
        assert kind in kinds, kind
    assert kinds.index("SHIFT_START") < kinds.index("SHIFT_END")
    # Statuses are shown in Arabic, never as raw codes.
    assert all(not (i["status"] or "").isascii() or not i["status"] for i in items)

    # Operations cannot read revenue: those items are left out, not blanked
    # (close-outs stay: operations has cash:read).
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    seen = {
        i["kind"] for i in client.get(f"/api/v1/vehicles/{vehicle.id}/timeline", headers=ops).json()
    }
    assert "REVENUE" not in seen
    assert {"SHIFT_START", "FUEL", "CLOSEOUT"} <= seen
