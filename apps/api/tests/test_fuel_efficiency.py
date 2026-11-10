"""Fuel efficiency by shift/day/week/month (U13)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, week_start
from app.models.finance import (
    FuelTransaction,
    PaidBy,
    PaymentMethod,
    QuantityUnit,
    RecordStatus,
)
from app.models.fleet import Vehicle
from app.models.shift import Shift
from app.services import fuel_efficiency
from tests.factories import fuel_type_id, login_as, make_completed_shift, make_vehicle
from tests.test_exceptions import pair
from tests.test_reports import _report

# A Monday two weeks back, so a whole Saturday-to-Friday week is in the past.
MONDAY = week_start(local_today()) - timedelta(days=12)


def _buy(
    db: Session,
    shift: Shift,
    code: str,
    quantity: str,
    amount: str,
    unit: QuantityUnit,
    *,
    linked: bool = True,
) -> None:
    assert shift.started_at
    db.add(
        FuelTransaction(
            vehicle_id=shift.vehicle_id,
            driver_id=shift.driver_id,
            shift_id=shift.id if linked else None,
            fuel_type_id=uuid.UUID(fuel_type_id(db, code)),
            quantity=Decimal(quantity),
            unit=unit,
            total_amount=Decimal(amount),
            occurred_at=shift.started_at + timedelta(hours=1),
            payment_method=PaymentMethod.CASH,
            paid_by=PaidBy.COMPANY,
            status=RecordStatus.APPROVED,
        )
    )
    db.commit()


def _shift(
    db: Session,
    vehicle: Vehicle | None = None,
    *,
    day: date = MONDAY,
    km: int = 100,
    start: int | None = 1_000,
) -> Shift:
    driver, v = pair(db)
    return make_completed_shift(
        db,
        driver,
        vehicle or v,
        day=day,
        start_odometer_km=start,
        end_odometer_km=(start or 0) + km,
    )


def _rows(
    db: Session, vehicle_id: uuid.UUID, period: fuel_efficiency.Period = "week"
) -> tuple[list[fuel_efficiency.EfficiencyRow], int]:
    rows, unplaced = fuel_efficiency.compute(
        db,
        MONDAY - timedelta(days=7),
        MONDAY + timedelta(days=7),
        period=period,
        vehicle_id=vehicle_id,
    )
    return rows, unplaced


def test_gasoline_km_per_litre_l_per_100km_and_cost_per_km(db: Session) -> None:
    s = _shift(db, km=100)
    _buy(db, s, "GASOLINE", "8.000", "120.00", QuantityUnit.LITER)
    [row], _ = _rows(db, s.vehicle_id)
    [line] = row.fuels.values()
    assert line.km_per_unit == Decimal("12.50")
    assert line.litres_per_100km == Decimal("8.00")
    assert line.egp_per_km == Decimal("1.20")
    assert row.egp_per_km == Decimal("1.20") and not row.mixed_fuel


def test_cng_uses_its_recorded_unit_and_oil_is_left_out(db: Session) -> None:
    s = _shift(db, km=100)
    _buy(db, s, "CNG", "10.000", "70.00", QuantityUnit.CUBIC_METER)
    _buy(db, s, "ENGINE_OIL", "4.000", "600.00", QuantityUnit.LITER)
    [row], _ = _rows(db, s.vehicle_id)
    [line] = row.fuels.values()  # the oil purchase is not a fuel line
    assert (line.code, line.unit) == ("CNG", QuantityUnit.CUBIC_METER)
    assert line.km_per_unit == Decimal("10.00")
    assert line.litres_per_100km is None  # not a liquid fuel
    assert row.fuel_cost == Decimal("70.00") and row.egp_per_km == Decimal("0.70")


def test_mixed_fuels_share_the_distance_and_combine_cost(db: Session) -> None:
    s = _shift(db, km=200)
    _buy(db, s, "CNG", "15.000", "105.00", QuantityUnit.CUBIC_METER)
    _buy(db, s, "GASOLINE", "5.000", "75.00", QuantityUnit.LITER)
    [row], _ = _rows(db, s.vehicle_id)
    assert row.mixed_fuel
    assert row.egp_per_km == Decimal("0.90")  # (105 + 75) / 200
    [total] = fuel_efficiency.vehicle_totals([row])
    assert total["egp_per_km"] == Decimal("0.90")


def test_missing_distance_gives_no_figures(db: Session) -> None:
    s = _shift(db, km=100, start=None)
    _buy(db, s, "GASOLINE", "8.000", "120.00", QuantityUnit.LITER)
    [row], _ = _rows(db, s.vehicle_id)
    assert row.distance_missing
    [line] = row.fuels.values()
    assert line.km_per_unit is None and row.egp_per_km is None


def test_grouping_by_shift_day_week_and_month(db: Session) -> None:
    vehicle = make_vehicle(db)
    a = _shift(db, vehicle, day=MONDAY, km=100)
    b = _shift(db, vehicle, day=MONDAY + timedelta(days=1), km=60)
    _buy(db, a, "GASOLINE", "8.000", "120.00", QuantityUnit.LITER)
    _buy(db, b, "GASOLINE", "4.000", "60.00", QuantityUnit.LITER, linked=False)

    week, _ = _rows(db, vehicle.id, "week")
    assert [(r.distance_km, r.shifts) for r in week] == [(160, 2)]
    assert week[0].egp_per_km == Decimal("1.13")  # 180 / 160

    days, _ = _rows(db, vehicle.id, "day")
    assert [r.distance_km for r in days] == [100, 60]

    shifts, unplaced = _rows(db, vehicle.id, "shift")
    assert {r.shift_id for r in shifts} == {a.id, b.id}
    assert unplaced == 1  # the purchase not tied to a shift cannot be placed per shift

    months, _ = _rows(db, vehicle.id, "month")
    assert sum(r.distance_km for r in months) == 160


def test_report_by_period(client: TestClient, db: Session) -> None:
    s = _shift(db, km=100)
    _buy(db, s, "GASOLINE", "8.000", "120.00", QuantityUnit.LITER)
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    report = _report(
        client,
        h,
        "fuel_efficiency",
        vehicle_id=str(s.vehicle_id),
        period="day",
        date_from=(MONDAY - timedelta(days=1)).isoformat(),
        date_to=(MONDAY + timedelta(days=1)).isoformat(),
    )
    [row] = report["rows"]
    assert row["km_per_unit"] == "12.50" and row["litres_per_100km"] == "8.00"
    assert report["columns"][0]["label"] == "بداية اليوم"
    bad = client.get("/api/v1/reports/fuel_efficiency", params={"period": "year"}, headers=h)
    assert bad.status_code == 422
