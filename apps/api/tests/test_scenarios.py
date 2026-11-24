"""End-to-end operational scenarios (Task 30), driven through the public API.

Each test follows one working day the way the office and the driver app
would, then checks the answers management needs (loops, distances,
money, review cases) against the records that were entered.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, to_local_date, utcnow
from app.models.audit import AuditLog
from tests.factories import (
    expense_category_id,
    fuel_type_id,
    login_as,
    make_driver_account,
    make_platform,
    operation_type_id,
)
from tests.test_route_events_api import SCHOOL, STATION, UNIVERSITY, _points, _route, _upload

API = "/api/v1"


def _ago(minutes: int) -> str:
    return (utcnow() - timedelta(minutes=minutes)).isoformat()


def _day(shift: dict[str, Any]) -> str:
    return to_local_date(datetime.fromisoformat(shift["started_at"])).isoformat()


def _report(client: TestClient, h: dict[str, str], code: str, **params: Any) -> Any:
    res = client.get(f"{API}/reports/{code}", params=params, headers=h)
    assert res.status_code == 200, res.text
    return res.json()


def _start_shift(
    client: TestClient,
    staff: dict[str, str],
    driver_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    *,
    minutes_ago: int,
    operation_type: str,
    route_id: uuid.UUID | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    shift = client.post(
        f"{API}/shifts",
        headers=staff,
        json={
            "driver_id": str(driver_id),
            "vehicle_id": str(vehicle_id),
            "start_now": True,
            "start_odometer_km": 50_000,
            "started_at": _ago(minutes_ago),
        },
    )
    assert shift.status_code == 201, shift.text
    body: dict[str, Any] = {
        "operation_type_id": operation_type,
        "started_at": shift.json()["started_at"],
    }
    if route_id:
        body["route_id"] = str(route_id)
    session = client.post(f"{API}/shifts/{shift.json()['id']}/sessions", headers=staff, json=body)
    assert session.status_code == 201, session.text
    return shift.json(), session.json()


def test_scenario_a_fixed_route_microbus_day(client: TestClient, db: Session) -> None:
    driver, _, app, vehicle = make_driver_account(client, db)
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    university = _route(db, "FIXED_ROUTE", STATION, UNIVERSITY, "موقف ⇄ جامعة")
    school = _route(db, "SCHOOL_ROUTE", STATION, SCHOOL, "مدرسة النور — ظهرًا")

    # 1. Shift starts on the university route.
    shift, route_session = _start_shift(
        client,
        ops,
        driver.id,
        vehicle.id,
        minutes_ago=120,
        operation_type=str(university.operation_type_id),
        route_id=university.id,
    )

    # 2. GPS records three station ⇄ university loops (uploaded in two batches).
    segments: list[Any] = [("dwell", STATION, 60)]
    for _ in range(3):
        segments += [("drive", STATION, UNIVERSITY, 300), ("dwell", UNIVERSITY, 60)]
        segments += [("drive", UNIVERSITY, STATION, 300), ("dwell", STATION, 60)]
    pts = _points(utcnow() - timedelta(minutes=115), segments)
    _upload(client, app, shift["id"], pts[: len(pts) // 2])
    _upload(client, app, shift["id"], pts[len(pts) // 2 :])
    detail = client.get(f"{API}/shifts/{shift['id']}", headers=ops).json()
    assert next(s for s in detail["sessions"] if s["id"] == route_session["id"])["loops"] == 3

    # 3. CNG bought by the driver from the app (reviewed later); gasoline entered by the office.
    cng = client.post(
        f"{API}/driver/fuel",
        headers={**app, "Idempotency-Key": str(uuid.uuid4())},
        json={"fuel_type_id": fuel_type_id(db, "CNG"), "quantity": "25", "total_amount": "175"},
    )
    assert cng.status_code == 201, cng.text
    gasoline = client.post(
        f"{API}/fuel",
        headers=acc,
        json={
            "vehicle_id": str(vehicle.id),
            "driver_id": str(driver.id),
            "shift_id": shift["id"],
            "fuel_type_id": fuel_type_id(db, "GASOLINE"),
            "quantity": "20",
            "total_amount": "300",
            "occurred_at": _ago(70),
            "approve_now": True,
        },
    )
    assert gasoline.status_code == 201, gasoline.text
    assert (
        client.post(f"{API}/fuel/{cng.json()['id']}/approve", headers=acc, json={}).status_code
        == 200
    )

    # 4. The school duty starts later in the same shift.
    ended = client.post(
        f"{API}/operation-sessions/{route_session['id']}/end",
        headers=ops,
        json={"ended_at": _ago(65)},
    )
    assert ended.status_code == 200, ended.text
    school_session = client.post(
        f"{API}/shifts/{shift['id']}/sessions",
        headers=ops,
        json={
            "operation_type_id": str(school.operation_type_id),
            "route_id": str(school.id),
            "started_at": _ago(60),
        },
    )
    assert school_session.status_code == 201, school_session.text
    _upload(
        client,
        app,
        shift["id"],
        _points(
            utcnow() - timedelta(minutes=55),
            [("dwell", STATION, 60), ("drive", STATION, SCHOOL, 300), ("dwell", SCHOOL, 90)],
        ),
    )

    # 5. The driver ends the shift from the app with the odometer reading.
    end = client.post(
        f"{API}/driver/shifts/{shift['id']}/end",
        headers={**app, "Idempotency-Key": str(uuid.uuid4())},
        json={"end_odometer_km": 50_017},
    )
    assert end.status_code == 200, end.text
    assert end.json()["status"] == "COMPLETED"

    # 6. Odometer reconciled against GPS.
    day = _day(shift)
    recon = _report(
        client,
        ops,
        "gps_odometer",
        date_from=day,
        date_to=local_today().isoformat(),
        vehicle_id=str(vehicle.id),
    )
    [row] = recon["rows"]
    assert row["odometer_km"] == 17
    assert 15 < row["gps_km"] < 18  # 3 loops of ~5.1 km + ~1.3 km to the school

    # 7. The day's fare collection, held by the driver until handover.
    revenue = client.post(
        f"{API}/revenue",
        headers=acc,
        json={
            "kind": "FIXED_ROUTE_COLLECTION",
            "vehicle_id": str(vehicle.id),
            "driver_id": str(driver.id),
            "shift_id": shift["id"],
            "occurred_on": day,
            "amount": "900",
            "loops_count": 3,
            "approve_now": True,
            "receipt": {
                "amount": "900",
                "received_at": _ago(5),
                "method": "CASH",
                "received_by": "DRIVER",
            },
        },
    )
    assert revenue.status_code == 201, revenue.text

    # 8. The vehicle's result for the day comes straight from those records.
    pnl = _report(
        client,
        acc,
        "vehicle_profitability",
        date_from=day,
        date_to=local_today().isoformat(),
        vehicle_id=str(vehicle.id),
    )
    [v] = pnl["rows"]
    assert v["gross_revenue"] == "900.00"
    assert v["fuel_cost"] == "475.00"  # CNG 175 + gasoline 300, both approved
    assert v["odometer_km"] == 17
    assert v["net_operating_profit"] == "425.00"  # no compensation plan: driver cost is 0
    loops = _report(
        client,
        ops,
        "route_loops",
        date_from=day,
        date_to=local_today().isoformat(),
        vehicle_id=str(vehicle.id),
    )
    assert loops["totals"]["loops"] == 3

    # The driver holds the fares and paid for the CNG: owes the company 900 - 175.
    statement = _report(
        client,
        acc,
        "driver_statements",
        date_from=day,
        date_to=local_today().isoformat(),
        driver_id=str(driver.id),
    )
    [d] = statement["rows"]
    assert d["cash_collected"] == "-900.00"
    assert d["reimbursements"] == "175.00"
    assert d["closing"] == "-725.00"


def test_scenario_b_ride_hailing_day(client: TestClient, db: Session) -> None:
    driver, _, app, vehicle = make_driver_account(client, db)
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    platform = make_platform(db)

    shift, _session = _start_shift(
        client,
        ops,
        driver.id,
        vehicle.id,
        minutes_ago=180,
        operation_type=operation_type_id(db, "RIDE_HAILING"),
    )
    # Tracking is active: trips around the city.
    _upload(
        client,
        app,
        shift["id"],
        _points(
            utcnow() - timedelta(minutes=170),
            [
                ("drive", STATION, UNIVERSITY, 600),
                ("dwell", UNIVERSITY, 120),
                ("drive", UNIVERSITY, SCHOOL, 600),
                ("dwell", SCHOOL, 120),
            ],
        ),
    )
    fuel = client.post(
        f"{API}/driver/fuel",
        headers={**app, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "fuel_type_id": fuel_type_id(db, "GASOLINE"),
            "quantity": "15",
            "total_amount": "225",
        },
    )
    assert fuel.status_code == 201, fuel.text
    end = client.post(
        f"{API}/driver/shifts/{shift['id']}/end",
        headers={**app, "Idempotency-Key": str(uuid.uuid4())},
        json={"end_odometer_km": 50_060},
    )
    assert end.status_code == 200, end.text
    assert (
        client.post(f"{API}/fuel/{fuel.json()['id']}/approve", headers=acc, json={}).status_code
        == 200
    )

    # Platform earnings and fees entered from the platform's statement (no scraping).
    day = _day(shift)
    statement = client.post(
        f"{API}/ride-hailing/statements",
        headers=acc,
        json={
            "platform_id": str(platform.id),
            "driver_id": str(driver.id),
            "vehicle_id": str(vehicle.id),
            "period_start": day,
            "period_end": day,
            "trips_count": 11,
            "gross_earnings": "1200",
            "platform_fees": "300",
            "cash_collected": "400",
            "payout_recipient": "COMPANY",
            "approve_now": True,
        },
    )
    assert statement.status_code == 201, statement.text
    assert statement.json()["revenue_entry_id"]

    today = local_today().isoformat()
    rh = _report(
        client, acc, "ride_hailing", date_from=day, date_to=today, vehicle_id=str(vehicle.id)
    )
    [row] = rh["rows"]
    assert row["trips"] == 11
    assert row["minutes"] > 0  # recorded ride-hailing time matched to the statement
    assert row["odometer_km"] == 60
    assert row["net"] == "900.00"

    pnl = _report(
        client,
        acc,
        "vehicle_profitability",
        date_from=day,
        date_to=today,
        vehicle_id=str(vehicle.id),
    )
    [v] = pnl["rows"]
    assert v["platform_fees"] == "300.00"
    assert v["fuel_cost"] == "225.00"
    driver_row = _report(
        client, acc, "driver_statements", date_from=day, date_to=today, driver_id=str(driver.id)
    )["rows"][0]
    # Cash fares the driver kept, gasoline the driver paid for.
    assert driver_row["cash_collected"] == "-400.00"
    assert driver_row["reimbursements"] == "225.00"


def test_scenario_c_gps_interruption_is_reviewed(client: TestClient, db: Session) -> None:
    driver, _, app, vehicle = make_driver_account(client, db)
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    route = _route(db, "FIXED_ROUTE", STATION, UNIVERSITY, "موقف ⇄ جامعة")
    shift, _session = _start_shift(
        client,
        ops,
        driver.id,
        vehicle.id,
        minutes_ago=90,
        operation_type=str(route.operation_type_id),
        route_id=route.id,
    )
    # Tracking works, then location is switched off for 35 minutes, then resumes.
    _upload(
        client,
        app,
        shift["id"],
        _points(utcnow() - timedelta(minutes=88), [("drive", STATION, UNIVERSITY, 900)]),
    )
    events = [
        {
            "client_event_id": str(uuid.uuid4()),
            "event_type": "LOCATION_DISABLED",
            "occurred_at": _ago(72),
            "shift_id": shift["id"],
        },
        {
            "client_event_id": str(uuid.uuid4()),
            "event_type": "LOCATION_ENABLED",
            "occurred_at": _ago(37),
            "shift_id": shift["id"],
        },
    ]
    assert (
        client.post(
            f"{API}/driver/tracking/events", headers=app, json={"events": events}
        ).status_code
        == 200
    )
    _upload(
        client,
        app,
        shift["id"],
        _points(utcnow() - timedelta(minutes=36), [("drive", SCHOOL, STATION, 900)]),
    )
    end = client.post(
        f"{API}/driver/shifts/{shift['id']}/end",
        headers={**app, "Idempotency-Key": str(uuid.uuid4())},
        json={"end_odometer_km": 50_025},
    )
    assert end.status_code == 200, end.text

    # The detection run raises review cases linked to the shift.
    run = client.post(f"{API}/exceptions/run", headers=ops, json={"days": 1})
    assert run.status_code == 200, run.text
    cases = client.get(f"{API}/exceptions", headers=ops, params={"shift_id": shift["id"]}).json()[
        "items"
    ]
    by_rule = {c["rule_code"]: c for c in cases}
    disabled = by_rule["GPS_DISABLED"]
    assert disabled["label"] == "REVIEW_REQUIRED"  # shown as «مراجعة مطلوبة»
    assert disabled["evidence"]["minutes"] == 35
    assert disabled["driver"]["id"] == str(driver.id)
    gap = by_rule["GPS_GAP"]
    assert gap["evidence"]["gaps"][0]["moved_m"] > 1000  # the vehicle moved while no data came in
    assert "LOCATION_DISABLED" in gap["evidence"]["gaps"][0]["device_events"]

    # Management is told, then a manager reviews the evidence and records the outcome.
    _, admin = login_as(client, db, UserRole.ADMIN)
    client.post(f"{API}/notifications/generate", headers=admin)
    inbox = client.get(f"{API}/notifications", headers=ops).json()["items"]
    assert any(n["link"] == f"/exceptions/{disabled['id']}" for n in inbox)

    url = f"{API}/exceptions/{disabled['id']}/review"
    assert client.post(url, headers=ops, json={"status": "UNDER_REVIEW"}).status_code == 200
    closed = client.post(
        url,
        headers=ops,
        json={
            "status": "EXPLAINED",
            "notes": "راجعت المسار مع السائق",
            "resolution": "الهاتف أوقف الموقع بسبب توفير البطارية؛ تم ضبط الإعداد",
        },
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "EXPLAINED"
    reviews = db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.entity_id == disabled["id"],
            AuditLog.action == "operational_exception.reviewed",
        )
    )
    assert reviews == 2


def test_scenario_d_financial_correction_keeps_history(client: TestClient, db: Session) -> None:
    driver, _, _app, vehicle = make_driver_account(client, db)
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    when = utcnow() - timedelta(minutes=30)
    # Dates come from the record itself, so the test also passes around midnight.
    day = to_local_date(when).isoformat()
    today = local_today().isoformat()

    # An expense entered as 150 instead of 15, and approved.
    wrong = client.post(
        f"{API}/expenses",
        headers=acc,
        json={
            "vehicle_id": str(vehicle.id),
            "driver_id": str(driver.id),
            "category_id": expense_category_id(db, "TOLL"),
            "amount": "150",
            "occurred_at": when.isoformat(),
            "approve_now": True,
        },
    ).json()
    fixed = client.post(
        f"{API}/expenses/{wrong['id']}/correct",
        headers=acc,
        json={
            "vehicle_id": str(vehicle.id),
            "driver_id": str(driver.id),
            "category_id": expense_category_id(db, "TOLL"),
            "amount": "15",
            "occurred_at": when.isoformat(),
            "approve_now": True,
            "reason": "خطأ في إدخال المبلغ (صفر زائد)",
        },
    )
    assert fixed.status_code == 201, fixed.text
    assert fixed.json()["corrects_id"] == wrong["id"]

    # Revenue entered as 800 instead of 850, corrected the same way.
    rev = client.post(
        f"{API}/revenue",
        headers=acc,
        json={
            "kind": "PRIVATE_TRIP",
            "vehicle_id": str(vehicle.id),
            "occurred_on": day,
            "amount": "800",
            "approve_now": True,
        },
    ).json()
    rev_fixed = client.post(
        f"{API}/revenue/{rev['id']}/correct",
        headers=acc,
        json={
            "kind": "PRIVATE_TRIP",
            "vehicle_id": str(vehicle.id),
            "occurred_on": day,
            "amount": "850",
            "approve_now": True,
            "reason": "المبلغ المتفق عليه 850",
        },
    )
    assert rev_fixed.status_code == 201, rev_fixed.text

    # The originals remain, voided and linked to their replacements.
    original = client.get(f"{API}/expenses/{wrong['id']}", headers=acc).json()
    assert original["status"] == "VOIDED"
    assert original["corrected_by_id"] == fixed.json()["id"]
    assert client.get(f"{API}/revenue/{rev['id']}", headers=acc).json()["status"] == "VOIDED"
    trail = set(
        db.scalars(
            select(AuditLog.action).where(
                AuditLog.entity_id.in_(
                    [wrong["id"], fixed.json()["id"], rev["id"], rev_fixed.json()["id"]]
                )
            )
        ).all()
    )
    assert {"expense.corrected", "revenue_entry.corrected"} <= trail

    # Reports reflect the corrected amounts only.
    expenses = _report(
        client, acc, "expenses", date_from=day, date_to=today, vehicle_id=str(vehicle.id)
    )
    assert expenses["totals"]["amount"] == "15.00"
    pnl = _report(
        client,
        acc,
        "vehicle_profitability",
        date_from=day,
        date_to=today,
        vehicle_id=str(vehicle.id),
    )
    [v] = pnl["rows"]
    assert v["gross_revenue"] == "850.00"
    assert v["other_expenses"] == "15.00"
    assert v["net_operating_profit"] == "835.00"
