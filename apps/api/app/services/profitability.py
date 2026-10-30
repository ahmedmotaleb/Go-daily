"""Vehicle profit & loss (Task 19).

Built only from APPROVED records; nothing is estimated. When inputs are
missing (no fuel records for a vehicle that drove, days without revenue,
drivers without a finalised settlement, ...) the figures stay as recorded
and a warning says what is missing.

Allocation rules (stated in the output, never hidden):
- revenue with a service period (contracts, platform statements) and
  settlement earnings are spread over their period by days;
- driver earnings are split across vehicles by the driver's completed-shift
  minutes on each vehicle within the earning period;
- costs are split across operation types by session minutes.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.time import local_day_bounds_utc, to_local_date, utcnow
from app.models.finance import (
    DriverLedgerEntry,
    DriverSettlement,
    Expense,
    ExpenseGroup,
    FuelCategory,
    FuelTransaction,
    LedgerEntryType,
    RecordStatus,
    RevenueEntry,
    RideHailingStatement,
    SettlementStatus,
)
from app.models.fleet import Vehicle
from app.models.operations import OperationType
from app.models.shift import OperationSession, SessionStatus, Shift, ShiftStatus
from app.services import finance_common as fc
from app.services import ride_hailing, tracking

ZERO = Decimal("0")
UNTYPED = "__none__"


@dataclass
class _VehicleAcc:
    gross: Decimal = ZERO
    fees: Decimal = ZERO
    revenue_by_type: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    revenue_days: set[date] = field(default_factory=set)
    fuel_by_type: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    fuel: Decimal = ZERO
    consumables: Decimal = ZERO
    fuel_records: int = 0
    expenses_by_group: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    maintenance: Decimal = ZERO
    other_expenses: Decimal = ZERO
    driver_cost: Decimal = ZERO
    shifts: list[Shift] = field(default_factory=list)
    minutes_by_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    pending: int = 0
    drivers_uncovered: set[uuid.UUID] = field(default_factory=set)


def _minutes(start: Any, end: Any) -> int:
    return max(0, int(((end or utcnow()) - start).total_seconds() // 60))


def _shift_minutes(
    db: Session, start_utc: Any, end_utc: Any
) -> dict[uuid.UUID, dict[tuple[uuid.UUID, date], int]]:
    """driver_id -> {(vehicle_id, local day): completed-shift minutes}."""
    rows = db.execute(
        select(Shift.driver_id, Shift.vehicle_id, Shift.started_at, Shift.ended_at).where(
            Shift.status == ShiftStatus.COMPLETED,
            Shift.started_at >= start_utc,
            Shift.started_at < end_utc,
        )
    ).all()
    out: dict[uuid.UUID, dict[tuple[uuid.UUID, date], int]] = defaultdict(lambda: defaultdict(int))
    for driver_id, vehicle_id, started, ended in rows:
        if started is not None:
            out[driver_id][(vehicle_id, to_local_date(started))] += _minutes(started, ended)
    return out


def _allocate(
    amount: Decimal,
    minutes: dict[tuple[uuid.UUID, date], int],
    start: date,
    end: date,
) -> dict[uuid.UUID, Decimal] | None:
    """Split by minutes per vehicle within [start, end]; None if no shifts."""
    per_vehicle: dict[uuid.UUID, int] = defaultdict(int)
    for (vehicle_id, day), m in minutes.items():
        if start <= day <= end:
            per_vehicle[vehicle_id] += m
    total = sum(per_vehicle.values())
    if total == 0:
        return None
    return {v: amount * Decimal(m) / Decimal(total) for v, m in per_vehicle.items()}


@dataclass(frozen=True)
class _Range:
    date_from: date
    date_to: date

    @property
    def start_utc(self) -> datetime:
        return local_day_bounds_utc(self.date_from)[0]

    @property
    def end_utc(self) -> datetime:
        return local_day_bounds_utc(self.date_to)[1]


type _Acc = dict[uuid.UUID, _VehicleAcc]


def _add_revenue(db: Session, r: _Range, acc: _Acc) -> None:
    """Approved revenue, spread over service periods by days."""
    rows = db.scalars(
        select(RevenueEntry).where(
            RevenueEntry.status == RecordStatus.APPROVED,
            func.coalesce(RevenueEntry.period_end, RevenueEntry.occurred_on) >= r.date_from,
            func.coalesce(RevenueEntry.period_start, RevenueEntry.occurred_on) <= r.date_to,
        )
    ).all()
    for e in rows:
        a = acc[e.vehicle_id]
        if e.period_start and e.period_end:
            share = fc.period_share(e.period_start, e.period_end, r.date_from, r.date_to)
            day = e.period_start
            while day <= e.period_end:
                a.revenue_days.add(day)
                day += timedelta(days=1)
        else:
            share = Decimal(1)
            a.revenue_days.add(e.occurred_on)
        a.gross += e.amount * share
        a.fees += e.fees_withheld * share
        key = str(e.operation_type_id) if e.operation_type_id else UNTYPED
        a.revenue_by_type[key] += e.amount * share


def _add_costs(db: Session, r: _Range, acc: _Acc) -> None:
    """Approved fuel/consumables and general expenses."""
    for tx in db.scalars(
        select(FuelTransaction).where(
            FuelTransaction.status == RecordStatus.APPROVED,
            FuelTransaction.occurred_at >= r.start_utc,
            FuelTransaction.occurred_at < r.end_utc,
        )
    ).all():
        a = acc[tx.vehicle_id]
        a.fuel_by_type[tx.fuel_type.code] += tx.total_amount
        if tx.fuel_type.category is FuelCategory.FUEL:
            a.fuel += tx.total_amount
            a.fuel_records += 1
        else:
            a.consumables += tx.total_amount
    for ex in db.scalars(
        select(Expense).where(
            Expense.status == RecordStatus.APPROVED,
            Expense.occurred_at >= r.start_utc,
            Expense.occurred_at < r.end_utc,
        )
    ).all():
        a = acc[ex.vehicle_id]
        group = ex.category.pnl_group
        a.expenses_by_group[group.value] += ex.amount
        if group is ExpenseGroup.MAINTENANCE:
            a.maintenance += ex.amount
        else:
            a.other_expenses += ex.amount


def _add_activity(db: Session, r: _Range, acc: _Acc) -> dict[uuid.UUID, float]:
    """Completed shifts and session minutes per operation type; returns GPS km."""
    shifts = db.scalars(
        select(Shift).where(
            Shift.status == ShiftStatus.COMPLETED,
            Shift.started_at >= r.start_utc,
            Shift.started_at < r.end_utc,
        )
    ).all()
    for s in shifts:
        acc[s.vehicle_id].shifts.append(s)
    for vehicle, type_id, started, ended in db.execute(
        select(
            Shift.vehicle_id,
            OperationSession.operation_type_id,
            OperationSession.started_at,
            OperationSession.ended_at,
        )
        .join(Shift, Shift.id == OperationSession.shift_id)
        .where(
            Shift.status == ShiftStatus.COMPLETED,
            Shift.started_at >= r.start_utc,
            Shift.started_at < r.end_utc,
            OperationSession.status != SessionStatus.CANCELLED,
        )
    ).all():
        acc[vehicle].minutes_by_type[str(type_id)] += _minutes(started, ended)
    return tracking.gps_distance_km(db, [s.id for s in shifts])


def _add_driver_cost(db: Session, r: _Range, acc: _Acc) -> Decimal:
    """Settlement earnings and bonuses split by driving minutes; returns unallocated."""
    # Only the in-range part of each earning is allocated, by in-range driving.
    minutes = _shift_minutes(db, r.start_utc, r.end_utc)
    unallocated = ZERO
    ledger = db.scalars(
        select(DriverLedgerEntry).where(
            DriverLedgerEntry.voided_at.is_(None),
            DriverLedgerEntry.entry_type.in_((LedgerEntryType.EARNING, LedgerEntryType.BONUS)),
            or_(
                (DriverLedgerEntry.period_start.is_not(None))
                & (DriverLedgerEntry.period_end >= r.date_from)
                & (DriverLedgerEntry.period_start <= r.date_to),
                (DriverLedgerEntry.period_start.is_(None))
                & (DriverLedgerEntry.occurred_on >= r.date_from)
                & (DriverLedgerEntry.occurred_on <= r.date_to),
            ),
        )
    ).all()
    for entry in ledger:
        p_start = entry.period_start or r.date_from
        p_end = entry.period_end or r.date_to
        in_range = entry.amount * fc.period_share(p_start, p_end, r.date_from, r.date_to)
        if entry.vehicle_id and not entry.period_start:
            acc[entry.vehicle_id].driver_cost += in_range
            continue
        split = _allocate(
            in_range,
            minutes.get(entry.driver_id, {}),
            max(p_start, r.date_from),
            min(p_end, r.date_to),
        )
        if split is None:
            unallocated += in_range
            continue
        for v, amount in split.items():
            acc[v].driver_cost += amount

    # Driver-days on each vehicle not covered by a finalised settlement.
    settled = db.execute(
        select(
            DriverSettlement.driver_id, DriverSettlement.period_start, DriverSettlement.period_end
        ).where(
            DriverSettlement.status == SettlementStatus.FINALIZED,
            DriverSettlement.period_end >= r.date_from,
            DriverSettlement.period_start <= r.date_to,
        )
    ).all()
    for driver_id, per_day in minutes.items():
        for v, day in per_day:
            if not any(d == driver_id and s <= day <= e for d, s, e in settled):
                acc[v].drivers_uncovered.add(driver_id)
    return unallocated


def _add_pending(db: Session, r: _Range, acc: _Acc) -> None:
    """Count records waiting for review (they are excluded from the figures)."""
    queries = (
        select(FuelTransaction.vehicle_id, func.count())
        .where(
            FuelTransaction.status == RecordStatus.SUBMITTED,
            FuelTransaction.occurred_at >= r.start_utc,
            FuelTransaction.occurred_at < r.end_utc,
        )
        .group_by(FuelTransaction.vehicle_id),
        select(Expense.vehicle_id, func.count())
        .where(
            Expense.status == RecordStatus.SUBMITTED,
            Expense.occurred_at >= r.start_utc,
            Expense.occurred_at < r.end_utc,
        )
        .group_by(Expense.vehicle_id),
        select(RevenueEntry.vehicle_id, func.count())
        .where(
            RevenueEntry.status == RecordStatus.SUBMITTED,
            RevenueEntry.occurred_on >= r.date_from,
            RevenueEntry.occurred_on <= r.date_to,
        )
        .group_by(RevenueEntry.vehicle_id),
        select(RideHailingStatement.vehicle_id, func.count())
        .where(
            RideHailingStatement.status == RecordStatus.SUBMITTED,
            RideHailingStatement.period_end >= r.date_from,
            RideHailingStatement.period_start <= r.date_to,
        )
        .group_by(RideHailingStatement.vehicle_id),
    )
    for query in queries:
        for v, count in db.execute(query).all():
            acc[v].pending += count


TOTAL_KEYS = (
    "gross_revenue",
    "platform_fees",
    "fuel_cost",
    "consumables_cost",
    "maintenance_cost",
    "other_expenses",
    "direct_operating_cost",
    "driver_cost",
    "net_operating_profit",
)


def compute(
    db: Session, date_from: date, date_to: date, vehicle_id: uuid.UUID | None = None
) -> tuple[list[dict[str, Any]], dict[str, Decimal]]:
    r = _Range(date_from, date_to)
    acc: _Acc = defaultdict(_VehicleAcc)
    types = {str(t.id): t for t in db.scalars(select(OperationType)).all()}
    _add_revenue(db, r, acc)
    _add_costs(db, r, acc)
    gps = _add_activity(db, r, acc)
    unallocated = _add_driver_cost(db, r, acc)
    _add_pending(db, r, acc)
    unstated = ride_hailing.uncovered_days(db, date_from=date_from, date_to=date_to)

    stmt = select(Vehicle).order_by(Vehicle.internal_code)
    if vehicle_id:
        stmt = stmt.where(Vehicle.id == vehicle_id)
    vehicles = [v for v in db.scalars(stmt).all() if v.is_active or v.id in acc]
    results = [
        _vehicle_result(v, acc[v.id], date_from, date_to, gps, types, unstated.get(v.id, 0))
        for v in vehicles
    ]
    totals: dict[str, Decimal] = dict.fromkeys(TOTAL_KEYS, ZERO)
    for row in results:
        for key in TOTAL_KEYS:
            totals[key] += row[key]
    totals["unallocated_driver_cost"] = fc.money(unallocated)
    return results, totals


def _ratio(amount: Decimal, divisor: float | int) -> Decimal | None:
    if not divisor:
        return None
    return fc.money(amount / Decimal(str(divisor)))


def _vehicle_result(
    vehicle: Vehicle,
    a: _VehicleAcc,
    date_from: date,
    date_to: date,
    gps: dict[uuid.UUID, float],
    types: dict[str, OperationType],
    unstated_days: int,
) -> dict[str, Any]:
    m = fc.money
    gross = m(a.gross)
    fees = m(a.fees)
    direct = m(a.fuel + a.consumables + a.maintenance + a.other_expenses + a.fees)
    driver_cost = m(a.driver_cost)
    net = gross - direct - driver_cost
    odometer_values = [s.odometer_distance_km for s in a.shifts]
    odometer_km = sum(v for v in odometer_values if v is not None)
    missing_odometer = sum(1 for v in odometer_values if v is None)
    gps_km = round(sum(gps.get(s.id, 0.0) for s in a.shifts), 2)
    shift_days = {to_local_date(s.started_at) for s in a.shifts if s.started_at}
    days_without_revenue = len(shift_days - a.revenue_days)

    total_minutes = sum(a.minutes_by_type.values())
    keys = set(a.revenue_by_type) | set(a.minutes_by_type)
    by_type = []
    cost_total = direct + driver_cost
    for key in sorted(keys, key=lambda k: (k == UNTYPED, types[k].sort_order if k in types else 0)):
        minutes = a.minutes_by_type.get(key, 0)
        if total_minutes:
            allocated = m(cost_total * Decimal(minutes) / Decimal(total_minutes))
        else:
            allocated = cost_total if key == UNTYPED else ZERO
        revenue_part = m(a.revenue_by_type.get(key, ZERO))
        op = types.get(key)
        by_type.append(
            {
                "operation_type": {"id": op.id, "name": op.name_ar} if op else None,
                "revenue": revenue_part,
                "allocated_cost": allocated,
                "profit": revenue_part - allocated,
                "session_minutes": minutes,
            }
        )
    if not total_minutes and cost_total and UNTYPED not in keys:
        by_type.append(
            {
                "operation_type": None,
                "revenue": ZERO,
                "allocated_cost": cost_total,
                "profit": -cost_total,
                "session_minutes": 0,
            }
        )

    warnings: list[dict[str, Any]] = []

    def warn(code: str, message: str, count: int | None = None) -> None:
        warnings.append({"code": code, "message": message, "count": count})

    if a.pending:
        warn("PENDING_RECORDS", "سجلات مالية بانتظار الاعتماد وغير محسوبة", a.pending)
    if a.shifts and a.fuel_records == 0:
        warn("NO_FUEL_RECORDS", "المركبة عملت في الفترة ولا توجد سجلات وقود معتمدة")
    if days_without_revenue:
        warn("DAYS_WITHOUT_REVENUE", "أيام تشغيل بدون إيراد مسجل", days_without_revenue)
    if missing_odometer:
        warn(
            "MISSING_ODOMETER",
            "ورديات بدون قراءة عداد نهائية؛ التكلفة/كم غير مكتملة",
            missing_odometer,
        )
    if a.drivers_uncovered:
        warn(
            "DRIVER_COST_INCOMPLETE",
            "سائقون عملوا على المركبة في أيام بدون تسوية نهائية؛ تكلفة السائق غير مكتملة",
            len(a.drivers_uncovered),
        )
    if unstated_days:
        warn("RIDE_HAILING_WITHOUT_STATEMENT", "أيام نقل ذكي بدون كشف منصة", unstated_days)
    warn(
        "MAINTENANCE_FROM_EXPENSES",
        "تكلفة الصيانة محسوبة من مصروفات تصنيفات الصيانة فقط",
    )

    return {
        "vehicle": {"id": vehicle.id, "name": vehicle.internal_code},
        "date_from": date_from,
        "date_to": date_to,
        "gross_revenue": gross,
        "platform_fees": fees,
        "fuel_by_type": {k: m(v) for k, v in a.fuel_by_type.items()},
        "fuel_cost": m(a.fuel),
        "consumables_cost": m(a.consumables),
        "maintenance_cost": m(a.maintenance),
        "expenses_by_group": {k: m(v) for k, v in a.expenses_by_group.items()},
        "other_expenses": m(a.other_expenses),
        "direct_operating_cost": direct,
        "driver_cost": driver_cost,
        "net_operating_profit": net,
        "shifts_count": len(a.shifts),
        "odometer_km": odometer_km,
        "gps_km": gps_km,
        "cost_per_km": _ratio(direct + driver_cost, odometer_km),
        "revenue_per_km": _ratio(gross, odometer_km),
        "profit_per_shift": _ratio(net, len(a.shifts)),
        "by_operation_type": by_type,
        "warnings": warnings,
    }
