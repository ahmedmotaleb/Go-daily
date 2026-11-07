"""Exception engine V2 (U26): new rules and the explanation on every case."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today
from app.models.cash import ShiftCloseout
from app.models.route_events import SchoolRun, SchoolRunStatus
from app.models.shift import Shift
from app.services import exception_rules as rules
from tests.factories import login_as, make_completed_shift, make_driver_account
from tests.test_driver_cash import _close, _start
from tests.test_exceptions import codes, ctx_around, pair


def test_every_rule_has_a_review_action_and_threshold_split() -> None:
    assert {info.code for info, _ in rules.RULES} <= set(rules.REVIEW_ACTIONS)
    why = rules.explain("GPS_DISABLED", {"minutes": 12, "threshold_minutes": 5})
    assert why.observed == {"minutes": 12}
    assert why.thresholds == {"threshold_minutes": 5}
    assert why.reason and why.action


def test_assignment_override_and_school_runs(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=local_today(), minutes=120)
    shift.assignment_override_reason = "السيارة الأساسية في الصيانة"
    assert shift.started_at and shift.ended_at
    run = SchoolRun(
        route_id=shift.sessions[0].route_id or _any_route(db),
        service_date=local_today(),
        scheduled_start_at=shift.started_at,
        scheduled_end_at=shift.ended_at,
        vehicle_id=vehicle.id,
        driver_id=driver.id,
        status=SchoolRunStatus.MISSED,
    )
    db.add(run)
    db.commit()
    ctx = ctx_around(db, shift)
    assert "ASSIGNMENT_OVERRIDE" in codes(rules.assignment_override(ctx))
    school = rules.school_run_attention(ctx)
    assert codes(school) == ["SCHOOL_RUN"]
    assert school.candidates[0].severity.value == "HIGH"


def _any_route(db: Session) -> object:
    from app.models.operations import RouteDefinition

    route = db.scalar(select(RouteDefinition).limit(1))
    if route is None:
        from tests.factories import make_route

        route = make_route(db)
    return route.id


def test_cash_not_handed_over_after_the_allowed_days(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    out = _close(client, h, _start(client, h, vehicle)["id"])
    ctx = ctx_around(db)
    # Today's close-out is within the allowed days: nothing yet.
    assert codes(rules.cash_not_handed_over(ctx)) == []
    closeout = db.get(ShiftCloseout, out["id"])
    assert closeout is not None
    closeout.service_date = local_today() - timedelta(days=3)
    db.commit()
    found = rules.cash_not_handed_over(ctx)
    case = next(c for c in found.candidates if c.driver_id == driver.id)
    assert case.evidence["outstanding"] == Decimal("1980.00")
    assert case.evidence["days_waiting"] == 3 and case.evidence["threshold_days"] == 2
    # Once the cash is collected the case is no longer produced (and gets cleared).
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    client.post(
        "/api/v1/cash/collections",
        headers=acc,
        json={"driver_id": str(driver.id), "amount": "1980"},
    )
    again = rules.cash_not_handed_over(ctx)
    assert all(c.driver_id != driver.id for c in again.candidates)
    assert f"CASH_NOT_HANDED_OVER:{driver.id}" in again.scopes


def test_cases_carry_the_explanation(client: TestClient, db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=local_today(), minutes=60)
    shift.assignment_override_reason = "تجربة"
    db.commit()
    _, admin = login_as(client, db, UserRole.ADMIN)
    res = client.post("/api/v1/exceptions/run", json={"days": 1}, headers=admin)
    assert res.status_code in (200, 201), res.text
    cases = client.get(
        "/api/v1/exceptions", params={"rule_code": "ASSIGNMENT_OVERRIDE"}, headers=admin
    ).json()["items"]
    case = next(c for c in cases if c["shift_id"] == str(shift.id))
    assert case["review_action"] == rules.REVIEW_ACTIONS["ASSIGNMENT_OVERRIDE"]
    assert case["reason"] and case["observed"]["reason"] == "تجربة"
    rules_out = client.get("/api/v1/exceptions/rules", headers=admin).json()["rules"]
    assert all(r["review_action"] for r in rules_out)
    assert db.get(Shift, shift.id) is not None
