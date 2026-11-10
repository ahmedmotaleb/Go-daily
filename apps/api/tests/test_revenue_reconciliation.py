"""Revenue reconciliation (U18): every source per vehicle, no double counting, warnings."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today
from app.services import revenue_reconciliation as rr
from tests.factories import login_as, make_driver, make_platform, make_vehicle
from tests.test_finance_revenue import _stmt_body

D = Decimal
TODAY = local_today()


def _day(days_ago: int) -> date:
    return TODAY - timedelta(days=days_ago)


def _revenue(client: TestClient, h: dict[str, str], vehicle_id: str, **over: Any) -> Any:
    body: dict[str, Any] = {
        "kind": "PRIVATE_TRIP",
        "vehicle_id": vehicle_id,
        "occurred_on": _day(2).isoformat(),
        "amount": "400",
        "approve_now": True,
    }
    body.update(over)
    res = client.post("/api/v1/revenue", json=body, headers=h)
    assert res.status_code == 201, res.text
    return res.json()


def _row(result: rr.Reconciliation, vehicle_id: Any) -> rr.VehicleRevenue:
    return next(v for v in result.vehicles if v.vehicle_id == vehicle_id)


def test_sources_are_combined_without_double_counting(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver, platform = make_vehicle(db), make_driver(db), make_platform(db)
    st = client.post(
        "/api/v1/ride-hailing/statements",
        json=_stmt_body(str(platform.id), str(driver.id), str(vehicle.id)),
        headers=h,
    ).json()
    client.post(f"/api/v1/ride-hailing/statements/{st['id']}/approve", json={}, headers=h)
    _revenue(client, h, str(vehicle.id))
    # A 30-day school contract: a 7-day range takes 7/30 of it.
    _revenue(
        client,
        h,
        str(vehicle.id),
        kind="CONTRACT_SERVICE",
        amount="3000",
        occurred_on=_day(20).isoformat(),
        period_start=_day(29).isoformat(),
        period_end=_day(0).isoformat(),
    )
    _revenue(client, h, str(vehicle.id), amount="150", approve_now=False)

    result = rr.reconcile(db, _day(6), _day(0), vehicle_id=vehicle.id)
    row = _row(result, vehicle.id)
    # Statement 7 days long (days 7..1); the range covers days 6..1 = 6/7 of it.
    share = D(6) / D(7)
    assert row.ride_income == (D("3050") * share).quantize(D("0.01"))
    assert row.ride_commission == (D("750") * share).quantize(D("0.01"))
    assert row.ride_cash == (D("1200") * share).quantize(D("0.01"))
    assert row.contracts == D("700.00")
    assert row.private_trips == D("400.00")
    assert row.pending_review == D("150.00")
    # The generated ride-hailing revenue entry is not counted a second time.
    assert row.recognized == (row.ride_net + D("1100")).quantize(D("0.01"))
    assert {w.code for w in row.warnings} == {"PENDING_REVIEW"}


def test_completeness_warnings(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    _revenue(client, h, str(vehicle.id), amount="250")
    _revenue(client, h, str(vehicle.id), amount="250")
    row = _row(rr.reconcile(db, _day(6), _day(0), vehicle_id=vehicle.id), vehicle.id)
    codes = {w.code: w.count for w in row.warnings}
    assert codes["POSSIBLE_DUPLICATE"] == 2


def test_report_and_permissions(client: TestClient, db: Session) -> None:
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    _revenue(client, acc, str(vehicle.id))
    params = {"date_from": _day(6).isoformat(), "date_to": _day(0).isoformat()}
    res = client.get("/api/v1/reports/revenue_reconciliation", params=params, headers=acc)
    assert res.status_code == 200, res.text
    rows = [r for r in res.json()["rows"] if r["vehicle"] == vehicle.internal_code]
    assert D(rows[0]["private_trips"]) == D("400")
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    denied = client.get("/api/v1/reports/revenue_reconciliation", params=params, headers=ops)
    assert denied.status_code == 403
