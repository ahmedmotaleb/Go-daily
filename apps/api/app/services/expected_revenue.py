"""Expected collection from detected loops vs recorded collection (U10).

Expected revenue comes from the loops/legs detected on fixed routes
(including audited manual corrections) and the route's revenue rate that
applied on that day. Actual collection is what was recorded as fixed-route
collection for the same vehicle and day. A shortfall beyond the tolerance
is "فرق تحصيل — مراجعة مطلوبة": a reason to check, never an accusation.

Money is Decimal throughout and rounded to piastres only for display.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.time import local_day_bounds_utc, local_today, to_local_date
from app.models.finance import (
    ExpectedRevenueModel,
    RecordStatus,
    RevenueEntry,
    RevenueKind,
    RouteRevenueRate,
)
from app.models.operations import OperationKind, RouteDefinition, TripPattern
from app.models.shift import OperationSession, SessionStatus
from app.models.user import User
from app.schemas.expected_revenue import RateCreate
from app.services import audit, route_events
from app.services import finance_common as fc

ZERO = Decimal("0")
SHORTFALL_LABEL = "فرق تحصيل — مراجعة مطلوبة"


class CollectionStatus(StrEnum):
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"  # مطابق للمتوقع
    SHORTFALL = "SHORTFALL"  # فرق تحصيل — مراجعة مطلوبة
    ABOVE_EXPECTED = "ABOVE_EXPECTED"  # أعلى من المتوقع
    NO_RATE = "NO_RATE"  # لا يوجد سعر متوقع للمسار
    NO_LOOPS = "NO_LOOPS"  # تحصيل بدون دورات مسجلة
    DAY_OPEN = "DAY_OPEN"  # اليوم لم ينتهِ بعد


STATUS_AR: dict[CollectionStatus, str] = {
    CollectionStatus.WITHIN_TOLERANCE: "مطابق للمتوقع",
    CollectionStatus.SHORTFALL: SHORTFALL_LABEL,
    CollectionStatus.ABOVE_EXPECTED: "أعلى من المتوقع",
    CollectionStatus.NO_RATE: "لا يوجد سعر متوقع للمسار",
    CollectionStatus.NO_LOOPS: "تحصيل بدون دورات مسجلة",
    CollectionStatus.DAY_OPEN: "اليوم لم ينتهِ بعد",
}


# --- Rates ----------------------------------------------------------------------


def _route(db: Session, route_id: uuid.UUID, *, lock: bool = False) -> RouteDefinition:
    stmt = select(RouteDefinition).where(RouteDefinition.id == route_id)
    if lock:
        stmt = stmt.with_for_update(of=RouteDefinition)
    route = db.scalars(stmt).first()
    if route is None:
        raise NotFoundError("المسار غير موجود")
    return route


def list_rates(db: Session, route_id: uuid.UUID) -> list[RouteRevenueRate]:
    _route(db, route_id)
    return list(
        db.scalars(
            select(RouteRevenueRate)
            .where(RouteRevenueRate.route_id == route_id)
            .order_by(RouteRevenueRate.effective_from.desc())
        ).all()
    )


def add_rate(
    db: Session, *, actor: User, route_id: uuid.UUID, data: RateCreate
) -> RouteRevenueRate:
    """Start a new rate. The open rate is closed the day before; history is never edited."""
    route = _route(db, route_id, lock=True)
    if data.model is ExpectedRevenueModel.PER_LOOP and route.trip_pattern != TripPattern.ROUND_TRIP:
        raise ValidationFailed(
            "مسار الاتجاه الواحد لا يكتمل فيه دوران؛ استخدم السعر لكل اتجاه",
            code="per_loop_needs_round_trip",
        )
    latest = db.scalar(
        select(RouteRevenueRate)
        .where(RouteRevenueRate.route_id == route_id)
        .order_by(RouteRevenueRate.effective_from.desc())
        .limit(1)
        .with_for_update()
    )
    if latest is not None:
        if data.effective_from <= latest.effective_from:
            raise ConflictError(
                "تاريخ بداية السعر الجديد يجب أن يكون بعد بداية السعر الحالي",
                code="rate_effective_date_conflict",
            )
        if latest.effective_to is None or latest.effective_to >= data.effective_from:
            old_to = latest.effective_to
            latest.effective_to = data.effective_from - timedelta(days=1)
            audit.record(
                db,
                action="route_revenue_rate.closed",
                actor=actor,
                entity_type="route_revenue_rate",
                entity_id=latest.id,
                changes={
                    "effective_to": {
                        "old": audit.to_jsonable(old_to),
                        "new": latest.effective_to.isoformat(),
                    }
                },
            )
    rate = RouteRevenueRate(
        route_id=route_id,
        model=data.model,
        amount_per_loop=data.amount_per_loop
        if data.model is ExpectedRevenueModel.PER_LOOP
        else None,
        amount_per_leg=data.amount_per_leg if data.model is ExpectedRevenueModel.PER_LEG else None,
        fare=data.fare if data.model is ExpectedRevenueModel.PASSENGERS_X_FARE else None,
        passengers_per_leg=(
            data.passengers_per_leg
            if data.model is ExpectedRevenueModel.PASSENGERS_X_FARE
            else None
        ),
        effective_from=data.effective_from,
        notes=data.notes,
        created_by_id=actor.id,
    )
    db.add(rate)
    db.flush()
    audit.record(
        db,
        action="route_revenue_rate.created",
        actor=actor,
        entity_type="route_revenue_rate",
        entity_id=rate.id,
        changes=audit.diff(
            {},
            audit.snapshot(
                rate,
                (
                    "route_id",
                    "model",
                    "amount_per_loop",
                    "amount_per_leg",
                    "fare",
                    "passengers_per_leg",
                    "effective_from",
                ),
            ),
        ),
    )
    db.commit()
    return rate


def expected_amount(rate: RouteRevenueRate, *, loops: int, legs: int) -> Decimal:
    if rate.model is ExpectedRevenueModel.PER_LOOP:
        return Decimal(loops) * (rate.amount_per_loop or ZERO)
    if rate.model is ExpectedRevenueModel.PER_LEG:
        return Decimal(legs) * (rate.amount_per_leg or ZERO)
    return Decimal(legs * (rate.passengers_per_leg or 0)) * (rate.fare or ZERO)


def _rate_on(rates: list[RouteRevenueRate], day: date) -> RouteRevenueRate | None:
    for r in rates:
        if r.effective_from <= day and (r.effective_to is None or r.effective_to >= day):
            return r
    return None


# --- Expected vs actual -------------------------------------------------------------


@dataclass
class DayCollection:
    day: date
    vehicle_id: uuid.UUID
    vehicle_code: str
    routes: list[str] = field(default_factory=list)
    loops: int = 0
    legs: int = 0
    expected: Decimal | None = ZERO
    approved: Decimal = ZERO
    pending: Decimal = ZERO
    difference: Decimal | None = None
    difference_pct: Decimal | None = None
    allowed: Decimal | None = None
    status: CollectionStatus = CollectionStatus.WITHIN_TOLERANCE
    missing_rate_routes: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)

    @property
    def recorded(self) -> Decimal:
        """Approved and submitted collection (pending entries are records too)."""
        return self.approved + self.pending


def _classify(row: DayCollection, today: date) -> None:
    s = get_settings()
    if row.missing_rate_routes:
        row.expected = None
        row.status = CollectionStatus.NO_RATE
        return
    expected = row.expected or ZERO
    row.difference = fc.money(row.recorded - expected)
    row.allowed = fc.money(
        max(s.collection_tolerance_amount, expected * s.collection_tolerance_pct / 100)
    )
    row.difference_pct = (
        (row.difference * 100 / expected).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if expected > 0
        else None
    )
    if expected == 0 and row.recorded > 0:
        row.status = CollectionStatus.NO_LOOPS
    elif row.difference < -row.allowed:
        row.status = CollectionStatus.DAY_OPEN if row.day >= today else CollectionStatus.SHORTFALL
    elif row.difference > row.allowed:
        row.status = CollectionStatus.ABOVE_EXPECTED
    else:
        row.status = CollectionStatus.WITHIN_TOLERANCE


Rows = dict[tuple[uuid.UUID, date], DayCollection]


def _row(rows: Rows, vehicle_id: uuid.UUID, code: str, day: date) -> DayCollection:
    key = (vehicle_id, day)
    if key not in rows:
        rows[key] = DayCollection(day=day, vehicle_id=vehicle_id, vehicle_code=code)
    return rows[key]


def _sessions(
    db: Session,
    start: datetime,
    end: datetime,
    vehicle_id: uuid.UUID | None,
    route_id: uuid.UUID | None,
) -> list[OperationSession]:
    stmt = select(OperationSession).where(
        OperationSession.route_id.is_not(None),
        OperationSession.status != SessionStatus.CANCELLED,
        OperationSession.started_at >= start,
        OperationSession.started_at < end,
    )
    if route_id:
        stmt = stmt.where(OperationSession.route_id == route_id)
    return [
        s
        for s in db.scalars(stmt.order_by(OperationSession.started_at)).all()
        if s.route is not None and (vehicle_id is None or s.shift.vehicle_id == vehicle_id)
    ]


def _rates(
    db: Session, route_ids: set[uuid.UUID], date_from: date, date_to: date
) -> dict[uuid.UUID, list[RouteRevenueRate]]:
    rates: dict[uuid.UUID, list[RouteRevenueRate]] = defaultdict(list)
    if not route_ids:
        return rates
    for r in db.scalars(
        select(RouteRevenueRate)
        .where(
            RouteRevenueRate.route_id.in_(route_ids),
            RouteRevenueRate.effective_from <= date_to,
            or_(
                RouteRevenueRate.effective_to.is_(None),
                RouteRevenueRate.effective_to >= date_from,
            ),
        )
        .order_by(RouteRevenueRate.effective_from)
    ):
        rates[r.route_id].append(r)
    return rates


def _add_expected(
    rows: Rows,
    sessions: list[OperationSession],
    rates: dict[uuid.UUID, list[RouteRevenueRate]],
    counts: dict[uuid.UUID, dict[str, int]],
) -> None:
    for s in sessions:
        route = s.route
        assert route is not None  # noqa: S101 - filtered in _sessions
        day = to_local_date(s.started_at)
        rate = _rate_on(rates.get(route.id, []), day)
        if rate is None and route.operation_type.kind is not OperationKind.FIXED_ROUTE:
            continue  # e.g. a school route paid by contract, with no per-loop rate
        row = _row(rows, s.shift.vehicle_id, s.shift.vehicle.internal_code, day)
        if route.name not in row.routes:
            row.routes.append(route.name)
        loops = counts.get(s.id, {}).get("loops", 0)
        legs = counts.get(s.id, {}).get("legs", 0)
        row.loops += loops
        row.legs += legs
        if rate is None:
            if route.name not in row.missing_rate_routes:
                row.missing_rate_routes.append(route.name)
            continue
        if rate.model.value not in row.models:
            row.models.append(rate.model.value)
        row.expected = (row.expected or ZERO) + expected_amount(rate, loops=loops, legs=legs)


def _add_collections(
    db: Session,
    rows: Rows,
    date_from: date,
    date_to: date,
    vehicle_id: uuid.UUID | None,
    route_id: uuid.UUID | None,
) -> None:
    stmt = select(RevenueEntry).where(
        RevenueEntry.kind == RevenueKind.FIXED_ROUTE_COLLECTION,
        RevenueEntry.status.in_((RecordStatus.SUBMITTED, RecordStatus.APPROVED)),
        RevenueEntry.occurred_on >= date_from,
        RevenueEntry.occurred_on <= date_to,
    )
    if vehicle_id:
        stmt = stmt.where(RevenueEntry.vehicle_id == vehicle_id)
    for e in db.scalars(stmt).all():
        if route_id and (e.vehicle_id, e.occurred_on) not in rows:
            continue  # filtering by route: only the days that route ran
        row = _row(rows, e.vehicle_id, e.vehicle.internal_code, e.occurred_on)
        if e.status is RecordStatus.APPROVED:
            row.approved += e.amount
        else:
            row.pending += e.amount


def compare(
    db: Session,
    date_from: date,
    date_to: date,
    *,
    vehicle_id: uuid.UUID | None = None,
    route_id: uuid.UUID | None = None,
) -> list[DayCollection]:
    """One row per vehicle and day with fixed-route sessions or fixed-route collections."""
    start, end = local_day_bounds_utc(date_from)[0], local_day_bounds_utc(date_to)[1]
    sessions = _sessions(db, start, end, vehicle_id, route_id)
    rates = _rates(db, {s.route_id for s in sessions if s.route_id}, date_from, date_to)
    rows: Rows = {}
    _add_expected(rows, sessions, rates, route_events.counts(db, [s.id for s in sessions]))
    _add_collections(db, rows, date_from, date_to, vehicle_id, route_id)
    today = local_today()
    for row in rows.values():
        row.expected = fc.money(row.expected) if row.expected is not None else None
        row.approved, row.pending = fc.money(row.approved), fc.money(row.pending)
        _classify(row, today)
    return sorted(rows.values(), key=lambda r: (r.day, r.vehicle_code))


__all__ = [
    "STATUS_AR",
    "CollectionStatus",
    "DayCollection",
    "add_rate",
    "compare",
    "expected_amount",
    "list_rates",
]
