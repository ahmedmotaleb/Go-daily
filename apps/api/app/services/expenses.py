"""General operating expenses with configurable categories (Task 16)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, field_error
from app.core.time import local_day_bounds_utc, to_local_date
from app.models.finance import (
    Expense,
    ExpenseCategory,
    ExpenseGroup,
    LedgerEntryType,
    LedgerSource,
    PaidBy,
    RecordSource,
    RecordStatus,
)
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.finance import (
    ExpenseCategoryCreate,
    ExpenseCategoryUpdate,
    ExpenseCorrection,
    ExpenseCreate,
    ExpenseUpdate,
)
from app.services import audit, driver_ledger
from app.services import finance_common as fc
from app.services.common import apply_changes, paginate

ENTITY = "expense"
AUDITED = (
    "vehicle_id",
    "driver_id",
    "shift_id",
    "session_id",
    "category_id",
    "amount",
    "occurred_at",
    "vendor",
    "payment_method",
    "paid_by",
    "notes",
)


# --- Categories ------------------------------------------------------------------------


def list_categories(db: Session, *, include_inactive: bool = False) -> list[ExpenseCategory]:
    stmt = select(ExpenseCategory).order_by(ExpenseCategory.sort_order, ExpenseCategory.code)
    if not include_inactive:
        stmt = stmt.where(ExpenseCategory.is_active.is_(True))
    return list(db.scalars(stmt).all())


def create_category(db: Session, *, actor: User, data: ExpenseCategoryCreate) -> ExpenseCategory:
    if db.scalar(select(ExpenseCategory.id).where(ExpenseCategory.code == data.code)):
        raise field_error("code", "الرمز مستخدم بالفعل", code="duplicate_code")
    category = ExpenseCategory(**data.model_dump())
    db.add(category)
    db.flush()
    audit.record(
        db,
        action="expense_category.created",
        actor=actor,
        entity_type="expense_category",
        entity_id=category.id,
        details=data.model_dump(mode="json"),
    )
    db.commit()
    return category


def update_category(
    db: Session, *, actor: User, category_id: uuid.UUID, data: ExpenseCategoryUpdate
) -> ExpenseCategory:
    category = db.get(ExpenseCategory, category_id)
    if category is None:
        raise NotFoundError("التصنيف غير موجود")
    changes = apply_changes(
        category,
        data.model_dump(exclude_unset=True),
        ("name_ar", "pnl_group", "is_active", "sort_order"),
    )
    if changes:
        audit.record(
            db,
            action="expense_category.updated",
            actor=actor,
            entity_type="expense_category",
            entity_id=category.id,
            changes=changes,
        )
    db.commit()
    return category


# --- Expenses ---------------------------------------------------------------------------


def get(db: Session, expense_id: uuid.UUID) -> Expense:
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise NotFoundError("المصروف غير موجود")
    return expense


def _active_category(db: Session, category_id: uuid.UUID) -> ExpenseCategory:
    category = db.get(ExpenseCategory, category_id)
    if category is None or not category.is_active:
        raise field_error("category_id", "التصنيف غير موجود أو غير مفعل")
    return category


def _validate(expense: Expense) -> None:
    fc.check_time(expense.occurred_at)
    if expense.paid_by is PaidBy.DRIVER and expense.driver_id is None:
        raise field_error("driver_id", "حدد السائق الذي دفع المبلغ")


def _new(
    db: Session, *, actor: User, data: ExpenseCreate, corrects: Expense | None = None
) -> Expense:
    vehicle, driver, shift, session = fc.resolve_refs(
        db,
        vehicle_id=data.vehicle_id,
        driver_id=data.driver_id,
        shift_id=data.shift_id,
        session_id=data.session_id,
    )
    category = _active_category(db, data.category_id)
    expense = Expense(
        vehicle_id=vehicle.id,
        driver_id=driver.id if driver else None,
        shift_id=shift.id if shift else None,
        session_id=session.id if session else None,
        category_id=category.id,
        amount=data.amount,
        occurred_at=data.occurred_at,
        vendor=data.vendor,
        payment_method=data.payment_method,
        paid_by=data.paid_by,
        notes=data.notes,
        source=corrects.source if corrects else RecordSource.ADMIN,
        status=RecordStatus.SUBMITTED,
        created_by_id=actor.id,
        corrects_id=corrects.id if corrects else None,
    )
    expense.vehicle = vehicle
    expense.category = category
    _validate(expense)
    db.add(expense)
    db.flush()
    return expense


def _post_reimbursement(db: Session, expense: Expense, actor: User) -> None:
    if expense.paid_by is not PaidBy.DRIVER or expense.driver_id is None:
        return
    driver_ledger.post(
        db,
        driver_id=expense.driver_id,
        entry_type=LedgerEntryType.REIMBURSEMENT,
        amount=expense.amount,
        occurred_on=to_local_date(expense.occurred_at),
        description=f"تعويض مصروف {expense.category.name_ar} — {expense.vehicle.internal_code}",
        actor=actor,
        source_type=LedgerSource.EXPENSE,
        source_id=expense.id,
        vehicle_id=expense.vehicle_id,
    )


def _approve(db: Session, expense: Expense, actor: User, note: str | None) -> None:
    fc.approve(expense, actor, note)
    _post_reimbursement(db, expense, actor)
    audit.record(
        db,
        action=f"{ENTITY}.approved",
        actor=actor,
        entity_type=ENTITY,
        entity_id=expense.id,
        details={"note": note} if note else None,
    )


def create(db: Session, *, actor: User, data: ExpenseCreate, can_approve: bool = False) -> Expense:
    expense = _new(db, actor=actor, data=data)
    audit.record(
        db,
        action=f"{ENTITY}.created",
        actor=actor,
        entity_type=ENTITY,
        entity_id=expense.id,
        changes=audit.diff({}, audit.snapshot(expense, AUDITED)),
    )
    if data.approve_now and can_approve:
        _approve(db, expense, actor, note="اعتماد عند الإدخال")
    db.commit()
    return expense


def update(db: Session, *, actor: User, expense_id: uuid.UUID, data: ExpenseUpdate) -> Expense:
    expense = get(db, expense_id)
    fc.ensure_editable(expense)
    fields = data.model_dump(exclude_unset=True)
    if {"driver_id", "shift_id", "session_id"} & fields.keys():
        _, driver, shift, session = fc.resolve_refs(
            db,
            vehicle_id=expense.vehicle_id,
            driver_id=fields.get("driver_id", expense.driver_id),
            shift_id=fields.get("shift_id", expense.shift_id),
            session_id=fields.get("session_id", expense.session_id),
        )
        fields["driver_id"] = driver.id if driver else None
        fields["shift_id"] = shift.id if shift else None
        fields["session_id"] = session.id if session else None
    if "category_id" in fields:
        expense.category = _active_category(db, fields["category_id"])
    changes = apply_changes(expense, fields, AUDITED)
    _validate(expense)
    fc.resubmit_if_rejected(expense)
    if changes:
        audit.record(
            db,
            action=f"{ENTITY}.updated",
            actor=actor,
            entity_type=ENTITY,
            entity_id=expense.id,
            changes=changes,
        )
    db.commit()
    return expense


def approve(db: Session, *, actor: User, expense_id: uuid.UUID, note: str | None) -> Expense:
    expense = get(db, expense_id)
    _approve(db, expense, actor, note)
    db.commit()
    return expense


def reject(db: Session, *, actor: User, expense_id: uuid.UUID, reason: str) -> Expense:
    expense = get(db, expense_id)
    fc.reject(expense, actor, reason)
    audit.record(
        db,
        action=f"{ENTITY}.rejected",
        actor=actor,
        entity_type=ENTITY,
        entity_id=expense.id,
        reason=reason,
    )
    db.commit()
    return expense


def _void(db: Session, expense: Expense, actor: User, reason: str) -> None:
    previous = fc.void(expense, actor, reason)
    if previous is RecordStatus.APPROVED:
        driver_ledger.void_source(db, LedgerSource.EXPENSE, expense.id, actor, reason)
    audit.record(
        db,
        action=f"{ENTITY}.voided",
        actor=actor,
        entity_type=ENTITY,
        entity_id=expense.id,
        reason=reason,
    )


def void(db: Session, *, actor: User, expense_id: uuid.UUID, reason: str) -> Expense:
    expense = get(db, expense_id)
    _void(db, expense, actor, reason)
    db.commit()
    return expense


def correct(
    db: Session, *, actor: User, expense_id: uuid.UUID, data: ExpenseCorrection, can_approve: bool
) -> Expense:
    original = get(db, expense_id)
    fc.ensure_correctable(original)
    _void(db, original, actor, f"تصحيح: {data.reason}")
    replacement = _new(db, actor=actor, data=data, corrects=original)
    audit.record(
        db,
        action=f"{ENTITY}.corrected",
        actor=actor,
        entity_type=ENTITY,
        entity_id=replacement.id,
        reason=data.reason,
        changes=audit.diff(audit.snapshot(original, AUDITED), audit.snapshot(replacement, AUDITED)),
        details={"corrects_id": original.id},
    )
    if data.approve_now and can_approve:
        _approve(db, replacement, actor, note="اعتماد التصحيح")
    db.commit()
    return replacement


@dataclass(frozen=True)
class ExpenseFilters:
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    group: ExpenseGroup | None = None
    status: RecordStatus | None = None
    date_from: date | None = None
    date_to: date | None = None


def _filtered(f: ExpenseFilters) -> Select[Expense]:
    stmt = select(Expense)
    if f.vehicle_id:
        stmt = stmt.where(Expense.vehicle_id == f.vehicle_id)
    if f.driver_id:
        stmt = stmt.where(Expense.driver_id == f.driver_id)
    if f.category_id:
        stmt = stmt.where(Expense.category_id == f.category_id)
    if f.group:
        stmt = stmt.join(ExpenseCategory, ExpenseCategory.id == Expense.category_id).where(
            ExpenseCategory.pnl_group == f.group
        )
    if f.status:
        stmt = stmt.where(Expense.status == f.status)
    if f.date_from:
        stmt = stmt.where(Expense.occurred_at >= local_day_bounds_utc(f.date_from)[0])
    if f.date_to:
        stmt = stmt.where(Expense.occurred_at < local_day_bounds_utc(f.date_to)[1])
    return stmt


def list_expenses(
    db: Session, params: PageParams, filters: ExpenseFilters
) -> tuple[list[Expense], int]:
    stmt = _filtered(filters).order_by(Expense.occurred_at.desc(), Expense.created_at.desc())
    return paginate(db, stmt, params)


def summary(db: Session, filters: ExpenseFilters) -> dict[str, object]:
    base = _filtered(replace(filters, status=None)).subquery()
    rows = db.execute(
        select(base.c.category_id, func.count(), func.coalesce(func.sum(base.c.amount), 0))
        .where(base.c.status == RecordStatus.APPROVED.value)
        .group_by(base.c.category_id)
    ).all()
    pending = db.scalar(
        select(func.count()).select_from(base).where(base.c.status == RecordStatus.SUBMITTED.value)
    )
    categories = {c.id: c for c in list_categories(db, include_inactive=True)}
    by_category = [
        {"category": categories[cid], "count": count, "amount": Decimal(amount)}
        for cid, count, amount in sorted(
            rows, key=lambda r: (categories[r[0]].sort_order, categories[r[0]].code)
        )
    ]
    return {
        "by_category": by_category,
        "total_amount": fc.money(sum((Decimal(r[2]) for r in rows), Decimal("0"))),
        "pending_count": pending or 0,
    }
