from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from app.models.audit import AuditLog
from app.models.fleet import Vehicle
from app.models.shift import Shift, ShiftStatus
from tests.factories import (
    assign,
    login_as,
    make_driver,
    make_route,
    make_vehicle,
    operation_type_id,
)

S = "/api/v1/shifts"


@pytest.fixture()
def setup(client: TestClient, db: Session):
    _, h = login_as(client, db, UserRole.OPERATIONS)
    vehicle = make_vehicle(db, current_odometer_km=120_000)
    driver = make_driver(db)
    assign(db, driver, vehicle)
    return h, driver, vehicle


def _start(client, h, driver, vehicle, **kw):
    body = {
        "driver_id": str(driver.id),
        "vehicle_id": str(vehicle.id),
        "start_now": True,
        "start_odometer_km": 120_010,
        **kw,
    }
    return client.post(S, headers=h, json=body)


def test_plan_then_start_then_end(client: TestClient, db: Session, setup) -> None:
    h, driver, vehicle = setup
    planned = client.post(
        S,
        headers=h,
        json={
            "driver_id": str(driver.id),
            "vehicle_id": str(vehicle.id),
            "planned_start_at": (utcnow() + timedelta(hours=1)).isoformat(),
        },
    )
    assert planned.status_code == 201, planned.text
    shift = planned.json()
    assert shift["status"] == "PLANNED"

    started = client.post(
        f"{S}/{shift['id']}/start", headers=h, json={"start_odometer_km": 120_050}
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "ACTIVE"
    assert db.get(Vehicle, vehicle.id).current_odometer_km == 120_050  # type: ignore[union-attr]

    ended = client.post(f"{S}/{shift['id']}/end", headers=h, json={"end_odometer_km": 120_230})
    assert ended.status_code == 200, ended.text
    body = ended.json()
    assert body["status"] == "COMPLETED"
    assert body["odometer_distance_km"] == 180
    db.expire_all()
    assert db.get(Vehicle, vehicle.id).current_odometer_km == 120_230  # type: ignore[union-attr]
    actions = db.scalars(
        select(AuditLog.action)
        .where(AuditLog.entity_id == shift["id"])
        .order_by(AuditLog.occurred_at)
    ).all()
    assert {"shift.planned", "shift.started", "shift.ended"} <= set(actions)


def test_end_odometer_cannot_be_lower_than_start(client: TestClient, db: Session, setup) -> None:
    h, driver, vehicle = setup
    shift = _start(client, h, driver, vehicle).json()
    res = client.post(f"{S}/{shift['id']}/end", headers=h, json={"end_odometer_km": 120_000})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "end_odometer_below_start"
    implausible = client.post(
        f"{S}/{shift['id']}/end", headers=h, json={"end_odometer_km": 125_000}
    )
    assert implausible.json()["error"]["code"] == "implausible_odometer"


def test_start_odometer_cannot_go_below_last_reading(
    client: TestClient, db: Session, setup
) -> None:
    h, driver, vehicle = setup
    res = _start(client, h, driver, vehicle, start_odometer_km=119_000)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "odometer_below_last_reading"
    assert res.json()["error"]["details"]["last_reading_km"] == 120_000
    # Nothing was persisted by the failed request.
    assert db.scalar(select(Shift).where(Shift.driver_id == driver.id)) is None


def test_one_active_shift_per_driver_and_vehicle(client: TestClient, db: Session, setup) -> None:
    h, driver, vehicle = setup
    assert _start(client, h, driver, vehicle).status_code == 201
    other_vehicle = make_vehicle(db, current_odometer_km=50_000)
    assign_other = make_driver(db)
    assign(db, assign_other, vehicle, role="RELIEF")

    second_for_vehicle = _start(client, h, assign_other, vehicle, start_odometer_km=120_020)
    assert second_for_vehicle.status_code == 409
    assert second_for_vehicle.json()["error"]["code"] == "vehicle_has_active_shift"

    second_for_driver = _start(
        client,
        h,
        driver,
        other_vehicle,
        start_odometer_km=50_000,
        assignment_override_reason="تغطية مؤقتة",
    )
    assert second_for_driver.status_code == 409
    assert second_for_driver.json()["error"]["code"] == "driver_has_active_shift"


def test_database_enforces_single_active_shift(db: Session) -> None:
    vehicle, d1, d2 = make_vehicle(db), make_driver(db), make_driver(db)
    now = utcnow()
    db.add(
        Shift(
            driver_id=d1.id,
            vehicle_id=vehicle.id,
            status=ShiftStatus.ACTIVE,
            started_at=now,
            start_odometer_km=1,
        )
    )
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            Shift(
                driver_id=d2.id,
                vehicle_id=vehicle.id,
                status=ShiftStatus.ACTIVE,
                started_at=now,
                start_odometer_km=1,
            )
        )
        db.flush()


