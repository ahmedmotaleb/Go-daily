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

from app.core.config import get_settings
from app.core.errors import ConflictError, PermissionDenied, field_error
from app.core.time import local_day_bounds_utc, to_local_date, utcnow
from app.models.driver import (
    CompensationMethod,
    Driver,
    DriverCompensationPlan,
    EmploymentStatus,
)
from app.models.finance import (
    POSTED_SETTLEMENTS,
    DriverLedgerEntry,
    DriverSettlement,
    LedgerEntryType,
    LedgerSource,
    PaymentMethod,
    RecordStatus,
    RevenueEntry,
    SettlementStatus,
)
from app.models.shift import Shift, ShiftStatus
from app.models.user import AuthSession, User
from app.schemas.common import PageParams
from app.schemas.finance import SettlementCreate
from app.services import audit, driver_ledger, reauth
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


def get(db: Session, settlement_id: uuid.UUID, *, lock: bool = False) -> DriverSettlement:
    return fc.fetch(db, DriverSettlement, settlement_id, "التسوية غير موجودة", lock=lock)


def _finalized_overlap(
    db: Session, driver_id: uuid.UUID, start: date, end: date
) -> DriverSettlement | None:
    return db.scalar(
        select(DriverSettlement).where(
            DriverSettlement.driver_id == driver_id,
            DriverSettlement.status.in_(POSTED_SETTLEMENTS),
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
        details={},
        notes=data.notes,
        created_by_id=actor.id,
    )
    db.add(settlement)
    db.flush()
    _apply(db, settlement, comp)
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
    settlement = get(db, settlement_id, lock=True)
    if settlement.status is not SettlementStatus.DRAFT:
        raise ConflictError("إعادة الحساب للمسودات فقط", code="invalid_state")
    comp = compute(db, settlement.driver_id, settlement.period_start, settlement.period_end)
    before = settlement.earnings_amount
    _apply(db, settlement, comp)
    audit.record(
        db,
        action=f"{ENTITY}.recalculated",
        actor=actor,
        entity_type="driver",
        entity_id=settlement.driver_id,
        details={
            "settlement_id": settlement.id,
            "before": before,
            "after": settlement.earnings_amount,
        },
    )
    db.commit()
    return settlement


def finalize(db: Session, *, actor: User, settlement_id: uuid.UUID) -> DriverSettlement:
    """Approve exactly what was reviewed (U20) and post the earnings."""
    settlement = get(db, settlement_id, lock=True)
    if settlement.status is not SettlementStatus.REVIEWED:
        raise ConflictError("راجع التسوية قبل اعتمادها", code="invalid_state")
    if get_settings().settlement_require_separate_finalizer and (
        settlement.reviewed_by_id == actor.id
    ):
        raise PermissionDenied(
            "من راجع التسوية لا يعتمدها؛ يعتمدها موظف آخر", code="separate_finalizer_required"
        )
    if _finalized_overlap(db, settlement.driver_id, settlement.period_start, settlement.period_end):
        raise ConflictError(
            "توجد تسوية نهائية تغطي جزءًا من هذه الفترة", code="overlapping_settlement"
        )
    # The reviewed inputs are frozen: if the records changed since, the
    # settlement goes back for another review instead of silently changing.
    comp = compute(db, settlement.driver_id, settlement.period_start, settlement.period_end)
    frozen = (settlement.details or {}).get("computed_total")
    # A review that froze no total cannot vouch for anything: review it again.
    if frozen is None or fc.money(comp.total) != Decimal(str(frozen)):
        raise ConflictError(
            "تغيرت البيانات منذ المراجعة؛ أعد التسوية إلى مسودة وراجعها مرة أخرى",
            code="inputs_changed",
        )
    settlement.opening_balance = driver_ledger.balance(
        db, settlement.driver_id, before=settlement.period_start
    )
    if settlement.earnings_amount > 0:
        driver_ledger.post(
            db,
            driver_id=settlement.driver_id,
            entry_type=LedgerEntryType.EARNING,
            amount=settlement.earnings_amount,
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
        details={"settlement_id": settlement.id, "earnings_amount": settlement.earnings_amount},
    )
    db.commit()
    return settlement


def void(
    db: Session,
    *,
    actor: User,
    settlement_id: uuid.UUID,
    reason: str,
    session: AuthSession | None = None,
) -> DriverSettlement:
    """Void a settlement. Its earnings leave the driver account; payments stay.

    A payment recorded against the settlement is money that really left the
    company, so it is never reversed here: after the void the driver owes it
    back (or a corrected settlement absorbs it). Voiding posted figures is a
    sensitive action and needs a recent confirmation (U35).
    """
    settlement = get(db, settlement_id, lock=True)
    if settlement.status is SettlementStatus.VOIDED:
        raise ConflictError("التسوية ملغاة بالفعل", code="invalid_state")
    if settlement.status in POSTED_SETTLEMENTS:
        if session is not None:
            reauth.require(session)
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


# --- U20: review, adjustments, payment, drafts for everyone ----------------------------


def account_summary(
    db: Session, driver_id: uuid.UUID, start: date, end: date, settlement_id: uuid.UUID
) -> dict[str, Any]:
    """The driver account around the period: opening balance and the period's entries.

    Bonuses, reimbursements, advances, deductions, cash and earlier payments
    are already on the account; the settlement shows them so the reviewer
    sees what the driver will be owed, without counting them twice.
    """
    rows = db.execute(
        select(DriverLedgerEntry.entry_type, func.sum(DriverLedgerEntry.amount))
        .where(
            DriverLedgerEntry.driver_id == driver_id,
            DriverLedgerEntry.voided_at.is_(None),
            DriverLedgerEntry.occurred_on >= start,
            DriverLedgerEntry.occurred_on <= end,
            ~(
                (DriverLedgerEntry.source_type == LedgerSource.SETTLEMENT)
                & (DriverLedgerEntry.source_id == settlement_id)
            ),
        )
        .group_by(DriverLedgerEntry.entry_type)
    ).all()
    opening = driver_ledger.balance(db, driver_id, before=start)
    by_type = {t.value: str(fc.money(total)) for t, total in rows if total}
    period = sum((Decimal(v) for v in by_type.values()), ZERO)
    return {
        "opening_balance": str(fc.money(opening)),
        "by_type": by_type,
        "period_entries": str(fc.money(period)),
    }


def _apply(db: Session, settlement: DriverSettlement, comp: Computation) -> None:
    """Store a computation, keeping the manual adjustments already made."""
    adjustments = list((settlement.details or {}).get("adjustments", []))
    total = comp.total + sum((Decimal(a["amount"]) for a in adjustments), ZERO)
    if total < 0:
        raise field_error("amount", "المستحقات بعد التعديل لا تكون سالبة", code="negative_total")
    details = comp.as_details()
    details["computed_total"] = str(comp.total)
    details["adjustments"] = adjustments
    if settlement.id is not None:
        details["account"] = account_summary(
            db, settlement.driver_id, settlement.period_start, settlement.period_end, settlement.id
        )
        account = details["account"]
        details["expected_balance"] = str(
            fc.money(
                Decimal(account["opening_balance"]) + Decimal(account["period_entries"]) + total
            )
        )
    settlement.details = details
    settlement.earnings_amount = fc.money(total)


def adjust(
    db: Session,
    *,
    actor: User,
    settlement_id: uuid.UUID,
    amount: Decimal,
    reason: str,
    session: AuthSession | None = None,
) -> DriverSettlement:
    """A manual change to a draft's earnings, with its reason (audited).

    Large changes need a recent confirmation, like large payments (audit H3).
    """
    settlement = get(db, settlement_id, lock=True)
    if settlement.status is not SettlementStatus.DRAFT:
        raise ConflictError("التعديل على المسودات فقط", code="invalid_state")
    if amount == 0:
        raise field_error("amount", "أدخل مبلغًا")
    if session is not None:
        reauth.require_for_amount(session, amount)
    before = settlement.earnings_amount
    details = dict(settlement.details or {})
    details["adjustments"] = [
        *details.get("adjustments", []),
        {
            "amount": str(fc.money(amount)),
            "reason": reason,
            "by": actor.full_name,
            "by_id": str(actor.id),
            "at": utcnow().isoformat(),
        },
    ]
    settlement.details = details
    comp = compute(db, settlement.driver_id, settlement.period_start, settlement.period_end)
    _apply(db, settlement, comp)
    audit.record(
        db,
        action=f"{ENTITY}.adjusted",
        actor=actor,
        entity_type="driver",
        entity_id=settlement.driver_id,
        details={
            "settlement_id": settlement.id,
            "amount": fc.money(amount),
            "before": before,
            "after": settlement.earnings_amount,
        },
        reason=reason,
    )
    db.commit()
    return settlement


def review(db: Session, *, actor: User, settlement_id: uuid.UUID) -> DriverSettlement:
    """Freeze the inputs: from here the figures change only by going back to draft."""
    settlement = get(db, settlement_id, lock=True)
    if settlement.status is not SettlementStatus.DRAFT:
        raise ConflictError("المراجعة للمسودات فقط", code="invalid_state")
    comp = compute(db, settlement.driver_id, settlement.period_start, settlement.period_end)
    _apply(db, settlement, comp)
    settlement.status = SettlementStatus.REVIEWED
    settlement.reviewed_by_id = actor.id
    settlement.reviewed_at = utcnow()
    audit.record(
        db,
        action=f"{ENTITY}.reviewed",
        actor=actor,
        entity_type="driver",
        entity_id=settlement.driver_id,
        details={"settlement_id": settlement.id, "earnings_amount": settlement.earnings_amount},
    )
    db.commit()
    return settlement


def reopen(db: Session, *, actor: User, settlement_id: uuid.UUID, reason: str) -> DriverSettlement:
    """Back to draft from review (before approval), with a reason."""
    settlement = get(db, settlement_id, lock=True)
    if settlement.status is not SettlementStatus.REVIEWED:
        raise ConflictError("الإرجاع للمسودة قبل الاعتماد فقط", code="invalid_state")
    settlement.status = SettlementStatus.DRAFT
    settlement.reviewed_by_id = None
    settlement.reviewed_at = None
    audit.record(
        db,
        action=f"{ENTITY}.reopened",
        actor=actor,
        entity_type="driver",
        entity_id=settlement.driver_id,
        details={"settlement_id": settlement.id},
        reason=reason,
    )
    db.commit()
    return settlement


def pay(
    db: Session,
    *,
    actor: User,
    settlement_id: uuid.UUID,
    amount: Decimal,
    paid_on: date,
    method: PaymentMethod,
    reference: str | None,
    session: AuthSession | None = None,
) -> DriverSettlement:
    """Record a payment made outside the system. Nothing is transferred here.

    Payments may be split, but together never exceed the settlement's earnings.
    The re-auth threshold applies to the cumulative amount paid, so splitting
    a large payment does not avoid the confirmation (U35).
    """
    settlement = get(db, settlement_id, lock=True)
    if settlement.status is not SettlementStatus.FINALIZED:
        raise ConflictError("يُسجل الدفع للتسويات المعتمدة فقط", code="invalid_state")
    if get_settings().settlement_require_separate_payer and settlement.finalized_by_id == actor.id:
        raise PermissionDenied(
            "من اعتمد التسوية لا يسجل صرفها؛ يسجله موظف آخر", code="separate_payer_required"
        )
    fc.check_day(paid_on, "paid_on")
    if paid_on < settlement.period_start:
        raise field_error("paid_on", "تاريخ الدفع قبل بداية الفترة")
    amount = fc.money(amount)
    already = fc.money(settlement.paid_amount or Decimal(0))
    due = fc.money(settlement.earnings_amount - already)
    if amount > due:
        raise field_error(
            "amount",
            f"المبلغ أكبر من المتبقي المستحق للسائق في هذه التسوية ({due} ج.م)",
            code="payment_exceeds_due",
        )
    if session is not None:
        reauth.require_for_amount(session, already + amount)
    driver_ledger.post(
        db,
        driver_id=settlement.driver_id,
        entry_type=LedgerEntryType.PAYMENT,
        amount=amount,
        occurred_on=paid_on,
        description=(
            f"دفع تسوية {settlement.period_start.isoformat()} — {settlement.period_end.isoformat()}"
        ),
        actor=actor,
        # Linked by settlement_id: the settlement's own source is its earnings.
        settlement_id=settlement.id,
    )
    settlement.paid_amount = already + amount
    if settlement.paid_amount == fc.money(settlement.earnings_amount):
        settlement.status = SettlementStatus.PAID
    settlement.paid_on = paid_on
    settlement.payment_method = method
    settlement.payment_reference = reference
    settlement.paid_by_id = actor.id
    settlement.paid_at = utcnow()
    audit.record(
        db,
        action=f"{ENTITY}.paid",
        actor=actor,
        entity_type="driver",
        entity_id=settlement.driver_id,
        details={
            "settlement_id": settlement.id,
            "amount": amount,
            "paid_total": settlement.paid_amount,
            "method": method.value,
            "paid_on": paid_on,
        },
    )
    db.commit()
    return settlement


@dataclass
class Generated:
    created: list[DriverSettlement] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


def generate_drafts(db: Session, *, actor: User, start: date, end: date) -> Generated:
    """A draft for every active driver with a compensation plan in the period.

    Drivers who already have a settlement (other than voided) touching the
    period are skipped and listed. Drafts are only calculations: nothing is
    posted or paid until each is reviewed and approved.
    """
    out = Generated()
    drivers = db.scalars(
        select(Driver)
        .where(
            Driver.employment_status == EmploymentStatus.ACTIVE,
            select(DriverCompensationPlan.id)
            .where(
                DriverCompensationPlan.driver_id == Driver.id,
                DriverCompensationPlan.effective_from <= end,
                (DriverCompensationPlan.effective_to.is_(None))
                | (DriverCompensationPlan.effective_to >= start),
            )
            .exists(),
        )
        .order_by(Driver.full_name)
    ).all()
    for driver in drivers:
        existing = db.scalar(
            select(DriverSettlement).where(
                DriverSettlement.driver_id == driver.id,
                DriverSettlement.status != SettlementStatus.VOIDED,
                DriverSettlement.period_start <= end,
                DriverSettlement.period_end >= start,
            )
        )
        if existing is not None:
            out.skipped.append(
                {"driver": driver.full_name, "reason": "توجد تسوية تغطي جزءًا من الفترة"}
            )
            continue
        out.created.append(
            create_draft(
                db,
                actor=actor,
                data=SettlementCreate(driver_id=driver.id, period_start=start, period_end=end),
            )
        )
    audit.record(
        db,
        action=f"{ENTITY}.generated",
        actor=actor,
        entity_type=ENTITY,
        entity_id=None,
        details={
            "period_start": start,
            "period_end": end,
            "created": len(out.created),
            "skipped": len(out.skipped),
        },
    )
    db.commit()
    return out


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
