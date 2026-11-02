"""Fuel efficiency by shift, day, week or month (U13).

Distance is the odometer distance of completed shifts; fuel is approved
purchases of fuel-category types only, so engine oil and other
consumables never enter efficiency figures. Quantities are kept per fuel
type and unit (litres, m³ or kg for CNG, as recorded) and never added
across units.

Many vehicles run on CNG and gasoline. When one period has more than
one fuel, the distance is shared and cannot be split between them: the
per-fuel km/unit is then marked as approximate, and the combined EGP/km
(all fuel cost over the distance) is the comparable figure.

Purchases are not consumption: a refuel covers the following driving.
Shift-level figures are therefore indicative; weeks and months smooth
this out. Missing distance or fuel gives no figure, never an estimate.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_day_bounds_utc, to_local_date, week_start
from app.models.finance import FuelCategory, FuelTransaction, FuelType, QuantityUnit, RecordStatus
from app.models.shift import Shift, ShiftStatus
from app.services import finance_common as fc

Period = Literal["shift", "day", "week", "month"]
ZERO = Decimal("0")
LIQUID_UNITS = (QuantityUnit.LITER,)


@dataclass
class FuelLine:
    fuel_type: str
    code: str
    unit: QuantityUnit
    quantity: Decimal = ZERO
    amount: Decimal = ZERO
    purchases: int = 0
    km_per_unit: Decimal | None = None
    litres_per_100km: Decimal | None = None
    egp_per_km: Decimal | None = None


@dataclass
class EfficiencyRow:
    period: Period
    period_start: date
    vehicle_id: uuid.UUID
    vehicle_code: str
    shift_id: uuid.UUID | None = None
    shifts: int = 0
    distance_km: int = 0
    distance_missing: bool = False
    fuels: dict[tuple[str, QuantityUnit], FuelLine] = field(default_factory=dict)
    fuel_cost: Decimal = ZERO
    egp_per_km: Decimal | None = None

    @property
    def mixed_fuel(self) -> bool:
        return len(self.fuels) > 1


def _bucket(period: Period, day: date) -> date:
    if period == "week":
        return week_start(day)
    if period == "month":
        return day.replace(day=1)
    return day


def _ratio(a: Decimal, b: Decimal, places: str) -> Decimal | None:
    return (a / b).quantize(Decimal(places), rounding=ROUND_HALF_UP) if b > 0 else None


def compute(
    db: Session,
    date_from: date,
    date_to: date,
    *,
    period: Period = "week",
    vehicle_id: uuid.UUID | None = None,
    fuel_type_id: uuid.UUID | None = None,
) -> tuple[list[EfficiencyRow], int]:
    """Rows per vehicle and period; also the number of purchases not tied to a shift
    (only relevant for period="shift", where they cannot be placed)."""
    start, end = local_day_bounds_utc(date_from)[0], local_day_bounds_utc(date_to)[1]
    rows: dict[tuple[uuid.UUID, date, uuid.UUID | None], EfficiencyRow] = {}

    def row(vid: uuid.UUID, code: str, day: date, shift_id: uuid.UUID | None) -> EfficiencyRow:
        # Per shift, rows are keyed by the shift alone: fuel bought after midnight
        # on an overnight shift still belongs to that shift.
        key = (vid, date.min, shift_id) if period == "shift" else (vid, _bucket(period, day), None)
        if key not in rows:
            rows[key] = EfficiencyRow(
                period=period,
                period_start=_bucket(period, day),
                vehicle_id=vid,
                vehicle_code=code,
                shift_id=key[2],
            )
        return rows[key]

    shifts_stmt = select(Shift).where(
        Shift.status == ShiftStatus.COMPLETED,
        Shift.started_at >= start,
        Shift.started_at < end,
    )
    if vehicle_id:
        shifts_stmt = shifts_stmt.where(Shift.vehicle_id == vehicle_id)
    for s in db.scalars(shifts_stmt).all():
        assert s.started_at is not None  # noqa: S101 - completed shifts have started
        r = row(s.vehicle_id, s.vehicle.internal_code, to_local_date(s.started_at), s.id)
        r.shifts += 1
        if s.odometer_distance_km is None:
            r.distance_missing = True
        else:
            r.distance_km += s.odometer_distance_km

    fuel_stmt = (
        select(FuelTransaction)
        .join(FuelType, FuelType.id == FuelTransaction.fuel_type_id)
        .where(
            FuelTransaction.status == RecordStatus.APPROVED,
            FuelType.category == FuelCategory.FUEL,
            FuelTransaction.occurred_at >= start,
            FuelTransaction.occurred_at < end,
        )
    )
    if vehicle_id:
        fuel_stmt = fuel_stmt.where(FuelTransaction.vehicle_id == vehicle_id)
    if fuel_type_id:
        fuel_stmt = fuel_stmt.where(FuelTransaction.fuel_type_id == fuel_type_id)
    unplaced = 0
    for t in db.scalars(fuel_stmt).all():
        if period == "shift" and t.shift_id is None:
            unplaced += 1
            continue
        r = row(t.vehicle_id, t.vehicle.internal_code, to_local_date(t.occurred_at), t.shift_id)
        line = r.fuels.setdefault(
            (t.fuel_type.code, t.unit), FuelLine(t.fuel_type.name_ar, t.fuel_type.code, t.unit)
        )
        line.quantity += t.quantity
        line.amount += t.total_amount
        line.purchases += 1
        r.fuel_cost += t.total_amount

    for r in rows.values():
        distance = Decimal(r.distance_km)
        usable = r.distance_km > 0 and not r.distance_missing
        r.fuel_cost = fc.money(r.fuel_cost)
        r.egp_per_km = _ratio(r.fuel_cost, distance, "0.01") if usable else None
        for line in r.fuels.values():
            line.amount = fc.money(line.amount)
            if not usable:
                continue
            line.km_per_unit = _ratio(distance, line.quantity, "0.01")
            line.egp_per_km = _ratio(line.amount, distance, "0.01")
            if line.unit in LIQUID_UNITS:
                line.litres_per_100km = _ratio(line.quantity * 100, distance, "0.01")
    ordered = sorted(rows.values(), key=lambda r: (r.period_start, r.vehicle_code, str(r.shift_id)))
    return ordered, unplaced


def vehicle_totals(rows: list[EfficiencyRow]) -> list[dict[str, object]]:
    """Whole-range totals per vehicle: combined EGP/km is valid even for mixed fuels."""
    totals: dict[uuid.UUID, dict[str, object]] = {}
    cost: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    km: dict[uuid.UUID, int] = defaultdict(int)
    missing: dict[uuid.UUID, bool] = defaultdict(bool)
    for r in rows:
        totals.setdefault(r.vehicle_id, {"vehicle": r.vehicle_code})
        cost[r.vehicle_id] += r.fuel_cost
        km[r.vehicle_id] += r.distance_km
        missing[r.vehicle_id] = missing[r.vehicle_id] or r.distance_missing
    for vid, t in totals.items():
        t["distance_km"] = km[vid]
        t["fuel_cost"] = fc.money(cost[vid])
        t["egp_per_km"] = (
            _ratio(cost[vid], Decimal(km[vid]), "0.01") if km[vid] and not missing[vid] else None
        )
    return sorted(totals.values(), key=lambda t: str(t["vehicle"]))
