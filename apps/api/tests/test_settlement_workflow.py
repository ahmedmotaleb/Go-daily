"""Driver settlement workflow (U20): draft → reviewed → approved → paid."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.audit import AuditLog
from app.models.driver import CompensationMethod
from tests.factories import (
    DEFAULT_PASSWORD,
    login_as,
    make_completed_shift,
    make_driver,
    make_plan,
    make_vehicle,
)
from tests.test_finance_settlements import _day, _settle

S = "/api/v1/settlements"


def _post(client: TestClient, h: dict[str, str], path: str, **body: object) -> object:
    return client.post(f"{S}/{path}", headers=h, json=body or None)


def test_draft_review_approve_pay_and_void(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver, vehicle = make_driver(db), make_vehicle(db)
    make_plan(
        db, driver, CompensationMethod.DAILY_WAGE, effective_from=_day(60), daily_wage_amount="300"
    )
    for days in (10, 9):
        make_completed_shift(db, driver, vehicle, day=_day(days))
    advance = client.post(
        f"/api/v1/drivers/{driver.id}/ledger",
        headers=h,
        json={
            "entry_type": "ADVANCE",
            "amount": "200",
            "occurred_on": _day(8).isoformat(),
            "description": "سلفة",
        },
    )
    assert advance.status_code == 201, advance.text
    draft = _settle(client, h, str(driver.id), _day(14), _day(1))
    sid = draft["id"]
    assert draft["earnings_amount"] == "600.00"
    # The period's account entries are shown, not counted again.
    assert draft["details"]["account"]["by_type"] == {"ADVANCE": "-200.00"}

    # A manual adjustment needs a reason and is audited; never below zero.
    res = client.post(
        f"{S}/{sid}/adjust", headers=h, json={"amount": "150", "reason": "حافز التزام"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["earnings_amount"] == "750.00"
    assert res.json()["details"]["adjustments"][0]["reason"] == "حافز التزام"
    too_much = client.post(f"{S}/{sid}/adjust", headers=h, json={"amount": "-900", "reason": "خطأ"})
    assert too_much.status_code == 422

    # Approval needs a review first; the review freezes the inputs.
    assert client.post(f"{S}/{sid}/finalize", headers=h).status_code == 409
    reviewed = client.post(f"{S}/{sid}/review", headers=h).json()
    assert reviewed["status"] == "REVIEWED" and reviewed["reviewed_by"]
    assert reviewed["earnings_amount"] == "750.00"  # the adjustment survives
    frozen = client.post(f"{S}/{sid}/adjust", headers=h, json={"amount": "10", "reason": "متأخر"})
    assert frozen.status_code == 409
    assert client.post(f"{S}/{sid}/recalculate", headers=h).status_code == 409

    # A shift recorded after the review: approval refuses instead of changing figures.
    make_completed_shift(db, driver, vehicle, day=_day(5))
    changed = client.post(f"{S}/{sid}/finalize", headers=h)
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "inputs_changed"
    back = client.post(f"{S}/{sid}/reopen", headers=h, json={"reason": "وردية مسجلة متأخرة"})
    assert back.json()["status"] == "DRAFT"
    assert client.post(f"{S}/{sid}/review", headers=h).json()["earnings_amount"] == "1050.00"
    approved = client.post(f"{S}/{sid}/finalize", headers=h)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "FINALIZED"

    # Paying is recording a payment made elsewhere; it posts PAYMENT to the account.
    assert (
        client.post(
            f"{S}/{sid}/pay",
            headers=h,
            json={"amount": "850", "paid_on": "1999-01-01", "method": "CASH"},
        ).status_code
        == 422
    )
    paid = client.post(
        f"{S}/{sid}/pay",
        headers=h,
        json={
            "amount": "1050",
            "paid_on": _day(0).isoformat(),
            "method": "WALLET",
            "reference": "VF-1",
        },
    )
    assert paid.status_code == 200, paid.text
    body = paid.json()
    assert body["status"] == "PAID" and body["paid_amount"] == "1050.00"
    assert body["payment_method"] == "WALLET" and body["paid_by"]
    statement = client.get(
        f"/api/v1/drivers/{driver.id}/statement",
        headers=h,
        params={"date_from": _day(30).isoformat(), "date_to": _day(0).isoformat()},
    ).json()
    assert Decimal(statement["closing_balance"]) == Decimal("1050") - 200 - 1050
    again = client.post(
        f"{S}/{sid}/pay",
        headers=h,
        json={"amount": "1", "paid_on": _day(0).isoformat(), "method": "CASH"},
    )
    assert again.status_code == 409

    # Voiding a paid settlement voids its earnings; the payment really happened and stays.
    _, admin = login_as(client, db, UserRole.ADMIN)
    voided = client.post(f"{S}/{sid}/void", headers=admin, json={"reason": "خطأ في الفترة"})
    assert voided.status_code == 200, voided.text
    after = client.get(
        f"/api/v1/drivers/{driver.id}/statement",
        headers=h,
        params={"date_from": _day(30).isoformat(), "date_to": _day(0).isoformat()},
    ).json()
    assert Decimal(after["closing_balance"]) == Decimal("-200") - 1050
    actions = set(db.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(driver.id))))
    assert {
        "driver_settlement.adjusted",
        "driver_settlement.reviewed",
        "driver_settlement.reopened",
        "driver_settlement.finalized",
        "driver_settlement.paid",
        "driver_settlement.voided",
    } <= actions


def test_drafts_for_every_driver_with_a_plan(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    with_plan, already, without = make_driver(db), make_driver(db), make_driver(db)
    for d in (with_plan, already):
        make_plan(
            db,
            d,
            CompensationMethod.FIXED_MONTHLY,
            effective_from=_day(90),
            fixed_monthly_amount="6000",
        )
    _settle(client, h, str(already.id), _day(20), _day(10))
    res = client.post(
        f"{S}/generate",
        headers=h,
        json={"period_start": _day(30).isoformat(), "period_end": _day(1).isoformat()},
    )
    assert res.status_code == 200, res.text
    created = {s["driver"]["id"] for s in res.json()["created"]}
    assert str(with_plan.id) in created
    assert str(already.id) not in created and str(without.id) not in created
    assert any(s["reason"] for s in res.json()["skipped"])
    assert all(s["status"] == "DRAFT" for s in res.json()["created"])
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    assert (
        client.post(
            f"{S}/generate",
            headers=ops,
            json={"period_start": _day(30).isoformat(), "period_end": _day(1).isoformat()},
        ).status_code
        == 403
    )


def test_validation_messages_are_arabic(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    res = client.post(
        f"{S}/00000000-0000-0000-0000-000000000000/pay",
        headers=h,
        json={"amount": "-8150", "paid_on": "not-a-date", "method": "CASH"},
    )
    assert res.status_code == 422
    messages = {f["loc"][-1]: f["msg"] for f in res.json()["error"]["details"]["fields"]}
    assert messages["amount"] == "يجب أن تكون القيمة أكبر من 0"
    assert messages["paid_on"] == "تاريخ غير صحيح"


# --- Security audit (runtime H1 / security H3): payments and voids ---------------------


def _finalized(client: TestClient, db: Session, h: dict[str, str], wage: str, days: int) -> str:
    """A finalized settlement whose earnings are `wage` x `days`."""
    driver, vehicle = make_driver(db), make_vehicle(db)
    make_plan(
        db, driver, CompensationMethod.DAILY_WAGE, effective_from=_day(60), daily_wage_amount=wage
    )
    for d in range(days):
        make_completed_shift(db, driver, vehicle, day=_day(10 - d))
    sid: str = _settle(client, h, str(driver.id), _day(14), _day(1))["id"]
    assert client.post(f"{S}/{sid}/review", headers=h).status_code == 200
    assert client.post(f"{S}/{sid}/finalize", headers=h).status_code == 200, sid
    return sid


def _pay(client: TestClient, h: dict[str, str], sid: str, amount: str) -> Any:
    return client.post(
        f"{S}/{sid}/pay",
        headers=h,
        json={"amount": amount, "paid_on": _day(0).isoformat(), "method": "CASH"},
    )


def test_payment_cannot_exceed_what_is_still_due(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    sid = _finalized(client, db, h, "300", 2)  # 600.00 earned

    over = _pay(client, h, sid, "600.01")
    assert over.status_code == 422, over.text
    assert over.json()["error"]["code"] == "payment_exceeds_due"

    part = _pay(client, h, sid, "400")
    assert part.status_code == 200, part.text
    assert part.json()["status"] == "FINALIZED"  # still 200.00 due
    assert part.json()["paid_amount"] == "400.00"
    assert _pay(client, h, sid, "200.01").json()["error"]["code"] == "payment_exceeds_due"

    rest = _pay(client, h, sid, "200")
    assert rest.status_code == 200, rest.text
    assert rest.json()["status"] == "PAID" and rest.json()["paid_amount"] == "600.00"
    assert _pay(client, h, sid, "0.01").status_code == 409


def test_payment_reauth_counts_what_was_already_paid(client: TestClient, db: Session) -> None:
    from tests.test_reauth import _age

    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    sid = _finalized(client, db, h, "6000", 4)  # 24,000.00 earned
    _age(db, h)
    first = _pay(client, h, sid, "9999.99")
    assert first.status_code == 200, first.text  # below the threshold on its own
    split = _pay(client, h, sid, "1.00")  # cumulative 10,000.99
    assert split.status_code == 403
    assert split.json()["error"]["code"] == "reauth_required"
    assert (
        client.post(
            "/api/v1/auth/reauth", headers=h, json={"password": DEFAULT_PASSWORD}
        ).status_code
        == 200
    )
    assert _pay(client, h, sid, "1.00").status_code == 200


def test_voiding_a_paid_settlement_keeps_the_payment_and_needs_reauth(
    client: TestClient, db: Session
) -> None:
    from tests.test_reauth import _age

    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    sid = _finalized(client, db, h, "300", 2)
    assert _pay(client, h, sid, "600").status_code == 200
    driver_id = client.get(f"{S}/{sid}", headers=h).json()["driver"]["id"]
    _age(db, h)
    refused = client.post(f"{S}/{sid}/void", headers=h, json={"reason": "خطأ في الفترة"})
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "reauth_required"
    assert (
        client.post(
            "/api/v1/auth/reauth", headers=h, json={"password": DEFAULT_PASSWORD}
        ).status_code
        == 200
    )
    voided = client.post(f"{S}/{sid}/void", headers=h, json={"reason": "خطأ في الفترة"})
    assert voided.status_code == 200, voided.text
    statement = client.get(
        f"/api/v1/drivers/{driver_id}/statement",
        headers=h,
        params={"date_from": _day(30).isoformat(), "date_to": _day(0).isoformat()},
    ).json()
    # The earnings are gone; the 600 really paid is still on the account (driver owes it).
    assert Decimal(statement["earned"]) == 0
    assert Decimal(statement["paid"]) == Decimal("-600")
    assert Decimal(statement["closing_balance"]) == Decimal("-600")


# --- Security audit H3: segregation of duties (opt-in), adjustments, frozen inputs ------


def test_separate_finalizer_and_payer_are_opt_in(
    client: TestClient, db: Session, monkeypatch: Any
) -> None:
    from app.core.config import get_settings

    _, first = login_as(client, db, UserRole.ACCOUNTANT)
    _, second = login_as(client, db, UserRole.ACCOUNTANT)
    monkeypatch.setattr(get_settings(), "settlement_require_separate_finalizer", True)
    monkeypatch.setattr(get_settings(), "settlement_require_separate_payer", True)
    driver, vehicle = make_driver(db), make_vehicle(db)
    make_plan(
        db, driver, CompensationMethod.DAILY_WAGE, effective_from=_day(60), daily_wage_amount="300"
    )
    make_completed_shift(db, driver, vehicle, day=_day(5))
    sid = _settle(client, first, str(driver.id), _day(14), _day(1))["id"]
    assert client.post(f"{S}/{sid}/review", headers=first).status_code == 200
    same = client.post(f"{S}/{sid}/finalize", headers=first)
    assert same.status_code == 403
    assert same.json()["error"]["code"] == "separate_finalizer_required"
    assert client.post(f"{S}/{sid}/finalize", headers=second).status_code == 200
    paid_by_finalizer = _pay(client, second, sid, "300")
    assert paid_by_finalizer.status_code == 403
    assert paid_by_finalizer.json()["error"]["code"] == "separate_payer_required"
    assert _pay(client, first, sid, "300").status_code == 200


def test_large_adjustments_need_reauth(client: TestClient, db: Session) -> None:
    from tests.test_reauth import _age

    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver = make_driver(db)
    sid = _settle(client, h, str(driver.id), _day(14), _day(1))["id"]
    _age(db, h)
    small = client.post(f"{S}/{sid}/adjust", headers=h, json={"amount": "500", "reason": "حافز"})
    assert small.status_code == 200, small.text
    big = client.post(f"{S}/{sid}/adjust", headers=h, json={"amount": "50000", "reason": "حافز"})
    assert big.status_code == 403
    assert big.json()["error"]["code"] == "reauth_required"


def test_finalize_refuses_when_the_frozen_total_is_missing(client: TestClient, db: Session) -> None:
    from app.models.finance import DriverSettlement

    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver, vehicle = make_driver(db), make_vehicle(db)
    make_plan(
        db, driver, CompensationMethod.DAILY_WAGE, effective_from=_day(60), daily_wage_amount="300"
    )
    make_completed_shift(db, driver, vehicle, day=_day(5))
    sid = _settle(client, h, str(driver.id), _day(14), _day(1))["id"]
    assert client.post(f"{S}/{sid}/review", headers=h).status_code == 200
    row = db.get(DriverSettlement, sid)
    assert row is not None
    row.details = {k: v for k, v in row.details.items() if k != "computed_total"}
    db.commit()
    res = client.post(f"{S}/{sid}/finalize", headers=h)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "inputs_changed"


def test_finalize_reauth_counts_the_expected_balance(client: TestClient, db: Session) -> None:
    from tests.test_reauth import _age

    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver, vehicle = make_driver(db), make_vehicle(db)
    make_plan(
        db, driver, CompensationMethod.DAILY_WAGE, effective_from=_day(60), daily_wage_amount="300"
    )
    make_completed_shift(db, driver, vehicle, day=_day(5))
    bonus = client.post(
        f"/api/v1/drivers/{driver.id}/ledger",
        headers=h,
        json={
            "entry_type": "BONUS",
            "amount": "20000",
            "occurred_on": _day(4).isoformat(),
            "description": "مكافأة سنوية",
        },
    )
    assert bonus.status_code == 201, bonus.text
    sid = _settle(client, h, str(driver.id), _day(14), _day(1))["id"]
    assert client.post(f"{S}/{sid}/review", headers=h).status_code == 200
    _age(db, h)
    # Earnings are 300, but approving makes the driver's balance 20,300.
    res = client.post(f"{S}/{sid}/finalize", headers=h)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "reauth_required"


# --- Runtime audit L7: no overlapping open drafts for one driver -----------------------


def test_overlapping_drafts_are_refused(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver = make_driver(db)
    first = _settle(client, h, str(driver.id), _day(14), _day(1))
    same = client.post(
        S,
        headers=h,
        json={
            "driver_id": str(driver.id),
            "period_start": _day(10).isoformat(),
            "period_end": _day(3).isoformat(),
        },
    )
    assert same.status_code == 409, same.text
    assert same.json()["error"]["code"] == "overlapping_draft"
    voided = client.post(f"{S}/{first['id']}/void", headers=h, json={"reason": "مكرر"})
    assert voided.status_code == 200
    assert _settle(client, h, str(driver.id), _day(14), _day(1))["status"] == "DRAFT"
