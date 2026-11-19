"""Refuelling plausibility checks (U15)."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.models.finance import FuelTransaction, PaidBy, QuantityUnit
from app.services import exception_rules as rules
from app.services import fuel_plausibility as service
from app.services.fuel_plausibility import CheckResult
from tests.factories import login_as, make_completed_shift, make_driver
from tests.test_exceptions import YESTERDAY, ctx_around, fuel, pair


def _results(db: Session, tx: FuelTransaction) -> dict[str, service.Check]:
    return {c.code: c for c in service.check(db, tx)}


def test_odometer_going_backwards_or_outside_the_shift(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(
        db, driver, vehicle, day=YESTERDAY, start_odometer_km=50_000, end_odometer_km=50_200
    )
    assert shift.started_at
    t0 = shift.started_at
    fuel(db, vehicle, at=t0 + timedelta(hours=1), driver=driver, odometer_km=50_050)
    back = fuel(
        db, vehicle, at=t0 + timedelta(hours=4), driver=driver, odometer_km=49_900, amount="250"
    )
    c = _results(db, back)["ODOMETER"]
    assert c.result is CheckResult.FAIL and c.threshold == 50_050

    driver2, vehicle2 = pair(db)
    s2 = make_completed_shift(
        db, driver2, vehicle2, day=YESTERDAY, start_odometer_km=1_000, end_odometer_km=1_100
    )
    assert s2.started_at
    ok = fuel(
        db,
        vehicle2,
        at=s2.started_at + timedelta(minutes=30),
        driver=driver2,
        odometer_km=1_090,
        amount="80",
    )
    far = fuel(
        db, vehicle2, at=s2.started_at + timedelta(hours=2), driver=driver2, odometer_km=1_500
    )
    assert _results(db, far)["ODOMETER"].result is CheckResult.FAIL
    assert _results(db, ok)["ODOMETER"].result is CheckResult.PASS


def test_quantity_above_the_limit_or_far_above_the_vehicles_usual(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=600)
    assert shift.started_at
    t0 = shift.started_at
    huge = fuel(db, vehicle, at=t0, quantity="150", code="GASOLINE", unit=QuantityUnit.LITER)
    c = _results(db, huge)["QUANTITY"]
    assert c.result is CheckResult.FAIL and c.threshold == 100

    for i in range(5):
        fuel(db, vehicle, at=t0 + timedelta(hours=1 + i), quantity="10", amount=str(70 + i))
    big = fuel(db, vehicle, at=t0 + timedelta(hours=8), quantity="25", amount="175")
    c = _results(db, big)["QUANTITY"]
    assert c.result is CheckResult.FAIL  # 25 m³ is under 40 but over 2 x the usual 10
    assert c.details["purchases_compared"] == 5


def test_rapid_repeated_refuels(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=600)
    assert shift.started_at
    t0 = shift.started_at
    fuel(db, vehicle, at=t0, odometer_km=1_000, amount="100")
    soon = fuel(db, vehicle, at=t0 + timedelta(minutes=30), odometer_km=1_010, amount="90")
    assert _results(db, soon)["RAPID_REPEAT"].result is CheckResult.FAIL
    short = fuel(db, vehicle, at=t0 + timedelta(hours=3), odometer_km=1_030, amount="80")
    assert _results(db, short)["RAPID_REPEAT"].details["km_since"] == 20
    assert _results(db, short)["RAPID_REPEAT"].result is CheckResult.FAIL
    later = fuel(
        db, vehicle, at=t0 + timedelta(hours=6, minutes=30), odometer_km=1_200, amount="70"
    )
    assert _results(db, later)["RAPID_REPEAT"].result is CheckResult.PASS


def test_driver_must_be_assigned_or_driving(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY)
    assert shift.started_at
    t = shift.started_at + timedelta(hours=1)
    assert (
        _results(db, fuel(db, vehicle, at=t, driver=driver))["ASSIGNMENT"].result
        is CheckResult.PASS
    )
    stranger = make_driver(db)
    other = fuel(db, vehicle, at=t + timedelta(minutes=90), driver=stranger, amount="210")
    assert _results(db, other)["ASSIGNMENT"].result is CheckResult.FAIL
    nobody = fuel(db, vehicle, at=t + timedelta(hours=3), amount="190")
    assert _results(db, nobody)["ASSIGNMENT"].result is CheckResult.NOT_CHECKABLE


def test_missing_data_is_not_checkable_and_covered_checks_name_their_rule(db: Session) -> None:
    driver, vehicle = pair(db)
    at = YESTERDAY
    shift = make_completed_shift(db, driver, vehicle, day=at)
    assert shift.started_at
    tx = fuel(
        db, vehicle, at=shift.started_at - timedelta(hours=5), driver=driver, paid_by=PaidBy.DRIVER
    )
    checks = _results(db, tx)
    assert checks["LOCATION"].result is CheckResult.NOT_CHECKABLE
    assert checks["ODOMETER"].result is CheckResult.NOT_CHECKABLE
    assert checks["SHIFT_TIME"].result is CheckResult.FAIL
    assert checks["SHIFT_TIME"].covered_by == "FUEL_OUTSIDE_SHIFT"


def test_rule_raises_one_case_with_every_check_as_evidence(client: TestClient, db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(
        db, driver, vehicle, day=YESTERDAY, start_odometer_km=50_000, end_odometer_km=50_200
    )
    assert shift.started_at
    fuel(db, vehicle, at=shift.started_at + timedelta(hours=1), driver=driver, odometer_km=50_050)
    back = fuel(
        db,
        vehicle,
        at=shift.started_at + timedelta(hours=4),
        driver=driver,
        odometer_km=49_900,
        amount="250",
    )
    found = [
        c
        for c in rules.fuel_plausibility(ctx_around(db, shift)).candidates
        if c.vehicle_id == vehicle.id
    ]
    assert [c.subject_id for c in found] == [back.id]
    assert found[0].summary.startswith("عملية وقود تحتاج مراجعة")
    assert found[0].severity.value == "MEDIUM"
    assert {e["check"] for e in found[0].evidence["checks"]} == {
        "ASSIGNMENT",
        "SHIFT_TIME",
        "ODOMETER",
        "LOCATION",
        "QUANTITY",
        "RAPID_REPEAT",
        "DUPLICATE",
    }

    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    res = client.get(f"/api/v1/fuel/{back.id}/plausibility", headers=acc)
    assert res.status_code == 200, res.text
    odometer = next(c for c in res.json() if c["code"] == "ODOMETER")
    assert odometer["result"] == "FAIL" and odometer["details"]["previous_reading_km"] == 50_050
