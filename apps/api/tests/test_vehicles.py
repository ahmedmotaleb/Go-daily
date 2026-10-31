from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today
from app.models.audit import AuditLog
from tests.factories import login_as, make_driver, make_vehicle, vehicle_type_id

V = "/api/v1/vehicles"


def _body(db: Session, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "internal_code": "gd-101",
        "plate_number": "أ ب ج ١٢٣٤",
        "vehicle_type_id": vehicle_type_id(db),
        "manufacturer": "Toyota",
        "model": "HiAce",
        "model_year": 2019,
        "color": "أبيض",
        "ownership_status": "OWNED",
        "current_odometer_km": 182000,
    }
    body.update(overrides)
    return body


def test_vehicle_types_are_seeded(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    res = client.get("/api/v1/vehicle-types", headers=h)
    assert res.status_code == 200
    codes = [t["code"] for t in res.json()]
    assert codes[:5] == ["MICROBUS", "SEDAN", "VAN", "BUS", "OTHER"]


def test_vehicle_types_are_extensible_by_admin_only(client: TestClient, db: Session) -> None:
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    _, admin = login_as(client, db, UserRole.ADMIN)
    body = {"code": "pickup", "name_ar": "نصف نقل"}
    assert client.post("/api/v1/vehicle-types", headers=ops, json=body).status_code == 403
    res = client.post("/api/v1/vehicle-types", headers=admin, json=body)
    assert res.status_code == 201
    assert res.json()["code"] == "PICKUP"
    dup = client.post("/api/v1/vehicle-types", headers=admin, json=body)
    assert dup.status_code == 409


def test_create_and_get_vehicle(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    res = client.post(V, headers=h, json=_body(db))
    assert res.status_code == 201, res.text
    v = res.json()
    assert v["internal_code"] == "GD-101"
    assert v["plate_number"] == "أ ب ج ١٢٣٤"
    assert v["vehicle_type"]["code"] == "MICROBUS"
    assert v["license_status"] == "UNKNOWN"
    assert v["current_assignments"] == []
    detail = client.get(f"{V}/{v['id']}", headers=h)
    assert detail.status_code == 200
    assert db.scalar(
        select(AuditLog).where(AuditLog.action == "vehicle.created", AuditLog.entity_id == v["id"])
    )


def test_plate_and_code_uniqueness_is_normalised(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    assert client.post(V, headers=h, json=_body(db)).status_code == 201
    same_plate = client.post(
        V, headers=h, json=_body(db, internal_code="GD-102", plate_number="ا-ب-ج 1234")
    )
    assert same_plate.status_code == 409
    assert same_plate.json()["error"]["code"] == "vehicle_plate_taken"
    same_code = client.post(V, headers=h, json=_body(db, plate_number="س ص 99"))
    assert same_code.status_code == 409
    assert same_code.json()["error"]["code"] == "vehicle_code_taken"


@pytest.mark.parametrize(
    ("field", "value"),
    [("model_year", 1800), ("current_odometer_km", -5), ("vehicle_type_id", "not-a-uuid")],
)
def test_vehicle_validation(client: TestClient, db: Session, field: str, value: object) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    res = client.post(V, headers=h, json=_body(db, **{field: value}))
    assert res.status_code == 422


def test_unknown_vehicle_type_rejected(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    res = client.post(
        V, headers=h, json=_body(db, vehicle_type_id="00000000-0000-0000-0000-000000000000")
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "invalid_vehicle_type"


def test_search_filter_and_pagination(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    make_vehicle(db, internal_code="ZZ-001", plate_number="ن ه و ٧٧٧", manufacturer="Kia")
    make_vehicle(db, internal_code="ZZ-002", plate_number="ن ه و 778", is_active=False)
    van = make_vehicle(
        db, internal_code="ZZ-003", vehicle_type_id=vehicle_type_id(db, "VAN"), plate_number="م 1"
    )

    assert client.get(V, headers=h, params={"q": "نهو777"}).json()["total"] == 1
    assert client.get(V, headers=h, params={"q": "kia"}).json()["total"] == 1
    assert client.get(V, headers=h, params={"q": "ZZ-", "is_active": False}).json()["total"] == 1
    by_type = client.get(V, headers=h, params={"vehicle_type_id": str(van.vehicle_type_id)})
    assert [i["internal_code"] for i in by_type.json()["items"]] == ["ZZ-003"]
    page = client.get(V, headers=h, params={"q": "ZZ-", "page_size": 2, "page": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1


def test_expiry_indicators_and_filter(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    today = local_today()
    make_vehicle(db, internal_code="EX-1", license_expiry=today - timedelta(days=1))
    make_vehicle(db, internal_code="EX-2", insurance_expiry=today + timedelta(days=10))
    make_vehicle(db, internal_code="EX-3", license_expiry=today + timedelta(days=200))

    items = {
        v["internal_code"]: v for v in client.get(V, headers=h, params={"q": "EX-"}).json()["items"]
    }
    assert items["EX-1"]["license_status"] == "EXPIRED"
    assert items["EX-2"]["insurance_status"] == "EXPIRING_SOON"
    assert items["EX-3"]["license_status"] == "OK"

    def codes(expiry: str) -> list[str]:
        res = client.get(V, headers=h, params={"q": "EX-", "expiry": expiry})
        return sorted(v["internal_code"] for v in res.json()["items"])

    assert codes("expired") == ["EX-1"]
    assert codes("expiring") == ["EX-2"]
    assert codes("attention") == ["EX-1", "EX-2"]


def test_update_vehicle_and_odometer_rules(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    v = make_vehicle(db, current_odometer_km=150_000)
    res = client.patch(
        f"{V}/{v.id}", headers=h, json={"color": "فضي", "current_odometer_km": 151000}
    )
    assert res.status_code == 200
    assert res.json()["color"] == "فضي"

    lower = client.patch(f"{V}/{v.id}", headers=h, json={"current_odometer_km": 140000})
    assert lower.status_code == 422
    assert lower.json()["error"]["code"] == "odometer_decrease_requires_reason"

    fixed = client.patch(
        f"{V}/{v.id}",
        headers=h,
        json={"current_odometer_km": 140000, "odometer_correction_reason": "خطأ إدخال سابق"},
    )
    assert fixed.status_code == 200
    entry = db.scalar(
        select(AuditLog)
        .where(AuditLog.entity_id == str(v.id), AuditLog.action == "vehicle.updated")
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id)
        .where(AuditLog.reason.is_not(None))
    )
    assert entry is not None and entry.reason == "خطأ إدخال سابق"
    assert entry.changes == {"current_odometer_km": {"old": 151000, "new": 140000}}


def test_deactivation_rules(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    v = make_vehicle(db)
    d = make_driver(db)
    a = client.post(
        "/api/v1/assignments", headers=h, json={"driver_id": str(d.id), "vehicle_id": str(v.id)}
    )
    assert a.status_code == 201
    blocked = client.post(f"{V}/{v.id}/deactivate", headers=h, json={"reason": "عطل"})
    assert blocked.status_code == 409
    client.post(f"/api/v1/assignments/{a.json()['id']}/end", headers=h, json={})
    ok = client.post(f"{V}/{v.id}/deactivate", headers=h, json={"reason": "عطل كبير"})
    assert ok.status_code == 200 and ok.json()["is_active"] is False
    again = client.post(f"{V}/{v.id}/activate", headers=h, json={})
    assert again.json()["is_active"] is True


def test_vehicle_permissions(client: TestClient, db: Session) -> None:
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    _, drv = login_as(client, db, UserRole.DRIVER)
    assert client.get(V, headers=acc).status_code == 200
    assert client.post(V, headers=acc, json=_body(db)).status_code == 403
    assert client.get(V, headers=drv).status_code == 403
    assert client.get(V).status_code == 401
