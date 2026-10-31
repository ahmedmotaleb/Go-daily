"""Driver account ledger, settlements and vehicle P&L (Tasks 18-19)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from app.models.driver import CompensationMethod
from tests.factories import (
    expense_category_id,
    fuel_type_id,
    login_as,
    make_completed_shift,
    make_driver,
    make_plan,
    make_vehicle,
)

D = Decimal


def _day(days_ago: int) -> date:
    return local_today() - timedelta(days=days_ago)


def _settle(client: TestClient, h: dict[str, str], driver_id: str, start: date, end: date) -> Any:
    res = client.post(
        "/api/v1/settlements",
        json={
            "driver_id": driver_id,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
        },
        headers=h,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _revenue(
    client: TestClient,
    h: dict[str, str],
    vehicle_id: str,
    driver_id: str | None,
    amount: str,
    day: date,
    **extra: object,
) -> Any:
    res = client.post(
        "/api/v1/revenue",
        json={
            "kind": extra.pop("kind", "FIXED_ROUTE_COLLECTION"),
            "vehicle_id": vehicle_id,
            "driver_id": driver_id,
            "occurred_on": day.isoformat(),
            "amount": amount,
            "approve_now": extra.pop("approve_now", True),
            **extra,
        },
        headers=h,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_daily_wage_counts_distinct_worked_days_and_finalize_posts_earning(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver = make_vehicle(db), make_driver(db)
    make_plan(
        db,
        driver,
        CompensationMethod.DAILY_WAGE,
        effective_from=_day(60),
        daily_wage_amount=D("250"),
    )
    for days_ago in (10, 9, 8):
        make_completed_shift(db, driver, vehicle, day=_day(days_ago), minutes=240)
    make_completed_shift(db, driver, vehicle, day=_day(8), minutes=60)  # same day: counted once

    advance = client.post(
        f"/api/v1/drivers/{driver.id}/ledger",
        json={
            "entry_type": "ADVANCE",
            "amount": "300",
            "occurred_on": _day(20).isoformat(),
            "description": "سلفة",
        },
        headers=h,
    )
    assert advance.status_code == 201
    draft = _settle(client, h, str(driver.id), _day(14), _day(1))
    assert draft["status"] == "DRAFT"
    assert draft["earnings_amount"] == "750.00"
    assert draft["details"]["days_worked"] == 3
    assert draft["details"]["lines"][0]["basis"].startswith("3 يوم عمل")

    final = client.post(f"/api/v1/settlements/{draft['id']}/finalize", headers=h).json()
    assert final["status"] == "FINALIZED"
    assert final["opening_balance"] == "-300.00"
    assert final["closing_balance"] == "450.00"
    statement = client.get(
        f"/api/v1/drivers/{driver.id}/statement",
        params={"date_from": _day(14).isoformat()},
        headers=h,
    ).json()
    assert statement["opening_balance"] == "-300.00"
    assert statement["earned"] == "750.00"
    assert statement["closing_balance"] == "450.00"

    payment = client.post(
        f"/api/v1/drivers/{driver.id}/ledger",
        json={
            "entry_type": "PAYMENT",
            "amount": "450",
            "occurred_on": _day(0).isoformat(),
            "description": "صرف المستحقات",
        },
        headers=h,
    )
    assert payment.status_code == 201
    statement = client.get(
        f"/api/v1/drivers/{driver.id}/statement",
        params={"date_from": _day(30).isoformat()},
        headers=h,
    ).json()
    assert statement["closing_balance"] == "0.00"
    assert statement["paid"] == "-450.00"


def test_revenue_percentage_uses_approved_net_revenue(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver = make_vehicle(db), make_driver(db)
    make_plan(
        db,
        driver,
        CompensationMethod.REVENUE_PERCENTAGE,
        effective_from=_day(60),
        revenue_percentage=D("25"),
    )
    _revenue(client, h, str(vehicle.id), str(driver.id), "1000", _day(5))
    _revenue(client, h, str(vehicle.id), str(driver.id), "600", _day(4))
    _revenue(client, h, str(vehicle.id), str(driver.id), "999", _day(3), approve_now=False)
    draft = _settle(client, h, str(driver.id), _day(10), _day(1))
    assert draft["earnings_amount"] == "400.00"
    assert any("بانتظار الاعتماد" in w for w in draft["details"]["warnings"])


def test_fixed_monthly_is_prorated_and_plan_changes_split_the_period(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver = make_driver(db)
    # A full past month, so the expected proration is exact.
    first_of_this_month = local_today().replace(day=1)
    month_end = first_of_this_month - timedelta(days=1)
    month_start = month_end.replace(day=1)
    days = (month_end - month_start).days + 1
    mid = month_start + timedelta(days=9)  # plan changes after day 10
    make_plan(
        db,
        driver,
        CompensationMethod.FIXED_MONTHLY,
        effective_from=month_start - timedelta(days=60),
        effective_to=mid,
        fixed_monthly_amount=D("3000"),
    )
    make_plan(
        db,
        driver,
        CompensationMethod.FIXED_MONTHLY,
        effective_from=mid + timedelta(days=1),
        effective_to=local_today(),
        fixed_monthly_amount=D("4500"),
    )
    draft = _settle(client, h, str(driver.id), month_start, month_end)
    lines = draft["details"]["lines"]
    assert len(lines) == 2
    expected = D("3000") * 10 / days + D("4500") * (days - 10) / days
    assert D(draft["earnings_amount"]) == expected.quantize(D("0.01"))
    final = client.post(f"/api/v1/settlements/{draft['id']}/finalize", headers=h).json()

    # A later plan change never rewrites the finalised settlement.
    make_plan(
        db,
        driver,
        CompensationMethod.DAILY_WAGE,
        effective_from=local_today() + timedelta(days=30),
        daily_wage_amount=D("1"),
    )
    again = client.get(f"/api/v1/settlements/{final['id']}", headers=h).json()
    assert again["earnings_amount"] == final["earnings_amount"]
    assert again["details"] == final["details"]
    recalc = client.post(f"/api/v1/settlements/{final['id']}/recalculate", headers=h)
    assert recalc.status_code == 409


def test_finalized_settlements_cannot_overlap_until_voided(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver = make_driver(db)
    make_plan(
        db,
        driver,
        CompensationMethod.DAILY_WAGE,
        effective_from=_day(90),
        daily_wage_amount=D("200"),
    )
    make_completed_shift(db, driver, make_vehicle(db), day=_day(5))
    first = _settle(client, h, str(driver.id), _day(10), _day(1))
    second = _settle(client, h, str(driver.id), _day(5), _day(0))  # drafts may overlap
    client.post(f"/api/v1/settlements/{first['id']}/finalize", headers=h)
    blocked = client.post(f"/api/v1/settlements/{second['id']}/finalize", headers=h)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "overlapping_settlement"
    new = client.post(
        "/api/v1/settlements",
        json={
            "driver_id": str(driver.id),
            "period_start": _day(3).isoformat(),
            "period_end": _day(0).isoformat(),
        },
        headers=h,
    )
    assert new.status_code == 422

    voided = client.post(
        f"/api/v1/settlements/{first['id']}/void", json={"reason": "خطأ في الفترة"}, headers=h
    ).json()
    assert voided["status"] == "VOIDED"
    statement = client.get(
        f"/api/v1/drivers/{driver.id}/statement",
        params={"date_from": _day(30).isoformat()},
        headers=h,
    ).json()
    assert statement["earned"] == "0.00"
    ok = client.post(f"/api/v1/settlements/{second['id']}/finalize", headers=h)
    assert ok.status_code == 200, ok.text


def test_manual_ledger_rules(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver = make_driver(db)
    url = f"/api/v1/drivers/{driver.id}/ledger"
    base = {"amount": "100", "occurred_on": _day(1).isoformat(), "description": "قيد"}
    assert client.post(url, json=base | {"entry_type": "EARNING"}, headers=h).status_code == 422
    assert client.post(url, json=base | {"entry_type": "ADJUSTMENT"}, headers=h).status_code == 422
    assert client.post(url, json=base | {"entry_type": "DEDUCTION"}, headers=h).status_code == 422
    adj = client.post(
        url,
        json=base | {"entry_type": "ADJUSTMENT", "direction": "DEBIT", "reason": "تسوية فرق عهدة"},
        headers=h,
    ).json()
    assert adj["amount"] == "-100.00"
    void = client.post(
        f"/api/v1/driver-ledger/{adj['id']}/void", json={"reason": "قيد خاطئ"}, headers=h
    )
    assert void.status_code == 200
    assert void.json()["voided_at"] is not None
    again = client.post(
        f"/api/v1/driver-ledger/{adj['id']}/void", json={"reason": "قيد خاطئ"}, headers=h
    )
    assert again.status_code == 409


def test_operations_cannot_read_driver_accounts(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    driver = make_driver(db)
    res = client.get(
        f"/api/v1/drivers/{driver.id}/statement",
        params={"date_from": _day(10).isoformat()},
        headers=h,
    )
    assert res.status_code == 403
    assert (
        client.get(
            "/api/v1/profitability/vehicles",
            params={"date_from": _day(10).isoformat(), "date_to": _day(0).isoformat()},
            headers=h,
        ).status_code
        == 403
    )


# --- Vehicle P&L ---------------------------------------------------------------------


def _cost(client: TestClient, h: dict[str, str], path: str, **body: object) -> None:
    res = client.post(
        path,
        json={
            "occurred_at": (utcnow() - timedelta(days=2)).isoformat(),
            "approve_now": True,
            **body,
        },
        headers=h,
    )
    assert res.status_code == 201, res.text


def _pnl(client: TestClient, h: dict[str, str], vehicle_id: str, start: date, end: date) -> Any:
    res = client.get(
        "/api/v1/profitability/vehicles",
        params={
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "vehicle_id": vehicle_id,
        },
        headers=h,
    )
    assert res.status_code == 200, res.text
    return res.json()["vehicles"][0]


def test_vehicle_pnl_from_approved_records(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver = make_vehicle(db), make_driver(db)
    v = str(vehicle.id)
    make_plan(
        db,
        driver,
        CompensationMethod.DAILY_WAGE,
        effective_from=_day(60),
        daily_wage_amount=D("300"),
    )
    make_completed_shift(
        db,
        driver,
        vehicle,
        day=_day(2),
        start_odometer_km=10_000,
        end_odometer_km=10_200,
    )
    _revenue(client, h, v, str(driver.id), "1500", _day(2))
    _cost(
        client,
        h,
        "/api/v1/fuel",
        vehicle_id=v,
        fuel_type_id=fuel_type_id(db, "CNG"),
        quantity="30",
        total_amount="210",
    )
    _cost(
        client,
        h,
        "/api/v1/fuel",
        vehicle_id=v,
        fuel_type_id=fuel_type_id(db, "GASOLINE"),
        quantity="5",
        total_amount="80",
    )
    _cost(
        client,
        h,
        "/api/v1/fuel",
        vehicle_id=v,
        fuel_type_id=fuel_type_id(db, "ENGINE_OIL"),
        quantity="4",
        total_amount="60",
    )
    _cost(
        client,
        h,
        "/api/v1/expenses",
        vehicle_id=v,
        category_id=expense_category_id(db, "TOLL"),
        amount="20",
    )
    _cost(
        client,
        h,
        "/api/v1/expenses",
        vehicle_id=v,
        category_id=expense_category_id(db, "REPAIR"),
        amount="130",
    )
    settlement = _settle(client, h, str(driver.id), _day(6), _day(0))
    client.post(f"/api/v1/settlements/{settlement['id']}/finalize", headers=h)

    pnl = _pnl(client, h, v, _day(6), _day(0))
    assert pnl["gross_revenue"] == "1500.00"
    assert pnl["fuel_by_type"] == {"CNG": "210.00", "GASOLINE": "80.00", "ENGINE_OIL": "60.00"}
    assert pnl["fuel_cost"] == "290.00"
    assert pnl["consumables_cost"] == "60.00"  # oil is not fuel
    assert pnl["maintenance_cost"] == "130.00"
    assert pnl["other_expenses"] == "20.00"
    assert pnl["direct_operating_cost"] == "500.00"
    assert pnl["driver_cost"] == "300.00"
    assert pnl["net_operating_profit"] == "700.00"
    assert pnl["shifts_count"] == 1
    assert pnl["odometer_km"] == 200
    assert pnl["cost_per_km"] == "4.00"
    assert pnl["revenue_per_km"] == "7.50"
    assert pnl["profit_per_shift"] == "700.00"
    codes = {w["code"] for w in pnl["warnings"]}
    assert not codes & {"NO_FUEL_RECORDS", "DAYS_WITHOUT_REVENUE", "DRIVER_COST_INCOMPLETE"}
    # Revenue not linked to a session stays "untyped"; costs follow session minutes.
    rows = {bool(r["operation_type"]): r for r in pnl["by_operation_type"]}
    assert rows[False]["revenue"] == "1500.00"
    assert rows[False]["allocated_cost"] == "0.00"
    assert rows[True]["allocated_cost"] == "800.00"
    assert rows[True]["session_minutes"] == 480


def test_pnl_warns_about_missing_inputs_instead_of_guessing(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver = make_vehicle(db), make_driver(db)
    v = str(vehicle.id)
    make_completed_shift(db, driver, vehicle, day=_day(3))
    make_completed_shift(db, driver, vehicle, day=_day(2))
    _revenue(client, h, v, str(driver.id), "500", _day(3))
    _cost(
        client,
        h,
        "/api/v1/expenses",
        vehicle_id=v,
        category_id=expense_category_id(db, "PARKING"),
        amount="10",
        approve_now=False,
    )

    pnl = _pnl(client, h, v, _day(6), _day(0))
    warnings = {w["code"]: w for w in pnl["warnings"]}
    assert warnings["NO_FUEL_RECORDS"]
    assert warnings["DAYS_WITHOUT_REVENUE"]["count"] == 1
    assert warnings["DRIVER_COST_INCOMPLETE"]["count"] == 1
    assert warnings["PENDING_RECORDS"]["count"] == 1
    assert pnl["fuel_cost"] == "0.00"  # nothing estimated
    assert pnl["driver_cost"] == "0.00"
    assert pnl["other_expenses"] == "0.00"  # the pending expense is excluded


def test_contract_revenue_is_spread_over_its_period(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    _revenue(
        client,
        h,
        str(vehicle.id),
        None,
        "3000",
        _day(1),
        kind="CONTRACT_SERVICE",
        customer_name="مدرسة",
        period_start=_day(30).isoformat(),
        period_end=_day(1).isoformat(),
    )
    pnl = _pnl(client, h, str(vehicle.id), _day(10), _day(1))
    assert pnl["gross_revenue"] == "1000.00"  # 10 of 30 days


def test_pnl_range_is_validated(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    res = client.get(
        "/api/v1/profitability/vehicles",
        params={"date_from": _day(0).isoformat(), "date_to": _day(5).isoformat()},
        headers=h,
    )
    assert res.status_code == 422
