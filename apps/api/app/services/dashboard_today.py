"""Today's operations and money overview for the dashboard (design: لوحة التشغيل).

Everything is computed from recorded data; nothing is estimated. Money is
split into approved and pending so the dashboard never presents records
waiting for review as final, and money is only returned to users allowed
to see it (the route decides).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import local_day_bounds_utc, local_today, to_local_date, utcnow
from app.models.finance import Expense, FuelTransaction, RecordStatus, RevenueEntry
from app.models.operations import OperationKind, OperationType
from app.models.route_events import SchoolRun, SchoolRunStatus
from app.models.shift import OperationSession, SessionStatus, Shift, ShiftStatus
from app.services import expected_revenue, route_events
from app.services import finance_common as fc

ZERO = Decimal("0")
LIVE = (RecordStatus.SUBMITTED, RecordStatus.APPROVED)
DONE_RUNS = (SchoolRunStatus.COMPLETED, SchoolRunStatus.COMPLETED_LATE)


@dataclass
class Money:
    approved: Decimal = ZERO
    pending: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return self.approved + self.pending


@dataclass
class OperationToday:
    kind: OperationKind
    name_ar: str
    vehicles: int = 0
    active_sessions: int = 0
    sessions_today: int = 0
    activity_label: str = ""
    activity_value: str = ""
    # 0-100 when there is a real reference (expected collection, scheduled runs).
    progress_pct: int | None = None
    note: str | None = None
    note_is_warning: bool = False
    collection: Decimal | None = None


@dataclass
class DayFigures:
    day: date
    revenue: Decimal = ZERO
    expenses: Decimal = ZERO


@dataclass
class TodayOverview:
    oldest_shift_started_at: datetime | None
    revenue: Money | None = None
    fuel: Money | None = None
    other_expenses: Money | None = None
    week: list[DayFigures] = field(default_factory=list)
    operations: list[OperationToday] = field(default_factory=list)


def _money(db: Session, status: Any, amount: Any, when: Any, start: Any, end: Any) -> Money:
    """Approved and pending totals of one kind of record between start and end."""
    rows = db.execute(
        select(status, func.coalesce(func.sum(amount), 0))
        .where(status.in_(LIVE), when >= start, when < end)
        .group_by(status)
    ).all()
    out = Money()
    for state, total in rows:
        if state is RecordStatus.APPROVED:
            out.approved += Decimal(total)
        else:
            out.pending += Decimal(total)
    out.approved, out.pending = fc.money(out.approved), fc.money(out.pending)
    return out


def _week(db: Session, today: date) -> list[DayFigures]:
    first = today - timedelta(days=6)
    days = {first + timedelta(days=i): DayFigures(first + timedelta(days=i)) for i in range(7)}
    for day, total in db.execute(
        select(RevenueEntry.occurred_on, func.sum(RevenueEntry.amount))
        .where(
            RevenueEntry.status.in_(LIVE),
            RevenueEntry.occurred_on >= first,
            RevenueEntry.occurred_on <= today,
        )
        .group_by(RevenueEntry.occurred_on)
    ).all():
        days[day].revenue += Decimal(total)
    start, end = local_day_bounds_utc(first)[0], local_day_bounds_utc(today)[1]
    sources: tuple[tuple[Any, Any, Any], ...] = (
        (FuelTransaction.status, FuelTransaction.total_amount, FuelTransaction.occurred_at),
        (Expense.status, Expense.amount, Expense.occurred_at),
    )
    for status, amount, when in sources:
        for at, value in db.execute(
            select(when, amount).where(status.in_(LIVE), when >= start, when < end)
        ).all():
            days[to_local_date(at)].expenses += Decimal(value)
    for d in days.values():
        d.revenue, d.expenses = fc.money(d.revenue), fc.money(d.expenses)
    return [days[k] for k in sorted(days)]


def _hours(minutes: float) -> str:
    whole = int(minutes)
    return f"{whole // 60}:{whole % 60:02d}"


Counts = dict[Any, dict[str, int]]


def _fixed_route(
    db: Session,
    op: OperationToday,
    items: list[OperationSession],
    counts: Counts,
    today: date,
    with_money: bool,
) -> None:
    op.activity_label = "لفات مكتملة"
    op.activity_value = str(sum(counts.get(s.id, {}).get("loops", 0) for s in items))
    if not with_money:
        return
    rows = expected_revenue.compare(db, today, today)
    expected = sum((r.expected or ZERO for r in rows), ZERO)
    recorded = sum((r.recorded for r in rows), ZERO)
    if expected > 0:
        op.progress_pct = min(100, int(recorded * 100 / expected))
        op.note = f"المسجّل {fc.money(recorded)} من المتوقع {fc.money(expected)} ج.م"
        op.note_is_warning = recorded < expected


def _school(
    db: Session,
    op: OperationToday,
    items: list[OperationSession],
    counts: Counts,
    today: date,
    with_money: bool,
) -> None:
    runs = db.scalars(select(SchoolRun).where(SchoolRun.service_date == today)).all()
    planned = [r for r in runs if r.status is not SchoolRunStatus.CANCELLED]
    done = [r for r in planned if r.status in DONE_RUNS]
    op.activity_label = "دورات اليوم"
    op.activity_value = f"{len(done)} / {len(planned)}"
    if planned:
        op.progress_pct = int(len(done) * 100 / len(planned))
    late = sum(1 for r in planned if r.status is SchoolRunStatus.COMPLETED_LATE)
    needs = sum(
        1
        for r in planned
        if r.status in (SchoolRunStatus.INCOMPLETE, SchoolRunStatus.COMPLETED_UNVERIFIED)
    )
    parts = ([f"{late} بتأخير"] if late else []) + ([f"{needs} تحتاج مراجعة"] if needs else [])
    if parts:
        op.note = "، ".join(parts)
        op.note_is_warning = True


def _ride_hailing(
    db: Session,
    op: OperationToday,
    items: list[OperationSession],
    counts: Counts,
    today: date,
    with_money: bool,
) -> None:
    start = local_day_bounds_utc(today)[0]
    now = utcnow()
    minutes = sum(
        ((s.ended_at or now) - max(s.started_at, start)).total_seconds() / 60 for s in items
    )
    op.activity_label = "ساعات التشغيل"
    op.activity_value = _hours(minutes)


def _other(
    db: Session,
    op: OperationToday,
    items: list[OperationSession],
    counts: Counts,
    today: date,
    with_money: bool,
) -> None:
    op.activity_label = "تشغيلات اليوم"
    op.activity_value = str(len(items))


_ACTIVITY = {
    OperationKind.FIXED_ROUTE: _fixed_route,
    OperationKind.SCHOOL_ROUTE: _school,
    OperationKind.RIDE_HAILING: _ride_hailing,
}


def _operations(db: Session, today: date, *, with_money: bool) -> list[OperationToday]:
    start, end = local_day_bounds_utc(today)
    sessions = db.scalars(
        select(OperationSession).where(
            OperationSession.status != SessionStatus.CANCELLED,
            OperationSession.started_at >= start,
            OperationSession.started_at < end,
        )
    ).all()
    # Sessions started before today but still running count as today's work too.
    sessions = list(sessions) + list(
        db.scalars(
            select(OperationSession).where(
                OperationSession.status == SessionStatus.ACTIVE,
                OperationSession.started_at < start,
            )
        ).all()
    )
    by_kind: dict[OperationKind, list[OperationSession]] = defaultdict(list)
    for s in sessions:
        by_kind[s.operation_type.kind].append(s)
    names = {t.kind: t.name_ar for t in db.scalars(select(OperationType)).all()}
    counts = route_events.counts(db, [s.id for s in sessions])
    collection: dict[OperationKind, Decimal] = defaultdict(lambda: ZERO)
    if with_money:
        for kind, total in db.execute(
            select(OperationType.kind, func.sum(RevenueEntry.amount))
            .join(OperationType, OperationType.id == RevenueEntry.operation_type_id)
            .where(RevenueEntry.status.in_(LIVE), RevenueEntry.occurred_on == today)
            .group_by(OperationType.kind)
        ).all():
            collection[kind] += Decimal(total)

    out: list[OperationToday] = []
    for kind, items in sorted(by_kind.items(), key=lambda kv: kv[0].value):
        op = OperationToday(
            kind=kind,
            name_ar=names.get(kind, kind.value),
            vehicles=len({s.shift.vehicle_id for s in items}),
            active_sessions=sum(1 for s in items if s.status is SessionStatus.ACTIVE),
            sessions_today=len(items),
            collection=fc.money(collection[kind]) if with_money else None,
        )
        _ACTIVITY.get(kind, _other)(db, op, items, counts, today, with_money)
        if op.note is None:
            op.note = (
                f"{op.active_sessions} تشغيل جارٍ الآن"
                if op.active_sessions
                else "لا تشغيل جارٍ الآن"
            )
        out.append(op)
    return out


def overview(db: Session, *, with_money: bool, with_expenses: bool) -> TodayOverview:
    today = local_today()
    start, end = local_day_bounds_utc(today)
    oldest = db.scalar(select(func.min(Shift.started_at)).where(Shift.status == ShiftStatus.ACTIVE))
    result = TodayOverview(oldest_shift_started_at=oldest)
    if with_money:
        result.revenue = _money(
            db,
            RevenueEntry.status,
            RevenueEntry.amount,
            RevenueEntry.occurred_on,
            today,
            today + timedelta(days=1),
        )
    if with_expenses:
        result.fuel = _money(
            db,
            FuelTransaction.status,
            FuelTransaction.total_amount,
            FuelTransaction.occurred_at,
            start,
            end,
        )
        result.other_expenses = _money(
            db, Expense.status, Expense.amount, Expense.occurred_at, start, end
        )
    if with_money and with_expenses:
        result.week = _week(db, today)
    result.operations = _operations(db, today, with_money=with_money)
    return result


__all__ = ["DayFigures", "Money", "OperationToday", "TodayOverview", "overview"]
