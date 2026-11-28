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

    client.post(f"/api/v1/settlements/{draft['id']}/review", headers=h)
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

    # Payments go through the settlement (never a manual ledger entry).
    payment = client.post(
        f"/api/v1/settlements/{draft['id']}/pay",
        json={"amount": "450", "paid_on": _day(0).isoformat(), "method": "CASH"},
        headers=h,
    )
    assert payment.status_code == 200, payment.text
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
    client.post(f"/api/v1/settlements/{draft['id']}/review", headers=h)
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
    # The API refuses overlapping open drafts (runtime audit L7); one made before
    # that rule (or concurrently) must still be stopped at approval.
    from app.models.finance import DriverSettlement, SettlementStatus

    legacy = DriverSettlement(
        driver_id=driver.id,
        period_start=_day(5),
        period_end=_day(0),
        status=SettlementStatus.DRAFT,
        earnings_amount=D("0"),
        details={},
    )
    db.add(legacy)
    db.commit()
    second = {"id": str(legacy.id)}
    client.post(f"/api/v1/settlements/{first['id']}/review", headers=h)
    client.post(f"/api/v1/settlements/{first['id']}/finalize", headers=h)
    client.post(f"/api/v1/settlements/{second['id']}/review", headers=h)
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
    client.post(f"/api/v1/settlements/{second['id']}/review", headers=h)
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
    client.post(f"/api/v1/settlements/{settlement['id']}/review", headers=h)
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


# --- Security audit (security H2, runtime M3): manual ledger entries -------------------


