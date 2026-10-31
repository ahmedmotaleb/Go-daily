from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today
from tests.factories import (
    assign,
    login_as,
    make_driver,
    make_route,
    make_vehicle,
    operation_type_id,
)


def test_dashboard_reflects_database_state(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    base = client.get("/api/v1/dashboard/summary", headers=h).json()["kpis"]

    v1 = make_vehicle(
        db, current_odometer_km=1000, insurance_expiry=local_today() + timedelta(days=5)
    )
    make_vehicle(db, is_active=False)
    d1 = make_driver(db, full_name="سائق اللوحة", license_expiry=local_today() - timedelta(days=1))
    d1.license_expiry = local_today() + timedelta(days=3)
    db.commit()
    assign(db, d1, v1)
    route = make_route(db)
    shift = client.post(
        "/api/v1/shifts",
        headers=h,
        json={
            "driver_id": str(d1.id),
            "vehicle_id": str(v1.id),
            "start_now": True,
            "start_odometer_km": 1000,
            "planned_operation_type_id": operation_type_id(db),
            "planned_route_id": str(route.id),
        },
    )
    assert shift.status_code == 201, shift.text

    res = client.get("/api/v1/dashboard/summary", headers=h)
    assert res.status_code == 200
    data = res.json()
    k = data["kpis"]
    assert k["active_vehicles"] == base["active_vehicles"] + 1
    assert k["active_drivers"] == base["active_drivers"] + 1
    assert k["active_shifts"] == base["active_shifts"] + 1
    assert k["today_shifts"] == base["today_shifts"] + 1

    row = next(r for r in data["vehicles"] if r["id"] == str(v1.id))
    assert row["in_shift"] is True
    assert row["driver_name"] == "سائق اللوحة"
    assert "خط ثابت" in row["current_operation"]

    kinds = {(d["kind"], d["entity_id"]) for d in data["expiring_documents"]}
    assert ("VEHICLE_INSURANCE", str(v1.id)) in kinds
    assert ("DRIVER_LICENSE", str(d1.id)) in kinds
    assert any(a["action"] == "shift.started" for a in data["recent_activity"])
    assert any(s["id"] == shift.json()["id"] for s in data["active_shifts"])


def test_dashboard_requires_staff(client: TestClient, db: Session) -> None:
    _, drv = login_as(client, db, UserRole.DRIVER)
    assert client.get("/api/v1/dashboard/summary", headers=drv).status_code == 403
