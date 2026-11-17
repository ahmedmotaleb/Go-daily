"""Fuel stations and vendors (U16)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import utcnow
from app.models.audit import AuditLog
from tests.factories import fuel_type_id, login_as, make_driver_account, make_vehicle
from tests.test_driver_cash import _start

URL = "/api/v1/fuel-stations"
HERE = (30.0444, 31.2357)


def _station(client: TestClient, h: dict[str, str], **body: Any) -> Any:
    res = client.post(URL, headers=h, json={"name": "محطة التحرير", **body})
    assert res.status_code == 201, res.text
    return res.json()


def _buy(client: TestClient, h: dict[str, str], vehicle: str, **body: Any) -> Any:
    payload = {
        "vehicle_id": vehicle,
        "quantity": "10",
        "occurred_at": (utcnow() - timedelta(hours=2)).isoformat(),
        "approve_now": True,
        **body,
    }
    res = client.post("/api/v1/fuel", headers=h, json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_station_master_is_managed_and_audited(client: TestClient, db: Session) -> None:
    _, admin = login_as(client, db, UserRole.ADMIN)
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    cng = fuel_type_id(db, "CNG")

    # Only settings managers create or edit; fuel readers can list.
    denied = client.post(URL, headers=acc, json={"name": "x"})
    assert denied.status_code == 403
    trusted_without_location = client.post(
        URL, headers=admin, json={"name": "x", "is_trusted": True}
    )
    assert trusted_without_location.status_code == 422
    half_location = client.post(URL, headers=admin, json={"name": "x", "latitude": 30})
    assert half_location.status_code == 422

    station = _station(client, admin, brand="وطنية", fuel_type_ids=[cng])
    assert [t["code"] for t in station["fuel_types"]] == ["CNG"]
    assert any(s["id"] == station["id"] for s in client.get(URL, headers=acc).json())

    # Deactivated, never deleted: hidden from the pick list, kept in history.
    res = client.patch(f"{URL}/{station['id']}", headers=admin, json={"is_active": False})
    assert res.status_code == 200 and res.json()["is_active"] is False
    assert all(s["id"] != station["id"] for s in client.get(URL, headers=acc).json())
    listed = client.get(URL, headers=acc, params={"include_inactive": True}).json()
    assert any(s["id"] == station["id"] for s in listed)
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity_id == station["id"])).all()
    assert set(actions) == {"fuel_station.created", "fuel_station.updated"}

    # An inactive station cannot be picked for a new purchase.
    vehicle = str(make_vehicle(db).id)
    res = client.post(
        "/api/v1/fuel",
        headers=acc,
        json={
            "vehicle_id": vehicle,
            "fuel_type_id": cng,
            "quantity": "10",
            "total_amount": "100",
            "occurred_at": (utcnow() - timedelta(hours=1)).isoformat(),
            "station_id": station["id"],
        },
    )
    assert res.status_code == 422


def test_station_prices_compare_with_the_fleet(client: TestClient, db: Session) -> None:
    _, admin = login_as(client, db, UserRole.ADMIN)
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    cng = fuel_type_id(db, "CNG")
    station = _station(client, admin, name="محطة غالية")
    vehicle = str(make_vehicle(db).id)

    a = _buy(client, acc, vehicle, fuel_type_id=cng, total_amount="120", station_id=station["id"])
    _buy(client, acc, vehicle, fuel_type_id=cng, total_amount="130", station_id=station["id"])
    # Elsewhere, cheaper: the fleet average includes every approved purchase.
    _buy(client, acc, vehicle, fuel_type_id=cng, total_amount="50", vendor="أخرى")
    assert a["station"]["name"] == "محطة غالية"
    assert a["vendor"] == "محطة غالية"  # filled from the station when left empty

    detail = client.get(f"{URL}/{station['id']}", headers=acc).json()
    [price] = [p for p in detail["prices"] if p["fuel_type"]["code"] == "CNG"]
    assert price["count"] == 2
    assert price["average_price"] == "12.500"
    assert price["min_price"] == "12.000" and price["max_price"] == "13.000"
    # The fleet's average for CNG covers all three purchases (300 / 30 = 10).
    assert price["fleet_average_price"] == "10.000"
    assert price["difference_pct"] == "25.0"
    assert detail["transactions_count"] == 2 and len(detail["recent"]) == 2
    assert detail["monthly"][0]["count"] == 2

    filtered = client.get("/api/v1/fuel", headers=acc, params={"station_id": station["id"]})
    assert filtered.json()["total"] == 2


def test_driver_purchase_inside_a_trusted_station_is_linked(
    client: TestClient, db: Session
) -> None:
    _, admin = login_as(client, db, UserRole.ADMIN)
    trusted = _station(
        client,
        admin,
        name="محطة موثوقة",
        latitude=HERE[0],
        longitude=HERE[1],
        radius_m=200,
        is_trusted=True,
    )
    # A known but untrusted station at the same place is never matched.
    _station(client, admin, name="غير موثوقة", latitude=HERE[0], longitude=HERE[1])
    _, _, h, vehicle = make_driver_account(client, db)
    _start(client, h, vehicle)
    cng = fuel_type_id(db, "CNG")

    def buy(lat: float, accuracy: float = 10) -> Any:
        res = client.post(
            "/api/v1/driver/fuel",
            headers=h,
            json={
                "fuel_type_id": cng,
                "quantity": "10",
                "total_amount": "100",
                "latitude": lat,
                "longitude": HERE[1],
                "location_accuracy_m": accuracy,
            },
        )
        assert res.status_code == 201, res.text
        return client.get(f"/api/v1/fuel/{res.json()['id']}", headers=admin).json()

    inside = buy(HERE[0] + 0.001)  # ~110 m away
    assert inside["station"]["id"] == trusted["id"]
    # A new station far away is accepted as is, just not linked.
    outside = buy(HERE[0] + 0.01)  # ~1.1 km away
    assert outside["station"] is None and outside["status"] == "SUBMITTED"
    assert outside["vendor"] is None
    # Too imprecise a location links nothing.
    assert buy(HERE[0], accuracy=500)["station"] is None