def test_manual_ledger_refuses_types_that_have_their_own_flow(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver = make_driver(db)
    for entry_type in ("PAYMENT", "CASH_HANDOVER", "REIMBURSEMENT", "CASH_COLLECTED", "EARNING"):
        res = client.post(
            f"/api/v1/drivers/{driver.id}/ledger",
            json={
                "entry_type": entry_type,
                "amount": "100",
                "occurred_on": _day(0).isoformat(),
                "description": "قيد يدوي",
            },
            headers=h,
        )
        assert res.status_code == 422, (entry_type, res.text)
        assert res.json()["error"]["code"] == "ledger_type_not_manual", entry_type


def test_large_manual_ledger_entries_need_reauth(client: TestClient, db: Session) -> None:
    from tests.factories import DEFAULT_PASSWORD
    from tests.test_reauth import _age

    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver = make_driver(db)
    url = f"/api/v1/drivers/{driver.id}/ledger"
    base = {"occurred_on": _day(0).isoformat(), "description": "قيد يدوي"}
    _age(db, h)
    small = client.post(url, json={**base, "entry_type": "BONUS", "amount": "9999.99"}, headers=h)
    assert small.status_code == 201, small.text
    for body in (
        {"entry_type": "BONUS", "amount": "10000"},
        {"entry_type": "ADVANCE", "amount": "25000"},
        {"entry_type": "ADJUSTMENT", "direction": "CREDIT", "amount": "9999999", "reason": "خطأ"},
    ):
        res = client.post(url, json={**base, **body}, headers=h)
        assert res.status_code == 403, (body, res.text)
        assert res.json()["error"]["code"] == "reauth_required"
    confirm = client.post("/api/v1/auth/reauth", headers=h, json={"password": DEFAULT_PASSWORD})
    assert confirm.status_code == 200
    big = client.post(url, json={**base, "entry_type": "BONUS", "amount": "10000"}, headers=h)
    assert big.status_code == 201, big.text
    _age(db, h)
    void = client.post(
        f"/api/v1/driver-ledger/{big.json()['id']}/void", json={"reason": "خطأ"}, headers=h
    )
    assert void.status_code == 403
    assert void.json()["error"]["code"] == "reauth_required"


# --- Security audit L1: a new plan never rewrites settled or closed history ------------


def test_backdated_plan_cannot_reach_into_settled_or_closed_history(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver, vehicle = make_driver(db), make_vehicle(db)
    make_plan(
        db, driver, CompensationMethod.DAILY_WAGE, effective_from=_day(60), daily_wage_amount="300"
    )
    make_completed_shift(db, driver, vehicle, day=_day(10))
    sid = _settle(client, h, str(driver.id), _day(14), _day(7))["id"]
    client.post(f"/api/v1/settlements/{sid}/review", headers=h)
    assert client.post(f"/api/v1/settlements/{sid}/finalize", headers=h).status_code == 200
    url = f"/api/v1/drivers/{driver.id}/compensation-plans"
    plan = {"method": "DAILY_WAGE", "daily_wage_amount": "350"}
    into_settled = client.post(url, headers=h, json={**plan, "effective_from": _day(9).isoformat()})
    assert into_settled.status_code == 409, into_settled.text
    assert into_settled.json()["error"]["code"] == "plan_in_settled_period"
    after = client.post(url, headers=h, json={**plan, "effective_from": _day(5).isoformat()})
    assert after.status_code == 201, after.text

    # A closed plan with a set end date is not shortened by a later backdated one.
    other = make_driver(db)
    make_plan(
        db,
        other,
        CompensationMethod.DAILY_WAGE,
        effective_from=_day(60),
        effective_to=_day(10),
        daily_wage_amount="300",
    )
    cut = client.post(
        f"/api/v1/drivers/{other.id}/compensation-plans",
        headers=h,
        json={**plan, "effective_from": _day(20).isoformat()},
    )
    assert cut.status_code == 409
    assert cut.json()["error"]["code"] == "plan_effective_date_conflict"


# --- Security audit L2: what counts as a paid day (two opt-in settings) -----------------


def test_daily_wage_day_rules_are_opt_in(client: TestClient, db: Session, monkeypatch: Any) -> None:
    from app.core.config import get_settings
    from app.models.cash import ShiftCloseout

    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver, vehicle = make_driver(db), make_vehicle(db)
    make_plan(
        db, driver, CompensationMethod.DAILY_WAGE, effective_from=_day(60), daily_wage_amount="300"
    )
    make_completed_shift(db, driver, vehicle, day=_day(10), minutes=480)
    short = make_completed_shift(db, driver, vehicle, day=_day(9), minutes=20)
    unclosed = make_completed_shift(db, driver, vehicle, day=_day(8), minutes=480)
    assert unclosed and short
    # Days 10 and 9 have a close-out; day 8 has none.
    from app.models.finance import RecordSource

    for shift in db.query(type(short)).filter(type(short).driver_id == driver.id):
        if shift.id != unclosed.id:
            db.add(
                ShiftCloseout(
                    shift_id=shift.id,
                    driver_id=driver.id,
                    vehicle_id=vehicle.id,
                    service_date=_day(10) if shift.id != short.id else _day(9),
                    submitted_at=shift.ended_at,
                    source=RecordSource.ADMIN,
                    end_odometer_km=1_100,
                    collection_amount=0,
                )
            )
    db.commit()

    def earnings() -> str:
        draft = _settle(client, h, str(driver.id), _day(14), _day(1))
        client.post(f"/api/v1/settlements/{draft['id']}/void", headers=h, json={"reason": "تجربة"})
        return str(draft["earnings_amount"])

    assert earnings() == "900.00"  # default: every completed shift is a day
    monkeypatch.setattr(get_settings(), "daily_wage_min_shift_minutes", 60)
    assert earnings() == "600.00"  # the 20-minute shift is not a paid day
    monkeypatch.setattr(get_settings(), "daily_wage_require_closeout", True)
    draft = _settle(client, h, str(driver.id), _day(14), _day(1))
    assert draft["earnings_amount"] == "300.00"  # only day 10 is long and closed out
    assert any("لم تُحتسب" in w for w in draft["details"]["warnings"])
