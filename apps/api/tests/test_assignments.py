from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import utcnow
from app.models.assignment import AssignmentRole, DriverVehicleAssignment
from tests.factories import login_as, make_driver, make_vehicle

A = "/api/v1/assignments"


def _assign(
    client: TestClient, h: dict[str, str], driver_id: object, vehicle_id: object, **kw: object
):
    return client.post(
        A, headers=h, json={"driver_id": str(driver_id), "vehicle_id": str(vehicle_id), **kw}
    )


def test_assign_and_current_assignment_visible_on_both_sides(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    v, d = make_vehicle(db), make_driver(db, full_name="حسن")
    res = _assign(client, h, d.id, v.id, notes="سائق الوردية الصباحية")
    assert res.status_code == 201, res.text
    assert res.json()["is_active"] is True

    vehicle = client.get(f"/api/v1/vehicles/{v.id}", headers=h).json()
    assert vehicle["current_assignments"][0]["driver_name"] == "حسن"
    driver = client.get(f"/api/v1/drivers/{d.id}", headers=h).json()
    assert driver["current_assignments"][0]["vehicle_code"] == v.internal_code


def test_overlapping_primary_assignment_is_rejected(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    v1, v2 = make_vehicle(db), make_vehicle(db)
    d1, d2 = make_driver(db), make_driver(db)
    assert _assign(client, h, d1.id, v1.id).status_code == 201

    same_vehicle = _assign(client, h, d2.id, v1.id)
    assert same_vehicle.status_code == 409
    assert same_vehicle.json()["error"]["code"] == "assignment_overlap"
    assert (
        same_vehicle.json()["error"]["details"]["conflicts"][0]["vehicle_code"] == v1.internal_code
    )

    same_driver = _assign(client, h, d1.id, v2.id)
    assert same_driver.status_code == 409


def test_replace_current_keeps_history(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    v = make_vehicle(db)
    d1, d2 = make_driver(db), make_driver(db)
    first = _assign(client, h, d1.id, v.id, starts_at=(utcnow() - timedelta(days=10)).isoformat())
    assert first.status_code == 201
    second = _assign(client, h, d2.id, v.id, replace_current=True)
    assert second.status_code == 201, second.text

    history = client.get(f"/api/v1/vehicles/{v.id}/assignments", headers=h).json()
    assert history["total"] == 2
    newest, oldest = history["items"]
    assert newest["driver_id"] == str(d2.id) and newest["is_active"]
    assert oldest["driver_id"] == str(d1.id) and oldest["ends_at"] is not None
    assert not oldest["is_active"]


def test_relief_driver_may_overlap(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    v = make_vehicle(db)
    d1, d2 = make_driver(db), make_driver(db)
    assert _assign(client, h, d1.id, v.id).status_code == 201
    relief = _assign(client, h, d2.id, v.id, role="RELIEF")
    assert relief.status_code == 201
    vehicle = client.get(f"/api/v1/vehicles/{v.id}", headers=h).json()
    assert [a["role"] for a in vehicle["current_assignments"]] == ["PRIMARY", "RELIEF"]


def test_end_assignment(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    v, d = make_vehicle(db), make_driver(db)
    a = _assign(client, h, d.id, v.id, starts_at=(utcnow() - timedelta(hours=5)).isoformat()).json()
    ended = client.post(f"{A}/{a['id']}/end", headers=h, json={"notes": "تسليم المركبة"})
    assert ended.status_code == 200
    assert ended.json()["is_active"] is False
    assert "تسليم المركبة" in ended.json()["notes"]
    twice = client.post(f"{A}/{a['id']}/end", headers=h, json={})
    assert twice.status_code == 409
    # Driver and vehicle are free again.
    assert _assign(client, h, d.id, v.id).status_code == 201


def test_end_before_start_rejected(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    v, d = make_vehicle(db), make_driver(db)
    a = _assign(client, h, d.id, v.id).json()
    res = client.post(
        f"{A}/{a['id']}/end",
        headers=h,
        json={"ends_at": (utcnow() - timedelta(days=1)).isoformat()},
    )
    assert res.status_code == 422


def test_inactive_driver_or_vehicle_cannot_be_assigned(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    res = _assign(client, h, make_driver(db, employment_status="ON_LEAVE").id, make_vehicle(db).id)
    assert res.json()["error"]["code"] == "driver_not_active"
    res = _assign(client, h, make_driver(db).id, make_vehicle(db, is_active=False).id)
    assert res.json()["error"]["code"] == "vehicle_not_active"


def test_backdated_history_overlap_is_detected(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    v = make_vehicle(db)
    d1, d2 = make_driver(db), make_driver(db)
    now = utcnow()
    closed = _assign(
        client,
        h,
        d1.id,
        v.id,
        starts_at=(now - timedelta(days=30)).isoformat(),
        ends_at=(now - timedelta(days=10)).isoformat(),
    )
    assert closed.status_code == 201
    overlapping = _assign(
        client,
        h,
        d2.id,
        v.id,
        starts_at=(now - timedelta(days=20)).isoformat(),
        ends_at=(now - timedelta(days=15)).isoformat(),
    )
    assert overlapping.status_code == 409
    after = _assign(
        client,
        h,
        d2.id,
        v.id,
        starts_at=(now - timedelta(days=10)).isoformat(),
        ends_at=(now - timedelta(days=5)).isoformat(),
    )
    assert after.status_code == 201  # touching ranges do not overlap


def test_database_rejects_overlap_even_without_the_service(db: Session) -> None:
    v, d1, d2 = make_vehicle(db), make_driver(db), make_driver(db)
    now = utcnow()
    db.add(DriverVehicleAssignment(driver_id=d1.id, vehicle_id=v.id, starts_at=now))
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            DriverVehicleAssignment(
                driver_id=d2.id,
                vehicle_id=v.id,
                starts_at=now + timedelta(hours=1),
                role=AssignmentRole.PRIMARY,
            )
        )
        db.flush()


def test_correction_requires_reason(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    v, d = make_vehicle(db), make_driver(db)
    a = _assign(client, h, d.id, v.id, starts_at=(utcnow() - timedelta(days=2)).isoformat()).json()
    new_start = (utcnow() - timedelta(days=3)).isoformat()
    no_reason = client.patch(f"{A}/{a['id']}", headers=h, json={"starts_at": new_start})
    assert no_reason.status_code == 422
    ok = client.patch(
        f"{A}/{a['id']}", headers=h, json={"starts_at": new_start, "reason": "تاريخ التسليم الفعلي"}
    )
    assert ok.status_code == 200


def test_assignment_permissions(client: TestClient, db: Session) -> None:
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    v, d = make_vehicle(db), make_driver(db)
    assert _assign(client, acc, d.id, v.id).status_code == 403
    assert client.get(A, headers=acc).status_code == 200
