"""Revenue ledger and receipts (Task 17).

Every earned amount is one revenue entry; it is the only revenue source
for reports, so the same money is never counted twice. Money actually
received is recorded as receipts (cash or electronic, held by the driver
or the company). Receipts held by the driver are custody: they post a
CASH_COLLECTED debit on the driver account until handed over.

Ride-hailing revenue is created only from approved platform statements.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.selectable import Subquery

from app.core.errors import ConflictError, NotFoundError, field_error
from app.core.time import to_local_date, utcnow
from app.models.finance import (
    LedgerEntryType,
    LedgerSource,
    PaymentMethod,
    ReceivedBy,
    RecordSource,
    RecordStatus,
    RevenueEntry,
    RevenueKind,
    RevenueReceipt,
)
from app.models.operations import OperationType
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.finance import (
    ReceiptIn,
    RevenueCorrection,
    RevenueCreate,
    RevenueFields,
    RevenueUpdate,
)
from app.services import audit, driver_ledger
from app.services import finance_common as fc
from app.services.common import apply_changes, paginate

ENTITY = "revenue_entry"
AUDITED = (
    "kind",
    "vehicle_id",
    "driver_id",
    "shift_id",
    "session_id",
    "operation_type_id",
    "occurred_on",
    "period_start",
    "period_end",
    "amount",
    "fees_withheld",
    "loops_count",
    "customer_name",
    "reference",
    "notes",
)
ZERO = Decimal("0")

KIND_LABELS = {
    RevenueKind.FIXED_ROUTE_COLLECTION: "تحصيل خط",
    RevenueKind.CONTRACT_SERVICE: "عقد خدمة",
    RevenueKind.PRIVATE_TRIP: "رحلة خاصة",
    RevenueKind.RIDE_HAILING: "نقل ذكي",
    RevenueKind.OTHER: "إيراد آخر",
}


def active_receipts(entry: RevenueEntry) -> list[RevenueReceipt]:
    return [r for r in entry.receipts if r.voided_at is None]


def received(entry: RevenueEntry) -> Decimal:
    return sum((r.amount for r in active_receipts(entry)), ZERO)


def received_split(entry: RevenueEntry) -> tuple[Decimal, Decimal]:
    """(cash, electronic) received."""
    cash = sum((r.amount for r in active_receipts(entry) if r.method is PaymentMethod.CASH), ZERO)
    return cash, received(entry) - cash


def net_amount(entry: RevenueEntry) -> Decimal:
    return entry.amount - entry.fees_withheld


def outstanding(entry: RevenueEntry) -> Decimal:
    return net_amount(entry) - received(entry)


def get(db: Session, entry_id: uuid.UUID, *, lock: bool = False) -> RevenueEntry:
    return fc.fetch(
        db,
        RevenueEntry,
        entry_id,
        "الإيراد غير موجود",
        lock=lock,
        options=[selectinload(RevenueEntry.receipts)],
    )


def _validate(entry: RevenueEntry) -> None:
    fc.check_day(entry.occurred_on, "occurred_on")
    if entry.kind is RevenueKind.CONTRACT_SERVICE and entry.period_start is None:
        raise field_error("period_start", "حدد فترة الخدمة لإيراد العقد")


def _operation_type_id(
    db: Session, requested: uuid.UUID | None, session_type: uuid.UUID | None
) -> uuid.UUID | None:
    if session_type is not None:
        return session_type
    if requested is not None and db.get(OperationType, requested) is None:
        raise field_error("operation_type_id", "نوع التشغيل غير موجود")
    return requested


def _new(
    db: Session,
    *,
    actor: User,
    data: RevenueFields,
    source: RecordSource = RecordSource.ADMIN,
    corrects: RevenueEntry | None = None,
    fees_withheld: Decimal = ZERO,
    statement_id: uuid.UUID | None = None,
) -> RevenueEntry:
    if data.kind is RevenueKind.RIDE_HAILING and source is not RecordSource.SYSTEM:
        raise field_error(
            "kind", "إيراد النقل الذكي يُسجل من كشوف المنصات فقط", code="use_statement"
        )
    vehicle, driver, shift, session = fc.resolve_refs(
        db,
        vehicle_id=data.vehicle_id,
        driver_id=data.driver_id,
        shift_id=data.shift_id,
        session_id=data.session_id,
    )
    entry = RevenueEntry(
        kind=data.kind,
        vehicle_id=vehicle.id,
        driver_id=driver.id if driver else None,
        shift_id=shift.id if shift else None,
        session_id=session.id if session else None,
        operation_type_id=_operation_type_id(
            db, data.operation_type_id, session.operation_type_id if session else None
        ),
        occurred_on=data.occurred_on,
        period_start=data.period_start,
        period_end=data.period_end,
        amount=data.amount,
        fees_withheld=fees_withheld,
        loops_count=data.loops_count,
        customer_name=data.customer_name,
        reference=data.reference,
        notes=data.notes,
        statement_id=statement_id,
        source=source,
        status=RecordStatus.SUBMITTED,
        created_by_id=actor.id,
        corrects_id=corrects.id if corrects else None,
    )
    entry.vehicle = vehicle
    _validate(entry)
    db.add(entry)
    db.flush()
    return entry


def _approve(db: Session, entry: RevenueEntry, actor: User, note: str | None) -> None:
    fc.approve(entry, actor, note)
    audit.record(
        db,
        action=f"{ENTITY}.approved",
        actor=actor,
        entity_type=ENTITY,
        entity_id=entry.id,
        details={"note": note} if note else None,
    )


def create(
    db: Session, *, actor: User, data: RevenueCreate, can_approve: bool = False
) -> RevenueEntry:
    entry = _new(db, actor=actor, data=data)
    audit.record(
        db,
        action=f"{ENTITY}.created",
        actor=actor,
        entity_type=ENTITY,
        entity_id=entry.id,
        changes=audit.diff({}, audit.snapshot(entry, AUDITED)),
    )
    if data.receipt is not None:
        add_receipt_to(db, entry, data.receipt, actor)
    if data.approve_now and can_approve:
        _approve(db, entry, actor, note="اعتماد عند الإدخال")
    db.commit()
    return get(db, entry.id)


def create_system(
    db: Session,
    *,
    actor: User,
    data: RevenueFields,
    fees_withheld: Decimal,
    statement_id: uuid.UUID,
) -> RevenueEntry:
    """Revenue generated from another approved record (caller commits)."""
    entry = _new(
        db,
        actor=actor,
        data=data,
        source=RecordSource.SYSTEM,
        fees_withheld=fees_withheld,
        statement_id=statement_id,
    )
    entry.status = RecordStatus.APPROVED
    entry.reviewed_by_id = actor.id
    entry.reviewed_at = utcnow()
    audit.record(
        db,
        action=f"{ENTITY}.created",
        actor=actor,
        entity_type=ENTITY,
        entity_id=entry.id,
        changes=audit.diff({}, audit.snapshot(entry, AUDITED)),
        details={"statement_id": statement_id},
    )
    return entry


def _ensure_manual(entry: RevenueEntry) -> None:
    if entry.statement_id is not None:
        raise ConflictError(
            "هذا الإيراد ناتج عن كشف منصة؛ عدّل أو ألغِ الكشف نفسه", code="statement_managed"
        )


def update(db: Session, *, actor: User, entry_id: uuid.UUID, data: RevenueUpdate) -> RevenueEntry:
    entry = get(db, entry_id, lock=True)
    _ensure_manual(entry)
    fc.ensure_editable(entry)
    fields = data.model_dump(exclude_unset=True)
    if {"driver_id", "shift_id", "session_id"} & fields.keys():
        _, driver, shift, session = fc.resolve_refs(
            db,
            vehicle_id=entry.vehicle_id,
            driver_id=fields.get("driver_id", entry.driver_id),
            shift_id=fields.get("shift_id", entry.shift_id),
            session_id=fields.get("session_id", entry.session_id),
        )
        if driver is None and any(
            r.received_by is ReceivedBy.DRIVER for r in active_receipts(entry)
        ):
            raise field_error("driver_id", "توجد مقبوضات لدى السائق؛ لا يمكن إزالة السائق")
        fields["driver_id"] = driver.id if driver else None
        fields["shift_id"] = shift.id if shift else None
        fields["session_id"] = session.id if session else None
        if session is not None:
            fields["operation_type_id"] = session.operation_type_id
    if "operation_type_id" in fields:
        fields["operation_type_id"] = _operation_type_id(db, fields["operation_type_id"], None)
    changes = apply_changes(entry, fields, AUDITED)
    if (entry.period_start is None) != (entry.period_end is None) or (
        entry.period_start and entry.period_end and entry.period_end < entry.period_start
    ):
        raise field_error("period_end", "فترة الخدمة غير صحيحة")
    _validate(entry)
    if outstanding(entry) < 0:
        raise field_error("amount", "المبلغ أقل من المقبوض فعلًا")
    fc.resubmit_if_rejected(entry)
    if changes:
        audit.record(
            db,
            action=f"{ENTITY}.updated",
            actor=actor,
            entity_type=ENTITY,
            entity_id=entry.id,
            changes=changes,
        )
    db.commit()
    return entry


def add_receipt_to(
    db: Session, entry: RevenueEntry, data: ReceiptIn, actor: User
) -> RevenueReceipt:
    """Record money received (caller commits)."""
    if entry.status in (RecordStatus.VOIDED, RecordStatus.REJECTED):
        raise ConflictError("لا يمكن تسجيل مقبوضات على إيراد ملغي أو مرفوض", code="invalid_state")
    fc.check_time(data.received_at, "received_at")
    if data.amount > outstanding(entry):
        raise field_error(
            "amount", f"المبلغ أكبر من المتبقي ({outstanding(entry)})", code="over_receipt"
        )
    if data.received_by is ReceivedBy.DRIVER and entry.driver_id is None:
        raise field_error("received_by", "حدد السائق على الإيراد أولًا")
    receipt = RevenueReceipt(
        revenue_entry_id=entry.id,
        received_at=data.received_at,
        amount=data.amount,
        method=data.method,
        received_by=data.received_by,
        reference=data.reference,
        notes=data.notes,
        created_by_id=actor.id,
    )
    db.add(receipt)
    entry.receipts.append(receipt)
    db.flush()
    if data.received_by is ReceivedBy.DRIVER and entry.driver_id is not None:
        driver_ledger.post(
            db,
            driver_id=entry.driver_id,
            entry_type=LedgerEntryType.CASH_COLLECTED,
            amount=data.amount,
            occurred_on=to_local_date(data.received_at),
            description=(
                f"تحصيل لدى السائق — {KIND_LABELS[entry.kind]} {entry.vehicle.internal_code}"
            ),
            actor=actor,
            source_type=LedgerSource.REVENUE_RECEIPT,
            source_id=receipt.id,
            vehicle_id=entry.vehicle_id,
        )
    audit.record(
        db,
        action="revenue_receipt.added",
        actor=actor,
        entity_type=ENTITY,
        entity_id=entry.id,
        details={
            "receipt_id": receipt.id,
            "amount": data.amount,
            "method": data.method.value,
            "received_by": data.received_by.value,
        },
    )
    return receipt


def add_receipt(db: Session, *, actor: User, entry_id: uuid.UUID, data: ReceiptIn) -> RevenueEntry:
    entry = get(db, entry_id, lock=True)
    _ensure_manual(entry)
    add_receipt_to(db, entry, data, actor)
    db.commit()
    return entry


def _void_receipt(db: Session, receipt: RevenueReceipt, actor: User, reason: str) -> None:
    receipt.voided_at = utcnow()
    receipt.voided_by_id = actor.id
    receipt.void_reason = reason
    driver_ledger.void_source(db, LedgerSource.REVENUE_RECEIPT, receipt.id, actor, reason)
    audit.record(
        db,
        action="revenue_receipt.voided",
        actor=actor,
        entity_type=ENTITY,
        entity_id=receipt.revenue_entry_id,
        details={"receipt_id": receipt.id, "amount": receipt.amount},
        reason=reason,
    )


def void_receipt(db: Session, *, actor: User, receipt_id: uuid.UUID, reason: str) -> RevenueEntry:
    receipt = db.get(RevenueReceipt, receipt_id)
    if receipt is None:
        raise NotFoundError("المقبوض غير موجود")
    if receipt.voided_at is not None:
        raise ConflictError("المقبوض ملغي بالفعل", code="invalid_state")
    _ensure_manual(receipt.entry)
    _void_receipt(db, receipt, actor, reason)
    db.commit()
    return get(db, receipt.revenue_entry_id)


def approve(db: Session, *, actor: User, entry_id: uuid.UUID, note: str | None) -> RevenueEntry:
    entry = get(db, entry_id, lock=True)
    _approve(db, entry, actor, note)
    db.commit()
    return entry


def reject(db: Session, *, actor: User, entry_id: uuid.UUID, reason: str) -> RevenueEntry:
    entry = get(db, entry_id, lock=True)
    _ensure_manual(entry)
    if active_receipts(entry):
        raise ConflictError("ألغِ المقبوضات المسجلة قبل رفض الإيراد", code="has_receipts")
    fc.reject(entry, actor, reason)
    audit.record(
        db,
        action=f"{ENTITY}.rejected",
        actor=actor,
        entity_type=ENTITY,
        entity_id=entry.id,
        reason=reason,
    )
    db.commit()
    return entry


def void_with_receipts(db: Session, entry: RevenueEntry, actor: User, reason: str) -> None:
    """Void an entry and everything received against it (caller commits)."""
    for receipt in active_receipts(entry):
        _void_receipt(db, receipt, actor, reason)
    fc.void(entry, actor, reason)
    audit.record(
        db,
        action=f"{ENTITY}.voided",
        actor=actor,
        entity_type=ENTITY,
        entity_id=entry.id,
        reason=reason,
    )


def void(db: Session, *, actor: User, entry_id: uuid.UUID, reason: str) -> RevenueEntry:
    entry = get(db, entry_id, lock=True)
    _ensure_manual(entry)
    if active_receipts(entry):
        raise ConflictError(
            "ألغِ المقبوضات المسجلة أولًا (أو استخدم التصحيح لنقلها)", code="has_receipts"
        )
    fc.void(entry, actor, reason)
    audit.record(
        db,
        action=f"{ENTITY}.voided",
        actor=actor,
        entity_type=ENTITY,
        entity_id=entry.id,
        reason=reason,
    )
    db.commit()
    return entry


def correct(
    db: Session,
    *,
    actor: User,
    entry_id: uuid.UUID,
    data: RevenueCorrection,
    can_approve: bool,
) -> RevenueEntry:
    """Replace an approved entry; its receipts move to the replacement."""
    original = get(db, entry_id, lock=True)
    _ensure_manual(original)
    fc.ensure_correctable(original)
    if data.kind is RevenueKind.RIDE_HAILING:
        raise field_error(
            "kind", "إيراد النقل الذكي يُسجل من كشوف المنصات فقط", code="use_statement"
        )
    receipts = active_receipts(original)
    fc.void(original, actor, f"تصحيح: {data.reason}")
    replacement = _new(db, actor=actor, data=data, corrects=original)
    for receipt in receipts:
        if receipt.received_by is ReceivedBy.DRIVER and replacement.driver_id != original.driver_id:
            raise field_error("driver_id", "توجد مقبوضات لدى السائق؛ لا يمكن تغيير السائق بالتصحيح")
        receipt.entry = replacement  # re-parent; the backref updates both collections
    if outstanding(replacement) < 0:
        raise field_error("amount", "المبلغ أقل من المقبوض فعلًا")
    audit.record(
        db,
        action=f"{ENTITY}.corrected",
        actor=actor,
        entity_type=ENTITY,
        entity_id=replacement.id,
        reason=data.reason,
        changes=audit.diff(audit.snapshot(original, AUDITED), audit.snapshot(replacement, AUDITED)),
        details={"corrects_id": original.id, "moved_receipts": [r.id for r in receipts]},
    )
    if data.approve_now and can_approve:
        _approve(db, replacement, actor, note="اعتماد التصحيح")
    db.commit()
    return get(db, replacement.id)


@dataclass(frozen=True)
class RevenueFilters:
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None
    kind: RevenueKind | None = None
    operation_type_id: uuid.UUID | None = None
    status: RecordStatus | None = None
    date_from: date | None = None
    date_to: date | None = None


def _filtered(f: RevenueFilters) -> Select[RevenueEntry]:
    stmt = select(RevenueEntry)
    if f.vehicle_id:
        stmt = stmt.where(RevenueEntry.vehicle_id == f.vehicle_id)
    if f.driver_id:
        stmt = stmt.where(RevenueEntry.driver_id == f.driver_id)
    if f.kind:
        stmt = stmt.where(RevenueEntry.kind == f.kind)
    if f.operation_type_id:
        stmt = stmt.where(RevenueEntry.operation_type_id == f.operation_type_id)
    if f.status:
        stmt = stmt.where(RevenueEntry.status == f.status)
    if f.date_from:
        stmt = stmt.where(RevenueEntry.occurred_on >= f.date_from)
    if f.date_to:
        stmt = stmt.where(RevenueEntry.occurred_on <= f.date_to)
    return stmt


def _received_subquery() -> Subquery:
    return (
        select(
            RevenueReceipt.revenue_entry_id.label("entry_id"),
            func.coalesce(func.sum(RevenueReceipt.amount), 0).label("received"),
            func.coalesce(
                func.sum(
                    case((RevenueReceipt.method == PaymentMethod.CASH.value, RevenueReceipt.amount))
                ),
                0,
            ).label("cash"),
        )
        .where(RevenueReceipt.voided_at.is_(None))
        .group_by(RevenueReceipt.revenue_entry_id)
        .subquery()
    )


def list_entries(
    db: Session, params: PageParams, filters: RevenueFilters, *, outstanding_only: bool = False
) -> tuple[list[RevenueEntry], int]:
    stmt = _filtered(filters).options(selectinload(RevenueEntry.receipts))
    if outstanding_only:
        rec = _received_subquery()
        stmt = (
            stmt.outerjoin(rec, rec.c.entry_id == RevenueEntry.id)
            .where(RevenueEntry.status != RecordStatus.VOIDED)
            .where(
                RevenueEntry.amount - RevenueEntry.fees_withheld - func.coalesce(rec.c.received, 0)
                > 0
            )
        )
    stmt = stmt.order_by(RevenueEntry.occurred_on.desc(), RevenueEntry.created_at.desc())
    return paginate(db, stmt, params)


def summary(db: Session, filters: RevenueFilters) -> dict[str, object]:
    base = _filtered(replace(filters, status=None)).subquery()
    rec = _received_subquery()
    approved = base.c.status == RecordStatus.APPROVED.value
    rows = db.execute(
        select(
            base.c.kind,
            func.coalesce(func.sum(base.c.amount), 0),
            func.coalesce(func.sum(base.c.fees_withheld), 0),
            func.coalesce(func.sum(rec.c.received), 0),
            func.coalesce(func.sum(rec.c.cash), 0),
        )
        .select_from(base)
        .outerjoin(rec, rec.c.entry_id == base.c.id)
        .where(approved)
        .group_by(base.c.kind)
    ).all()
    pending = db.scalar(
        select(func.count()).select_from(base).where(base.c.status == RecordStatus.SUBMITTED.value)
    )
    by_kind = {kind: Decimal(gross) for kind, gross, *_ in rows}
    gross = sum(by_kind.values(), ZERO)
    fees = sum((Decimal(r[2]) for r in rows), ZERO)
    received_total = sum((Decimal(r[3]) for r in rows), ZERO)
    cash = sum((Decimal(r[4]) for r in rows), ZERO)
    m = fc.money
    return {
        "by_kind": {k: m(v) for k, v in by_kind.items()},
        "gross_amount": m(gross),
        "fees_withheld": m(fees),
        "received_cash": m(cash),
        "received_electronic": m(received_total - cash),
        "outstanding_amount": m(gross - fees - received_total),
        "pending_count": pending or 0,
    }