def test_driver_must_be_assigned_unless_override(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    vehicle, driver = make_vehicle(db, current_odometer_km=10), make_driver(db)
    res = _start(client, h, driver, vehicle, start_odometer_km=10)
    assert res.json()["error"]["code"] == "driver_not_assigned"
    ok = _start(
        client,
        h,
        driver,
        vehicle,
        start_odometer_km=10,
        assignment_override_reason="سائق احتياطي اليوم",
    )
    assert ok.status_code == 201
    assert ok.json()["assignment_override_reason"] == "سائق احتياطي اليوم"


def test_expired_documents_block_start(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    vehicle = make_vehicle(db, current_odometer_km=10)
    driver = make_driver(db, license_expiry=local_today() - timedelta(days=1))
    assign(db, driver, vehicle)
    res = _start(client, h, driver, vehicle, start_odometer_km=10)
    assert res.json()["error"]["code"] == "driver_license_expired"
    driver.license_expiry = local_today() + timedelta(days=100)
    vehicle.license_expiry = local_today() - timedelta(days=2)
    db.commit()
    res = _start(client, h, driver, vehicle, start_odometer_km=10)
    assert res.json()["error"]["code"] == "vehicle_license_expired"


def test_inactive_driver_or_vehicle_rejected(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    res = _start(client, h, make_driver(db, employment_status="SUSPENDED"), make_vehicle(db))
    assert res.json()["error"]["code"] == "driver_not_active"


def test_cancel_requires_reason_and_works_from_planned_or_active(client, db, setup) -> None:
    h, driver, vehicle = setup
    shift = _start(client, h, driver, vehicle).json()
    assert client.post(f"{S}/{shift['id']}/cancel", headers=h, json={}).status_code == 422
    res = client.post(f"{S}/{shift['id']}/cancel", headers=h, json={"reason": "بدأت بالخطأ"})
    assert res.status_code == 200
    assert res.json()["status"] == "CANCELLED"
    again = client.post(f"{S}/{shift['id']}/cancel", headers=h, json={"reason": "مرة أخرى"})
    assert again.status_code == 409
    # Vehicle and driver are free again.
    assert _start(client, h, driver, vehicle).status_code == 201


def test_multiple_operation_sessions_in_one_shift(client: TestClient, db: Session, setup) -> None:
    h, driver, vehicle = setup
    route = make_route(db)
    school = make_route(db, code="SCHOOL_ROUTE", name="مدرسة النور")
    shift = _start(
        client,
        h,
        driver,
        vehicle,
    ).json()
    first = client.post(
        f"{S}/{shift['id']}/sessions",
        headers=h,
        json={"operation_type_id": operation_type_id(db, "FIXED_ROUTE"), "route_id": str(route.id)},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"{S}/{shift['id']}/sessions",
        headers=h,
        json={
            "operation_type_id": operation_type_id(db, "SCHOOL_ROUTE"),
            "route_id": str(school.id),
        },
    )
    assert second.status_code == 201

    detail = client.get(f"{S}/{shift['id']}", headers=h).json()
    statuses = [(s["operation_type"]["code"], s["status"]) for s in detail["sessions"]]
    assert statuses == [("FIXED_ROUTE", "COMPLETED"), ("SCHOOL_ROUTE", "ACTIVE")]
    assert detail["active_session"]["route"]["name"] == "مدرسة النور"

    ended = client.post(f"{S}/{shift['id']}/end", headers=h, json={"end_odometer_km": 120_100})
    assert all(s["status"] == "COMPLETED" for s in ended.json()["sessions"])


def test_session_validation(client: TestClient, db: Session, setup) -> None:
    h, driver, vehicle = setup
    school_route = make_route(db, code="SCHOOL_ROUTE", name="مدرسة")
    planned = client.post(
        S, headers=h, json={"driver_id": str(driver.id), "vehicle_id": str(vehicle.id)}
    ).json()
    not_active = client.post(
        f"{S}/{planned['id']}/sessions",
        headers=h,
        json={"operation_type_id": operation_type_id(db, "RIDE_HAILING")},
    )
    assert not_active.json()["error"]["code"] == "shift_not_active"
    client.post(f"{S}/{planned['id']}/start", headers=h, json={"start_odometer_km": 120_000})

    missing_route = client.post(
        f"{S}/{planned['id']}/sessions",
        headers=h,
        json={"operation_type_id": operation_type_id(db, "FIXED_ROUTE")},
    )
    assert missing_route.json()["error"]["code"] == "route_required"
    mismatch = client.post(
        f"{S}/{planned['id']}/sessions",
        headers=h,
        json={
            "operation_type_id": operation_type_id(db, "FIXED_ROUTE"),
            "route_id": str(school_route.id),
        },
    )
    assert mismatch.json()["error"]["code"] == "route_type_mismatch"
    ride = client.post(
        f"{S}/{planned['id']}/sessions",
        headers=h,
        json={"operation_type_id": operation_type_id(db, "RIDE_HAILING")},
    )
    assert ride.status_code == 201
    end = client.post(f"/api/v1/operation-sessions/{ride.json()['id']}/end", headers=h, json={})
    assert end.json()["status"] == "COMPLETED"


def test_planned_operation_becomes_first_session(client: TestClient, db: Session, setup) -> None:
    h, driver, vehicle = setup
    route = make_route(db)
    planned = client.post(
        S,
        headers=h,
        json={
            "driver_id": str(driver.id),
            "vehicle_id": str(vehicle.id),
            "planned_operation_type_id": operation_type_id(db, "FIXED_ROUTE"),
            "planned_route_id": str(route.id),
        },
    ).json()
    started = client.post(
        f"{S}/{planned['id']}/start", headers=h, json={"start_odometer_km": 120_000}
    )
    assert started.json()["active_session"]["route"]["id"] == str(route.id)


def test_odometer_correction_is_audited(client: TestClient, db: Session, setup) -> None:
    h, driver, vehicle = setup
    shift = _start(client, h, driver, vehicle).json()
    client.post(f"{S}/{shift['id']}/end", headers=h, json={"end_odometer_km": 120_200})
    bad = client.post(
        f"{S}/{shift['id']}/odometer-correction", headers=h, json={"end_odometer_km": 120_300}
    )
    assert bad.status_code == 422  # reason required
    ok = client.post(
        f"{S}/{shift['id']}/odometer-correction",
        headers=h,
        json={"end_odometer_km": 120_150, "reason": "خطأ في إدخال القراءة"},
    )
    assert ok.status_code == 200
    assert ok.json()["odometer_distance_km"] == 140
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "shift.odometer_corrected"))
    assert entry is not None and entry.reason == "خطأ في إدخال القراءة"
    assert entry.changes == {"end_odometer_km": {"old": 120200, "new": 120150}}


def test_list_filters_today_and_active(client: TestClient, db: Session, setup) -> None:
    h, driver, vehicle = setup
    _start(client, h, driver, vehicle)
    today = client.get(S, headers=h, params={"day": local_today().isoformat()}).json()
    assert today["total"] >= 1
    active = client.get(
        S, headers=h, params={"status": "ACTIVE", "driver_id": str(driver.id)}
    ).json()
    assert active["total"] == 1
    yesterday = (local_today() - timedelta(days=3)).isoformat()
    assert (
        client.get(S, headers=h, params={"day": yesterday, "driver_id": str(driver.id)}).json()[
            "total"
        ]
        == 0
    )


def test_backdating_limits_for_staff(client: TestClient, db: Session, setup) -> None:
    h, driver, vehicle = setup
    too_old = _start(
        client, h, driver, vehicle, started_at=(utcnow() - timedelta(days=9)).isoformat()
    )
    assert too_old.json()["error"]["code"] == "time_too_old"
    future = _start(
        client, h, driver, vehicle, started_at=(utcnow() + timedelta(hours=2)).isoformat()
    )
    assert future.json()["error"]["code"] == "time_in_future"


def test_shift_permissions(client: TestClient, db: Session, setup) -> None:
    _, driver, vehicle = setup
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    assert client.get(S, headers=acc).status_code == 200
    assert _start(client, acc, driver, vehicle).status_code == 403
