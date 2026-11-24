"""Driver settlement workflow (U20): draft → reviewed → approved → paid."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.audit import AuditLog
from app.models.driver import CompensationMethod
from tests.factories import login_as, make_completed_shift, make_driver, make_plan, make_vehicle
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
            "amount": "850",
            "paid_on": _day(0).isoformat(),
            "method": "WALLET",
            "reference": "VF-1",
        },
    )
    assert paid.status_code == 200, paid.text
    body = paid.json()
    assert body["status"] == "PAID" and body["paid_amount"] == "850.00"
    assert body["payment_method"] == "WALLET" and body["paid_by"]
    statement = client.get(
        f"/api/v1/drivers/{driver.id}/statement",
        headers=h,
        params={"date_from": _day(30).isoformat(), "date_to": _day(0).isoformat()},
    ).json()
    assert Decimal(statement["closing_balance"]) == Decimal("1050") - 200 - 850
    again = client.post(
        f"{S}/{sid}/pay",
        headers=h,
        json={"amount": "1", "paid_on": _day(0).isoformat(), "method": "CASH"},
    )
    assert again.status_code == 409

    # Voiding a paid settlement voids both its earnings and its payment.
    _, admin = login_as(client, db, UserRole.ADMIN)
    voided = client.post(f"{S}/{sid}/void", headers=admin, json={"reason": "خطأ في الفترة"})
    assert voided.status_code == 200, voided.text
    after = client.get(
        f"/api/v1/drivers/{driver.id}/statement",
        headers=h,
        params={"date_from": _day(30).isoformat(), "date_to": _day(0).isoformat()},
    ).json()
    assert Decimal(after["closing_balance"]) == Decimal("-200")
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
