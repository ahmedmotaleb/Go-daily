"""Security audit M10 / runtime M1: the phone's position at fuelling is driver location.

Accountants hold fuel:read but are barred from tracking, so fuel records
reach them without coordinates; tracking readers still see them.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from tests.factories import fuel_type_id, login_as, make_driver_account, start_photo

DA = "/api/v1/driver"


def test_fuel_coordinates_only_for_tracking_readers(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = client.post(
        f"{DA}/shifts/start",
        headers=h,
        json={
            "vehicle_id": str(vehicle.id),
            "start_odometer_km": 50_000,
            "start_odometer_photo_id": start_photo(client, h),
        },
    )
    assert shift.status_code == 201, shift.text
    fuel = client.post(
        f"{DA}/fuel",
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "fuel_type_id": fuel_type_id(db, "CNG"),
            "quantity": "20",
            "total_amount": "140",
            "latitude": 31.0409,
            "longitude": 31.3785,
            "location_accuracy_m": 12,
        },
    )
    assert fuel.status_code == 201, fuel.text
    tx = fuel.json()["id"]
    _, ac = login_as(client, db, UserRole.ACCOUNTANT)
    _, op = login_as(client, db, UserRole.OPERATIONS)

    for url in (f"/api/v1/fuel/{tx}", "/api/v1/fuel"):
        text = client.get(url, headers=ac).text
        assert "31.3785" not in text and "31.0409" not in text, url
    shown = client.get(f"/api/v1/fuel/{tx}", headers=ac).json()
    assert shown["latitude"] is None and shown["location_accuracy_m"] is None
    approved = client.post(f"/api/v1/fuel/{tx}/approve", headers=ac, json={})
    assert approved.status_code == 200 and approved.json()["longitude"] is None

    seen = client.get(f"/api/v1/fuel/{tx}", headers=op).json()
    assert seen["latitude"] == 31.0409 and seen["longitude"] == 31.3785
