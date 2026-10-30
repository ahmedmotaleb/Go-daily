from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.shift import Shift
from tests.factories import (
    login_as,
    make_driver_account,
    make_route,
    make_vehicle,
    operation_type_id,
)

DA = "/api/v1/driver"


def test_driver_me_lists_assigned_vehicles(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    me = client.get(f"{DA}/me", headers=h)
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["driver_id"] == str(driver.id)
    assert [v["id"] for v in body["vehicles"]] == [str(vehicle.id)]
    assert body["vehicles"][0]["last_odometer_km"] == 50_000
    assert body["active_shift"] is None


def test_driver_start_and_end_shift_with_idempotency(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    route = make_route(db)
    body = {
        "vehicle_id": str(vehicle.id),
        "start_odometer_km": 50_010,
        "operation_type_id": operation_type_id(db),
        "route_id": str(route.id),
    }
    headers = {**h, "Idempotency-Key": "start-abc-1"}
    first = client.post(f"{DA}/shifts/start", headers=headers, json=body)
    assert first.status_code == 201, first.text
    retry = client.post(f"{DA}/shifts/start", headers=headers, json=body)
    assert retry.status_code == 201
    assert retry.json()["id"] == first.json()["id"]
    assert (
        db.scalar(select(func.count()).select_from(Shift).where(Shift.driver_id == driver.id)) == 1
    )
    assert first.json()["source"] == "DRIVER_APP"
    assert first.json()["active_session"]["route"]["id"] == str(route.id)

    reused = client.post(
        f"{DA}/shifts/start", headers=headers, json={**body, "start_odometer_km": 50_020}
    )
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "idempotency_key_reused"

    shift_id = first.json()["id"]
    end_headers = {**h, "Idempotency-Key": "end-abc-1"}
    end = client.post(
        f"{DA}/shifts/{shift_id}/end", headers=end_headers, json={"end_odometer_km": 50_090}
    )
    assert end.status_code == 200
    again = client.post(
        f"{DA}/shifts/{shift_id}/end", headers=end_headers, json={"end_odometer_km": 50_090}
    )
    assert again.status_code == 200 and again.json()["status"] == "COMPLETED"


def test_driver_cannot_use_unassigned_vehicle(client: TestClient, db: Session) -> None:
    _, _, h, _ = make_driver_account(client, db)
    other = make_vehicle(db, current_odometer_km=10)
    res = client.post(
        f"{DA}/shifts/start", headers=h, json={"vehicle_id": str(other.id), "start_odometer_km": 10}
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "not_assigned_to_vehicle"


def test_driver_cannot_backdate_or_touch_other_shifts(client: TestClient, db: Session) -> None:
    _, _, h1, v1 = make_driver_account(client, db)
    _, _, h2, _ = make_driver_account(client, db)
    shift = client.post(
        f"{DA}/shifts/start",
        headers=h1,
        json={"vehicle_id": str(v1.id), "start_odometer_km": 50_000},
    ).json()
    res = client.post(
        f"{DA}/shifts/{shift['id']}/end", headers=h2, json={"end_odometer_km": 50_100}
    )
    assert res.status_code == 404


def test_driver_switches_operation(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    school = make_route(db, code="SCHOOL_ROUTE", name="مدرسة")
    shift = client.post(
        f"{DA}/shifts/start",
        headers=h,
        json={"vehicle_id": str(vehicle.id), "start_odometer_km": 50_000},
    ).json()
    res = client.post(
        f"{DA}/shifts/{shift['id']}/sessions",
        headers=h,
        json={
            "operation_type_id": operation_type_id(db, "SCHOOL_ROUTE"),
            "route_id": str(school.id),
        },
    )
    assert res.status_code == 201
    active = client.get(f"{DA}/shifts/active", headers=h).json()
    assert active["active_session"]["operation_type"]["code"] == "SCHOOL_ROUTE"
    end = client.post(f"{DA}/sessions/{res.json()['id']}/end", headers=h)
    assert end.json()["status"] == "COMPLETED"


def test_driver_catalog_and_today(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    make_route(db)
    catalog = client.get(f"{DA}/catalog", headers=h).json()
    assert any(t["code"] == "FIXED_ROUTE" for t in catalog["operation_types"])
    assert catalog["routes"]
    client.post(
        f"{DA}/shifts/start",
        headers=h,
        json={"vehicle_id": str(vehicle.id), "start_odometer_km": 50_000},
    )
    assert len(client.get(f"{DA}/shifts/today", headers=h).json()) == 1


def test_staff_cannot_use_driver_endpoints(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ADMIN)
    assert client.get(f"{DA}/me", headers=h).status_code == 403


def test_driver_account_without_profile_is_rejected(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.DRIVER)
    res = client.get(f"{DA}/me", headers=h)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "no_driver_profile"
