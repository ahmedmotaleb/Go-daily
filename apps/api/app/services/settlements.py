"""Driver settlements (Task 18).

A settlement computes compensation for a period from the plan(s) in force
(plans are versioned and never edited). Finalising freezes the calculation
in `details` and posts one EARNING entry to the driver account, so later
plan or data changes never alter a historical settlement. A finalised
settlement can only be voided (with a reason) and redone.

Compensation rules:
- FIXED_MONTHLY: monthly amount pro-rated by calendar days of each month.
- DAILY_WAGE: wage x local days with a completed shift.
- REVENUE_PERCENTAGE: % of eligible revenue = approved revenue attributed
  to the driver, net of platform fees; amounts with a service period are
  spread over it by days.
- FIXED_PLUS_INCENTIVE: pro-rated fixed amount + incentive % of eligible
  revenue above the (monthly, pro-rated) threshold.
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, field_error
from app.core.time import local_day_bounds_utc, to_local_date, utcnow
from app.models.driver import CompensationMethod, Driver, DriverCompensationPlan
from app.models.finance import (
    DriverSettlement,
    LedgerEntryType,
    LedgerSource,
    RecordStatus,
    RevenueEntry,
    SettlementStatus,
)
from app.models.shift import Shift, ShiftStatus
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.finance import SettlementCreate
from app.services import audit, driver_ledger
from app.services import finance_common as fc
from app.services.common import paginate

ENTITY = "driver_settlement"
ZERO = Decimal("0")
HUNDRED = Decimal("100")

METHOD_LABELS = {
    CompensationMethod.FIXED_MONTHLY: "راتب شهري ثابت",
    CompensationMethod.DAILY_WAGE: "يومية",
    CompensationMethod.REVENUE_PERCENTAGE: "نسبة من الإيراد",
    CompensationMethod.FIXED_PLUS_INCENTIVE: "ثابت + حافز",
}


@dataclass
class Computation:
    lines: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    plans: list[dict[str, Any]] = field(default_factory=list)
    days_worked: int = 0
    eligible_revenue: Decimal = ZERO
    total: Decimal = ZERO

    def as_details(self) -> dict[str, Any]:
        return {
            "lines": self.lines,
            "warnings": self.warnings,
            "plans": self.plans,
            "days_worked": self.days_worked,
            "eligible_revenue": str(fc.money(self.eligible_revenue)),
            "computed_at": utcnow().isoformat(),
        }


def _prorated_monthly(amount: Decimal, start: date, end: date) -> Decimal:
    total = ZERO
    cursor = start
    while cursor <= end:
        days_in_month = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = cursor.replace(day=days_in_month)
        segment_end = min(month_end, end)
        days = (segment_end - cursor).days + 1
        total += amount * Decimal(days) / Decimal(days_in_month)
        cursor = segment_end + timedelta(days=1)
    return total


def worked_days(db: Session, driver_id: uuid.UUID, start: date, end: date) -> set[date]:
    rows = db.scalars(
        select(Shift.started_at).where(
            Shift.driver_id == driver_id,
            Shift.status == ShiftStatus.COMPLETED,
            Shift.started_at >= local_day_bounds_utc(start)[0],
            Shift.started_at < local_day_bounds_utc(end)[1],
        )
    ).all()
    return {to_local_date(at) for at in rows if at is not None}


def eligible_revenue(db: Session, driver_id: uuid.UUID, start: date, end: date) -> Decimal:
    entries = db.scalars(
        select(RevenueEntry).where(
            RevenueEntry.driver_id == driver_id,
            RevenueEntry.status == RecordStatus.APPROVED,
            func.coalesce(RevenueEntry.period_end, RevenueEntry.occurred_on) >= start,
            func.coalesce(RevenueEntry.period_start, RevenueEntry.occurred_on) <= end,
        )
    ).all()
    total = ZERO
    for e in entries:
        net = e.amount - e.fees_withheld
        if e.period_start and e.period_end:
            total += net * fc.period_share(e.period_start, e.period_end, start, end)
        else:
            total += net
    return total


def _plan_terms(plan: DriverCompensationPlan) -> dict[str, Any]:
    def s(v: Decimal | None) -> str | None:
        return str(v) if v is not None else None

    return {
        "plan_id": str(plan.id),
        "method": plan.method.value,
        "fixed_monthly_amount": s(plan.fixed_monthly_amount),
        "daily_wage_amount": s(plan.daily_wage_amount),
        "revenue_percentage": s(plan.revenue_percentage),
        "incentive_percentage": s(plan.incentive_percentage),
        "incentive_threshold_amount": s(plan.incentive_threshold_amount),
        "effective_from": plan.effective_from.isoformat(),
        "effective_to": plan.effective_to.isoformat() if plan.effective_to else None,
    }


def _plan_line(
    db: Session,
    plan: DriverCompensationPlan,
    driver_id: uuid.UUID,
    s: date,
    e: date,
    all_days: set[date],
) -> dict[str, Any]:
    """One calculation line for the part [s, e] of the period covered by `plan`."""
    line: dict[str, Any] = {
        "plan_id": str(plan.id),
        "method": plan.method.value,
        "label": METHOD_LABELS[plan.method],
        "period_start": s.isoformat(),
        "period_end": e.isoformat(),
    }
    if plan.method is CompensationMethod.FIXED_MONTHLY:
        base = plan.fixed_monthly_amount or ZERO
        amount = _prorated_monthly(base, s, e)
        line["basis"] = f"{base} شهريًا، محسوب بالأيام"
    elif plan.method is CompensationMethod.DAILY_WAGE:
        wage = plan.daily_wage_amount or ZERO
        days = len({d for d in all_days if s <= d <= e})
        amount = wage * days
        line["basis"] = f"{days} يوم عمل × {wage}"
        line["days"] = days
    elif plan.method is CompensationMethod.REVENUE_PERCENTAGE:
        pct = plan.revenue_percentage or ZERO
        rev = eligible_revenue(db, driver_id, s, e)
        amount = rev * pct / HUNDRED
        line["basis"] = f"{pct}% من إيراد مؤهل {fc.money(rev)}"
        line["eligible_revenue"] = str(fc.money(rev))
    else:  # FIXED_PLUS_INCENTIVE
        fixed = _prorated_monthly(plan.fixed_monthly_amount or ZERO, s, e)
        threshold = _prorated_monthly(plan.incentive_threshold_amount or ZERO, s, e)
        pct = plan.incentive_percentage or ZERO
        rev = eligible_revenue(db, driver_id, s, e)
        incentive = max(ZERO, rev - threshold) * pct / HUNDRED
        amount = fixed + incentive
        line["basis"] = (
            f"ثابت {fc.money(fixed)} + {pct}% من الإيراد فوق {fc.money(threshold)} "
            f"(إيراد مؤهل {fc.money(rev)})"
        )
        line["fixed"] = str(fc.money(fixed))
        line["incentive"] = str(fc.money(incentive))
        line["eligible_revenue"] = str(fc.money(rev))
    line["amount"] = str(fc.money(amount))
    return line


def compute(db: Session, driver_id: uuid.UUID, start: date, end: date) -> Computation:
    comp = Computation()
    plans = db.scalars(
        select(DriverCompensationPlan)
        .where(
            DriverCompensationPlan.driver_id == driver_id,
            DriverCompensationPlan.effective_from <= end,
            (DriverCompensationPlan.effective_to.is_(None))
            | (DriverCompensationPlan.effective_to >= start),
        )
        .order_by(DriverCompensationPlan.effective_from)
    ).all()
    covered = 0
    all_days = worked_days(db, driver_id, start, end)
    comp.days_worked = len(all_days)
    comp.eligible_revenue = eligible_revenue(db, driver_id, start, end)

    for plan in plans:
        s = max(plan.effective_from, start)
        e = min(plan.effective_to or end, end)
        covered += (e - s).days + 1
        comp.plans.append(_plan_terms(plan))
        line = _plan_line(db, plan, driver_id, s, e, all_days)
        comp.lines.append(line)
        comp.total += Decimal(line["amount"])

    period_days = (end - start).days + 1
    if not plans:
        comp.warnings.append("لا توجد خطة تعويض للسائق في هذه الفترة؛ المستحقات صفر")
    elif covered < period_days:
        comp.warnings.append(f"{period_days - covered} يوم في الفترة بدون خطة تعويض")
    pending = db.scalar(
        select(func.count())
        .select_from(RevenueEntry)
        .where(
            RevenueEntry.driver_id == driver_id,
            RevenueEntry.status == RecordStatus.SUBMITTED,
            RevenueEntry.occurred_on >= start,
            RevenueEntry.occurred_on <= end,
        )
    )
    if pending:
        comp.warnings.append(f"{pending} إيراد بانتظار الاعتماد غير محسوب")
    active = db.scalar(
        select(func.count())
        .select_from(Shift)
        .where(
            Shift.driver_id == driver_id,
            Shift.status == ShiftStatus.ACTIVE,
            Shift.started_at < local_day_bounds_utc(end)[1],
        )
    )
    if active:
        comp.warnings.append("توجد وردية نشطة لم تنتهِ بعد ضمن الفترة")
    comp.total = fc.money(comp.total)
    return comp


def get(db: Session, settlement_id: uuid.UUID) -> DriverSettlement:
    settlement = db.get(DriverSettlement, settlement_id)
    if settlement is None:
        raise NotFoundError("التسوية غير موجودة")
    return settlement


def _finalized_overlap(
    db: Session, driver_id: uuid.UUID, start: date, end: date
) -> DriverSettlement | None:
    return db.scalar(
        select(DriverSettlement).where(
            DriverSettlement.driver_id == driver_id,
            DriverSettlement.status == SettlementStatus.FINALIZED,
            DriverSettlement.period_start <= end,
            DriverSettlement.period_end >= start,
        )
    )


def create_draft(db: Session, *, actor: User, data: SettlementCreate) -> DriverSettlement:
    if db.get(Driver, data.driver_id) is None:
        raise field_error("driver_id", "السائق غير موجود")
    if _finalized_overlap(db, data.driver_id, data.period_start, data.period_end):
        raise field_error(
            "period_start",
            "توجد تسوية نهائية تغطي جزءًا من هذه الفترة",
            code="overlapping_settlement",
        )
    comp = compute(db, data.driver_id, data.period_start, data.period_end)
    settlement = DriverSettlement(
        driver_id=data.driver_id,
        period_start=data.period_start,
        period_end=data.period_end,
        status=SettlementStatus.DRAFT,
        earnings_amount=comp.total,
        details=comp.as_details(),
        notes=data.notes,
        created_by_id=actor.id,
    )
    db.add(settlement)
    db.flush()
    audit.record(
        db,
        action=f"{ENTITY}.created",
        actor=actor,
        entity_type="driver",
        entity_id=data.driver_id,
        details={
            "settlement_id": settlement.id,
            "period_start": data.period_start,
            "period_end": data.period_end,
            "earnings_amount": comp.total,
        },
    )
    db.commit()
    return settlement


def recalculate(db: Session, *, actor: User, settlement_id: uuid.UUID) -> DriverSettlement:
    settlement = get(db, settlement_id)
    if settlement.status is not SettlementStatus.DRAFT:
        raise ConflictError("إعادة الحساب للمسودات فقط", code="invalid_state")
    comp = compute(db, settlement.driver_id, settlement.period_start, settlement.period_end)
    before = settlement.earnings_amount
    settlement.earnings_amount = comp.total
    settlement.details = comp.as_details()
    audit.record(
        db,
        action=f"{ENTITY}.recalculated",
        actor=actor,
        entity_type="driver",
        entity_id=settlement.driver_id,
        details={"settlement_id": settlement.id, "before": before, "after": comp.total},
    )
    db.commit()
    return settlement


def finalize(db: Session, *, actor: User, settlement_id: uuid.UUID) -> DriverSettlement:
    settlement = get(db, settlement_id)
    if settlement.status is not SettlementStatus.DRAFT:
        raise ConflictError("يمكن اعتماد المسودات فقط", code="invalid_state")
    if _finalized_overlap(db, settlement.driver_id, settlement.period_start, settlement.period_end):
        raise ConflictError(
            "توجد تسوية نهائية تغطي جزءًا من هذه الفترة", code="overlapping_settlement"
        )
    # Recompute so the frozen figures reflect the data at finalisation time.
    comp = compute(db, settlement.driver_id, settlement.period_start, settlement.period_end)
    settlement.earnings_amount = comp.total
    settlement.details = comp.as_details()
    settlement.opening_balance = driver_ledger.balance(
        db, settlement.driver_id, before=settlement.period_start
    )
    if comp.total > 0:
        driver_ledger.post(
            db,
            driver_id=settlement.driver_id,
            entry_type=LedgerEntryType.EARNING,
            amount=comp.total,
            occurred_on=settlement.period_end,
            description=(
                f"مستحقات الفترة {settlement.period_start.isoformat()} — "
                f"{settlement.period_end.isoformat()}"
            ),
            actor=actor,
            source_type=LedgerSource.SETTLEMENT,
            source_id=settlement.id,
            settlement_id=settlement.id,
            period=(settlement.period_start, settlement.period_end),
        )
    settlement.closing_balance = driver_ledger.balance(
        db, settlement.driver_id, before=settlement.period_end + timedelta(days=1)
    )
    settlement.status = SettlementStatus.FINALIZED
    settlement.finalized_by_id = actor.id
    settlement.finalized_at = utcnow()
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "توجد تسوية نهائية تغطي جزءًا من هذه الفترة", code="overlapping_settlement"
        ) from exc
    audit.record(
        db,
        action=f"{ENTITY}.finalized",
        actor=actor,
        entity_type="driver",
        entity_id=settlement.driver_id,
        details={"settlement_id": settlement.id, "earnings_amount": comp.total},
    )
    db.commit()
    return settlement


def void(db: Session, *, actor: User, settlement_id: uuid.UUID, reason: str) -> DriverSettlement:
    settlement = get(db, settlement_id)
    if settlement.status is SettlementStatus.VOIDED:
        raise ConflictError("التسوية ملغاة بالفعل", code="invalid_state")
    if settlement.status is SettlementStatus.FINALIZED:
        driver_ledger.void_source(db, LedgerSource.SETTLEMENT, settlement.id, actor, reason)
    settlement.status = SettlementStatus.VOIDED
    settlement.voided_by_id = actor.id
    settlement.voided_at = utcnow()
    settlement.void_reason = reason
    audit.record(
        db,
        action=f"{ENTITY}.voided",
        actor=actor,
        entity_type="driver",
        entity_id=settlement.driver_id,
        details={"settlement_id": settlement.id},
        reason=reason,
    )
    db.commit()
    return settlement


def list_settlements(
    db: Session,
    params: PageParams,
    *,
    driver_id: uuid.UUID | None = None,
    status: SettlementStatus | None = None,
) -> tuple[list[DriverSettlement], int]:
    stmt = select(DriverSettlement)
    if driver_id:
        stmt = stmt.where(DriverSettlement.driver_id == driver_id)
    if status:
        stmt = stmt.where(DriverSettlement.status == status)
    stmt = stmt.order_by(DriverSettlement.period_end.desc(), DriverSettlement.created_at.desc())
    return paginate(db, stmt, params)
