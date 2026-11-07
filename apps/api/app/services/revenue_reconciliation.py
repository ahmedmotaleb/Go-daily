"""Revenue reconciliation (U18): one view of every revenue source per vehicle.

For a date range and each vehicle it brings together:

- fixed routes: expected from detected loops (U10) vs recorded collection;
- ride-hailing: approved platform statements (gross, commission, net, cash
  paid by riders, electronic payout), spread over the range by days;
- private trips and other entries as recorded;
- school / employee contracts spread over their service period by days;
- approved corrections (adjustments) and what is still waiting for review.

Nothing is double counted: ride-hailing revenue is taken from statements
only (a statement produces at most one live revenue entry), and every
check that could reveal double counting or a gap is reported as a
completeness warning, never silently fixed or estimated.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cash import ShiftCloseout
from app.models.finance import (
    RecordStatus,
    RevenueEntry,
    RevenueKind,
    RideHailingStatement,
)
from app.models.fleet import Vehicle
from app.models.operations import OperationKind
from app.models.shift import Shift
from app.services import expected_revenue, ride_hailing
from app.services import finance_common as fc
from app.services.expected_revenue import CollectionStatus

ZERO = Decimal("0")
type _Get = Callable[[uuid.UUID], "VehicleRevenue"]
LIVE = (RecordStatus.SUBMITTED, RecordStatus.APPROVED)
# Driver-reported ride-hailing cash vs statement cash: allowed difference.
CASH_TOLERANCE_AMOUNT = Decimal("50")
CASH_TOLERANCE_PCT = Decimal("10")

WARNING_AR = {
    "FIXED_ROUTE_SHORTFALL": "أيام بفرق تحصيل عن المتوقع — مراجعة مطلوبة",
    "FIXED_ROUTE_NO_COLLECTION": "أيام دورات بدون تحصيل مسجل",
    "FIXED_ROUTE_NO_RATE": "أيام دورات بدون سعر متوقع للمسار",
    "COLLECTION_WITHOUT_LOOPS": "أيام تحصيل بدون دورات مسجلة",
    "RIDE_HAILING_WITHOUT_STATEMENT": "أيام نقل ذكي بدون كشف منصة",
    "STATEMENT_WITHOUT_REVENUE": "كشوف معتمدة بدون إيراد مسجل",
    "RIDE_HAILING_REVENUE_WITHOUT_STATEMENT": "إيراد نقل ذكي غير مرتبط بكشف معتمد",
    "POSSIBLE_DUPLICATE": "إيرادات متطابقة في نفس اليوم — احتمال تكرار",
    "PENDING_REVIEW": "إيرادات بانتظار المراجعة",
    "RIDE_HAILING_CASH_DIFFERENCE": "فرق بين نقدية النقل الذكي في التقفيلات والكشوف",
}


@dataclass
class Warning:
    code: str
    count: int
    amount: Decimal | None = None

    @property
    def message(self) -> str:
        return WARNING_AR[self.code]


@dataclass
class VehicleRevenue:
    vehicle_id: uuid.UUID
    vehicle_code: str
    plate_number: str
    fixed_expected: Decimal | None = ZERO
    fixed_recorded: Decimal = ZERO
    fixed_days: int = 0
    ride_income: Decimal = ZERO
    ride_commission: Decimal = ZERO
    ride_cash: Decimal = ZERO
    ride_electronic: Decimal = ZERO
    ride_closeout_cash: Decimal = ZERO
    private_trips: Decimal = ZERO
    contracts: Decimal = ZERO
    other: Decimal = ZERO
    # Fixed-route collection still waiting for review (shown, not recognized).
    fixed_pending: Decimal = ZERO
    adjustments: int = 0
    adjustments_change: Decimal = ZERO
    pending_review: Decimal = ZERO
    warnings: list[Warning] = field(default_factory=list)

    @property
    def ride_net(self) -> Decimal:
        return self.ride_income - self.ride_commission

    @property
    def recognized(self) -> Decimal:
        """Approved revenue in the range, net of platform commission (no double counting)."""
        approved_fixed = self.fixed_recorded - self.fixed_pending
        return fc.money(
            approved_fixed + self.ride_net + self.private_trips + self.contracts + self.other
        )

    def warn(self, code: str, count: int, amount: Decimal | None = None) -> None:
        if count:
            self.warnings.append(Warning(code, count, fc.money(amount) if amount else None))


@dataclass
class Reconciliation:
    date_from: date
    date_to: date
    vehicles: list[VehicleRevenue]

    @property
    def warnings(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for v in self.vehicles:
            for w in v.warnings:
                out[w.code] += w.count
        return dict(out)


def _vehicle(
    acc: dict[uuid.UUID, VehicleRevenue], vehicles: dict[uuid.UUID, Vehicle], vid: uuid.UUID
) -> VehicleRevenue:
    if vid not in acc:
        v = vehicles[vid]
        acc[vid] = VehicleRevenue(vid, v.internal_code, v.plate_number)
    return acc[vid]


def _fixed_routes(db: Session, f: date, t: date, vehicle_id: uuid.UUID | None, get: _Get) -> None:
    counts: dict[uuid.UUID, dict[CollectionStatus, int]] = defaultdict(lambda: defaultdict(int))
    for row in expected_revenue.compare(db, f, t, vehicle_id=vehicle_id):
        v = get(row.vehicle_id)
        v.fixed_days += 1
        if row.expected is None or v.fixed_expected is None:
            v.fixed_expected = None if row.expected is None else v.fixed_expected
        else:
            v.fixed_expected += row.expected
        v.fixed_recorded += row.recorded
        v.fixed_pending += row.pending
        counts[row.vehicle_id][row.status] += 1
        if (
            row.loops + row.legs > 0
            and row.recorded == 0
            and row.status is not CollectionStatus.DAY_OPEN
        ):
            v.warn("FIXED_ROUTE_NO_COLLECTION", 1)
    for vid, c in counts.items():
        v = get(vid)
        v.warn("FIXED_ROUTE_SHORTFALL", c[CollectionStatus.SHORTFALL])
        v.warn("FIXED_ROUTE_NO_RATE", c[CollectionStatus.NO_RATE])
        v.warn("COLLECTION_WITHOUT_LOOPS", c[CollectionStatus.NO_LOOPS])


def _ride_hailing(db: Session, f: date, t: date, vehicle_id: uuid.UUID | None, get: _Get) -> None:
    stmt = select(RideHailingStatement).where(
        RideHailingStatement.status == RecordStatus.APPROVED,
        RideHailingStatement.period_end >= f,
        RideHailingStatement.period_start <= t,
    )
    if vehicle_id:
        stmt = stmt.where(RideHailingStatement.vehicle_id == vehicle_id)
    statements = db.scalars(stmt).all()
    with_revenue = ride_hailing.revenue_ids(db, [s.id for s in statements])
    missing: dict[uuid.UUID, int] = defaultdict(int)
    for s in statements:
        share = fc.period_share(s.period_start, s.period_end, f, t)
        v = get(s.vehicle_id)
        v.ride_income += s.income * share
        v.ride_commission += s.platform_fees * share
        v.ride_cash += s.cash_collected * share
        v.ride_electronic += max(s.platform_payout, ZERO) * share
        if s.id not in with_revenue:
            missing[s.vehicle_id] += 1
    for vid, n in missing.items():
        get(vid).warn("STATEMENT_WITHOUT_REVENUE", n)
    for vid, days in ride_hailing.uncovered_days(db, date_from=f, date_to=t).items():
        if vehicle_id is None or vid == vehicle_id:
            get(vid).warn("RIDE_HAILING_WITHOUT_STATEMENT", days)


def _add_approved(v: VehicleRevenue, e: RevenueEntry, f: date, t: date) -> None:
    """Approved non-platform revenue; service periods are spread over the range by days."""
    # Contracts always carry a service period (the API requires it).
    if e.period_start and e.period_end:
        share = fc.period_share(e.period_start, e.period_end, f, t)
    else:
        share = Decimal(1)
    amount = e.amount * share
    if e.kind is RevenueKind.PRIVATE_TRIP:
        v.private_trips += amount
    elif e.kind is RevenueKind.CONTRACT_SERVICE:
        v.contracts += amount
    else:
        v.other += amount


def _entries(db: Session, f: date, t: date, vehicle_id: uuid.UUID | None, get: _Get) -> None:
    stmt = select(RevenueEntry).where(
        RevenueEntry.status.in_(LIVE),
        func.coalesce(RevenueEntry.period_end, RevenueEntry.occurred_on) >= f,
        func.coalesce(RevenueEntry.period_start, RevenueEntry.occurred_on) <= t,
    )
    if vehicle_id:
        stmt = stmt.where(RevenueEntry.vehicle_id == vehicle_id)
    entries = db.scalars(stmt).all()
    approved_statements = set(
        db.scalars(
            select(RideHailingStatement.id).where(
                RideHailingStatement.status == RecordStatus.APPROVED
            )
        ).all()
    )
    seen: dict[tuple[uuid.UUID, RevenueKind, date, Decimal], int] = defaultdict(int)
    corrected_ids = [e.corrects_id for e in entries if e.corrects_id]
    originals = (
        {
            e.id: e
            for e in db.scalars(
                select(RevenueEntry).where(RevenueEntry.id.in_(corrected_ids))
            ).all()
        }
        if corrected_ids
        else {}
    )
    for e in entries:
        v = get(e.vehicle_id)
        if e.kind is RevenueKind.RIDE_HAILING:
            # Counted from the statement; flag any entry not backed by an approved one.
            if e.statement_id is None or e.statement_id not in approved_statements:
                v.warn("RIDE_HAILING_REVENUE_WITHOUT_STATEMENT", 1, e.amount)
            continue
        seen[(e.vehicle_id, e.kind, e.occurred_on, e.amount)] += 1
        if e.kind is RevenueKind.FIXED_ROUTE_COLLECTION:
            continue  # counted through the fixed-route comparison
        if e.status is RecordStatus.SUBMITTED:
            v.pending_review += e.amount
            continue
        _add_approved(v, e, f, t)
        if e.corrects_id and e.corrects_id in originals:
            v.adjustments += 1
            v.adjustments_change += e.amount - originals[e.corrects_id].amount
    dupes: dict[uuid.UUID, int] = defaultdict(int)
    for (vid, _kind, _day, _amount), n in seen.items():
        if n > 1:
            dupes[vid] += n
    for vid, n in dupes.items():
        get(vid).warn("POSSIBLE_DUPLICATE", n)


def _ride_hailing_closeouts(
    db: Session, f: date, t: date, vehicle_id: uuid.UUID | None, get: _Get
) -> None:
    """Cash drivers declared on ride-hailing close-outs vs what statements say."""
    stmt = (
        select(ShiftCloseout, Shift)
        .join(Shift, Shift.id == ShiftCloseout.shift_id)
        .where(
            ShiftCloseout.voided_at.is_(None),
            ShiftCloseout.revenue_entry_id.is_(None),
            ShiftCloseout.collection_amount > 0,
            ShiftCloseout.service_date >= f,
            ShiftCloseout.service_date <= t,
        )
    )
    if vehicle_id:
        stmt = stmt.where(ShiftCloseout.vehicle_id == vehicle_id)
    for closeout, shift in db.execute(stmt).all():
        kinds = {s.operation_type.kind for s in shift.sessions}
        if OperationKind.RIDE_HAILING in kinds:
            get(closeout.vehicle_id).ride_closeout_cash += closeout.collection_amount


def reconcile(
    db: Session, date_from: date, date_to: date, *, vehicle_id: uuid.UUID | None = None
) -> Reconciliation:
    vehicles = {v.id: v for v in db.scalars(select(Vehicle)).all()}
    acc: dict[uuid.UUID, VehicleRevenue] = {}

    def get(vid: uuid.UUID) -> VehicleRevenue:
        return _vehicle(acc, vehicles, vid)

    _fixed_routes(db, date_from, date_to, vehicle_id, get)
    _ride_hailing(db, date_from, date_to, vehicle_id, get)
    _entries(db, date_from, date_to, vehicle_id, get)
    _ride_hailing_closeouts(db, date_from, date_to, vehicle_id, get)
    for v in acc.values():
        waiting = v.pending_review + v.fixed_pending
        v.warn("PENDING_REVIEW", int(waiting > 0), waiting)
        if v.ride_closeout_cash > 0 and v.ride_cash > 0:
            diff = abs(v.ride_closeout_cash - v.ride_cash)
            allowed = max(CASH_TOLERANCE_AMOUNT, v.ride_cash * CASH_TOLERANCE_PCT / 100)
            if diff > allowed:
                v.warn("RIDE_HAILING_CASH_DIFFERENCE", 1, diff)
        for name in (
            "fixed_recorded",
            "ride_income",
            "ride_commission",
            "ride_cash",
            "ride_electronic",
            "ride_closeout_cash",
            "private_trips",
            "contracts",
            "other",
            "adjustments_change",
            "pending_review",
            "fixed_pending",
        ):
            setattr(v, name, fc.money(getattr(v, name)))
        if v.fixed_expected is not None:
            v.fixed_expected = fc.money(v.fixed_expected)
    rows = sorted(acc.values(), key=lambda v: v.vehicle_code)
    return Reconciliation(date_from, date_to, rows)


__all__ = ["WARNING_AR", "Reconciliation", "VehicleRevenue", "Warning", "reconcile"]
