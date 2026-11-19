"""Rolling vehicle fuel baselines (U14)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_day_bounds_utc, local_today, week_start
from app.models.driver import Driver
from app.models.fleet import Vehicle
from app.services import fuel_baselines
from app.services.fuel_baselines import BaselineStatus
from tests.factories import login_as, make_completed_shift
from tests.test_exceptions import fuel, pair
from tests.test_reports import _report

TARGET = week_start(local_today()) - timedelta(days=7)


def _week(
    db: Session,
    driver: Driver,
    vehicle: Vehicle,
    week: date,
    *,
    km: int = 300,
    qty: str = "40",
    amount: str = "300",
    code: str = "CNG",
    start: int | None = None,
) -> None:
    day = week + timedelta(days=1)
    odo = 10_000 + (TARGET - week).days * 100
    make_completed_shift(
        db,
        driver,
        vehicle,
        day=day,
        start_odometer_km=start if start is not None else odo,
        end_odometer_km=odo + km,
    )
    fuel(
        db,
        vehicle,
        at=local_day_bounds_utc(day)[0] + timedelta(hours=12),
        amount=amount,
        quantity=qty,
        code=code,
    )


def _assess(db: Session, vehicle: Vehicle) -> fuel_baselines.WeekAssessment:
    [a] = fuel_baselines.assess(db, TARGET, TARGET, vehicle_id=vehicle.id)
    return a


def test_too_little_history_is_insufficient_not_a_verdict(db: Session) -> None:
    driver, vehicle = pair(db)
    for back in range(0, 3):  # two history weeks: below the minimum of four
        _week(
            db, driver, vehicle, TARGET - timedelta(days=7 * back), qty="100" if back == 0 else "40"
        )
    a = _assess(db, vehicle)
    assert a.status is BaselineStatus.INSUFFICIENT and a.reason == "not_enough_history"
    assert a.historical.samples == 2


def test_incomplete_weeks_are_never_used_or_judged(db: Session) -> None:
    driver, vehicle = pair(db)
    for back in range(1, 6):
        _week(db, driver, vehicle, TARGET - timedelta(days=7 * back))
    # One history week has only 50 km (below the 150 km minimum).
    _week(db, driver, vehicle, TARGET - timedelta(days=7 * 6), km=50)
    _week(db, driver, vehicle, TARGET, qty="40")
    a = _assess(db, vehicle)
    assert a.historical.samples == 5 and a.excluded_weeks == 1
    assert a.status is BaselineStatus.NORMAL and a.ratio == Decimal("1.00")
    assert a.recent.samples == 4 and a.recent.value == Decimal("7.50")

    other_driver, short = pair(db)
    _week(db, other_driver, short, TARGET, km=100)  # the target week itself is too short
    assert _assess(db, short).reason == "incomplete_week"


def test_a_new_vehicle_is_compared_with_peers_of_the_same_operation(db: Session) -> None:
    for _ in range(2):  # two peers x four weeks of fixed-route work
        driver, peer = pair(db)
        for back in range(1, 5):
            _week(db, driver, peer, TARGET - timedelta(days=7 * back))
    driver, new = pair(db)
    _week(db, driver, new, TARGET, qty="90", amount="675")
    a = _assess(db, new)
    assert a.historical.samples == 0
    assert a.basis == "peer" and a.peer.samples == 8 and a.peer.value == Decimal("7.50")
    assert a.status is BaselineStatus.UNUSUAL  # 300/90 = 3.33 km/m³, 2.25x worse


def test_a_bi_fuel_week_is_compared_on_cost_per_km(db: Session) -> None:
    driver, vehicle = pair(db)
    for back in range(1, 6):
        week = TARGET - timedelta(days=7 * back)
        _week(db, driver, vehicle, week)
        fuel(
            db,
            vehicle,
            at=local_day_bounds_utc(week + timedelta(days=2))[0] + timedelta(hours=12),
            amount="60",
            quantity="4",
            code="GASOLINE",
        )
    _week(db, driver, vehicle, TARGET, amount="300")
    fuel(
        db,
        vehicle,
        at=local_day_bounds_utc(TARGET + timedelta(days=2))[0] + timedelta(hours=12),
        amount="60",
        quantity="4",
        code="GASOLINE",
    )
    a = _assess(db, vehicle)
    assert a.metric == "egp_per_km" and a.fuel is None
    assert a.current == Decimal("1.20") and a.historical.value == Decimal("1.20")
    assert set(a.unit_price) == {"CNG:CUBIC_METER", "GASOLINE:CUBIC_METER"}


def test_report_shows_every_week_with_its_baselines(client: TestClient, db: Session) -> None:
    driver, vehicle = pair(db)
    for back in range(0, 5):
        _week(
            db, driver, vehicle, TARGET - timedelta(days=7 * back), qty="100" if back == 0 else "40"
        )
    _, h = login_as(client, db, UserRole.OPERATIONS)
    report = _report(
        client,
        h,
        "fuel_baselines",
        vehicle_id=str(vehicle.id),
        date_from=TARGET.isoformat(),
        date_to=(TARGET + timedelta(days=6)).isoformat(),
    )
    [row] = report["rows"]
    assert row["status"] == "استهلاك غير معتاد — مراجعة مطلوبة"
    assert row["historical"] == "7.50 (4)" and row["metric"] == "كم/وحدة"
