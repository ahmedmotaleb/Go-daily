"""End-of-shift close-outs, cash collections and the driver's cash account.

Money flow, kept consistent with the driver ledger:

- the collection becomes a revenue entry with a receipt held by the driver
  (ledger: CASH_COLLECTED, the driver holds company money);
- fuel, toll and maintenance paid from that cash become driver-paid fuel and
  expense records (ledger: REIMBURSEMENT once the office approves them);
- what a manager receives is a cash collection (ledger: CASH_HANDOVER).

The amount to hand over for a close-out is the declared collection less the
expense lines the office has not rejected or voided (corrections are
followed to the live record). Whatever is not collected carries over.
Nothing is estimated: every figure comes from recorded data.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailed, field_error
from app.core.time import local_day_bounds_utc, local_today, to_local_date, utcnow
from app.models.attachment import Attachment, AttachmentOwner
from app.models.cash import CashCollection, MaintenanceKind, ShiftCloseout
from app.models.driver import Driver
from app.models.finance import (
    Expense,
    ExpenseCategory,
    FuelTransaction,
    FuelType,
    LedgerEntryType,
    LedgerSource,
    PaidBy,
    PaymentMethod,
    ReceivedBy,
    RecordSource,
    RecordStatus,
    RevenueEntry,
    RevenueKind,
)
from app.models.operations import OperationKind
from app.models.shift import OperationSession, SessionStatus, Shift, ShiftSource, ShiftStatus
from app.models.user import User
from app.schemas.cash import CloseoutIn, CloseoutStatus
from app.schemas.finance import ExpenseCreate, FuelCreate, ReceiptIn, RevenueFields
from app.schemas.shift import ShiftEnd
from app.services import audit, driver_ledger, expenses, fuel, revenue
from app.services import finance_common as fc
from app.services import shifts as shifts_service

ZERO = Decimal("0")
ENTITY = "shift_closeout"
LineKey = Literal["gas", "gasoline", "toll", "maintenance"]
UNIT_AR = {"CUBIC_METER": "م³", "LITER": "لتر", "KG": "كجم", "UNIT": "وحدة"}
REVENUE_KIND: dict[OperationKind, RevenueKind | None] = {
    OperationKind.FIXED_ROUTE: RevenueKind.FIXED_ROUTE_COLLECTION,
    OperationKind.PRIVATE_TRIP: RevenueKind.PRIVATE_TRIP,
    # Ride-hailing revenue comes from platform statements only (no double counting).
    OperationKind.RIDE_HAILING: None,
}


# --- Reading close-outs -----------------------------------------------------------


@dataclass
class Line:
    key: LineKey
    label: str
    quantity: Decimal | None
    unit: str | None
    amount: Decimal
    record_status: RecordStatus | None
    deducted: bool


@dataclass
class Figures:
    lines: list[Line]
    deductions: Decimal
    net: Decimal
    collection_booked: bool


@dataclass
class Position:
    """Where a close-out stands in the driver's running cash account."""

    carried_before: Decimal = ZERO
    total_due: Decimal = ZERO
    collected: Decimal = ZERO
    remaining: Decimal = ZERO
    status: CloseoutStatus = "WAITING"


@dataclass
class DriverView:
    outstanding: Decimal = ZERO
    figures: dict[uuid.UUID, Figures] = field(default_factory=dict)
    positions: dict[uuid.UUID, Position] = field(default_factory=dict)
    collections: dict[uuid.UUID | None, list[CashCollection]] = field(default_factory=dict)


def _live_versions(db: Session, model: Any, wanted: set[uuid.UUID | None]) -> dict[uuid.UUID, Any]:
    """For each record id, its live version: corrections are followed to the newest record."""
    ids = {i for i in wanted if i is not None}
    if not ids:
        return {}
    records = {r.id: r for r in db.scalars(select(model).where(model.id.in_(ids))).all()}
    result: dict[uuid.UUID, Any] = dict(records)
    pending = {i: r for i, r in records.items() if r.status is RecordStatus.VOIDED}
    for _ in range(10):  # correction chains are short; bounded for safety
        if not pending:
            break
        voided = {r.id: origin for origin, r in pending.items()}
        successors = db.scalars(select(model).where(model.corrects_id.in_(voided))).all()
        pending = {}
        for s in successors:
            origin = voided[s.corrects_id]
            result[origin] = s
            if s.status is RecordStatus.VOIDED:
                pending[origin] = s
    return result


def _figures(
    closeouts: list[ShiftCloseout],
    fuels: dict[uuid.UUID, FuelTransaction],
    costs: dict[uuid.UUID, Expense],
) -> dict[uuid.UUID, Figures]:
    out: dict[uuid.UUID, Figures] = {}
    for c in closeouts:
        lines: list[Line] = []
        specs: list[tuple[LineKey, str, Decimal | None, uuid.UUID | None, Decimal, Any]] = [
            ("gas", "غاز", c.gas_quantity, c.gas_fuel_id, c.gas_amount, fuels),
            (
                "gasoline",
                "بنزين",
                c.gasoline_quantity,
                c.gasoline_fuel_id,
                c.gasoline_amount,
                fuels,
            ),
            ("toll", "الكارتة", None, c.toll_expense_id, c.toll_amount, costs),
            (
                "maintenance",
                "تغيير زيت" if c.maintenance_kind is MaintenanceKind.OIL_CHANGE else "صيانة",
                None,
                c.maintenance_expense_id,
                c.maintenance_amount,
                costs,
            ),
        ]
        for key, label, declared_qty, record_id, declared, pool in specs:
            record = pool.get(record_id) if record_id else None
            amount, qty, unit = declared, declared_qty, None
            if isinstance(record, FuelTransaction):
                amount, qty, unit = record.total_amount, record.quantity, UNIT_AR[record.unit.value]
            elif isinstance(record, Expense):
                amount = record.amount
            lines.append(
                Line(
                    key=key,
                    label=label,
                    quantity=qty,
                    unit=unit,
                    amount=amount,
                    record_status=record.status if record is not None else None,
                    deducted=record is not None
                    and record.status in (RecordStatus.SUBMITTED, RecordStatus.APPROVED),
                )
            )
        deductions = sum((ln.amount for ln in lines if ln.deducted), ZERO)
        out[c.id] = Figures(
            lines=lines,
            deductions=fc.money(deductions),
            net=fc.money(c.collection_amount - deductions),
            collection_booked=c.revenue_entry_id is not None or c.collection_amount == 0,
        )
    return out


def _status(total_due: Decimal, collected: Decimal, remaining: Decimal) -> CloseoutStatus:
    if total_due <= 0:
        return "NOTHING_DUE"
    if collected == 0:
        return "WAITING"
    return "COLLECTED" if remaining <= 0 else "PARTIAL"


def driver_views(db: Session, driver_ids: set[uuid.UUID]) -> dict[uuid.UUID, DriverView]:
    """Every live close-out and collection of these drivers, walked in order."""
    views = {d: DriverView() for d in driver_ids}
    if not driver_ids:
        return views
    closeouts = list(
        db.scalars(
            select(ShiftCloseout)
            .where(ShiftCloseout.driver_id.in_(driver_ids), ShiftCloseout.voided_at.is_(None))
            .order_by(ShiftCloseout.service_date, ShiftCloseout.submitted_at)
        ).all()
    )
    collections = db.scalars(
        select(CashCollection)
        .where(CashCollection.driver_id.in_(driver_ids), CashCollection.voided_at.is_(None))
        .order_by(CashCollection.collected_at)
    ).all()
    fuels = _live_versions(
        db,
        FuelTransaction,
        {i for c in closeouts for i in (c.gas_fuel_id, c.gasoline_fuel_id) if i},
    )
    costs = _live_versions(
        db,
        Expense,
        {i for c in closeouts for i in (c.toll_expense_id, c.maintenance_expense_id) if i},
    )
    figures = _figures(closeouts, fuels, costs)
    for col in collections:
        views[col.driver_id].collections.setdefault(col.closeout_id, []).append(col)
    for c in closeouts:
        views[c.driver_id].figures[c.id] = figures[c.id]

    by_driver: dict[uuid.UUID, list[ShiftCloseout]] = defaultdict(list)
    for c in closeouts:
        by_driver[c.driver_id].append(c)
    for driver_id, view in views.items():
        standalone = list(view.collections.get(None, []))
        carry = ZERO
        for c in by_driver.get(driver_id, []):
            while standalone and standalone[0].collected_at < c.submitted_at:
                carry -= standalone.pop(0).amount
            net = view.figures[c.id].net
            collected = sum((x.amount for x in view.collections.get(c.id, [])), ZERO)
            total = carry + net
            remaining = total - collected
            view.positions[c.id] = Position(
                carried_before=fc.money(carry),
                total_due=fc.money(total),
                collected=fc.money(collected),
                remaining=fc.money(remaining),
                status=_status(total, collected, remaining),
            )
            carry = remaining
        nets = sum((view.figures[c.id].net for c in by_driver.get(driver_id, [])), ZERO)
        paid = sum((x.amount for xs in view.collections.values() for x in xs), ZERO)
        view.outstanding = fc.money(nets - paid)
    return views


def outstanding(db: Session, driver_id: uuid.UUID) -> Decimal:
    return driver_views(db, {driver_id})[driver_id].outstanding


def live_closeout(db: Session, shift_id: uuid.UUID) -> ShiftCloseout | None:
    return db.scalar(
        select(ShiftCloseout).where(
            ShiftCloseout.shift_id == shift_id, ShiftCloseout.voided_at.is_(None)
        )
    )


def get_closeout(db: Session, closeout_id: uuid.UUID) -> ShiftCloseout:
    closeout = db.get(ShiftCloseout, closeout_id)
    if closeout is None:
        raise NotFoundError("التقفيل غير موجود")
    return closeout


def receipt_ids(db: Session, closeout_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    out: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    if not closeout_ids:
        return out
    for a in db.scalars(
        select(Attachment)
        .where(
            Attachment.owner_type == AttachmentOwner.SHIFT_CLOSEOUT,
            Attachment.owner_id.in_(closeout_ids),
            Attachment.deleted_at.is_(None),
        )
        .order_by(Attachment.created_at)
    ).all():
        out[a.owner_id].append(a.id)
    return out


def main_session(shift: Shift) -> OperationSession | None:
    """The session that ran longest (the shift's main operation)."""
    now = utcnow()
    sessions = [s for s in shift.sessions if s.status is not SessionStatus.CANCELLED]
    if not sessions:
        return None
    return max(sessions, key=lambda s: (s.ended_at or now) - s.started_at)


def operation_label(shift: Shift) -> str:
    session = main_session(shift)
    if session is not None:
        name = session.operation_type.name_ar
        return f"{name} · {session.route.name}" if session.route else name
    if shift.planned_operation_type is not None:
        return shift.planned_operation_type.name_ar
    return "بدون تشغيل محدد"


def _locked[M](db: Session, model: type[M], record_id: uuid.UUID) -> M | None:
    """Row lock by id only (FOR UPDATE cannot cover the eager outer joins)."""
    id_column = cast(Any, model).id
    found = db.scalar(select(id_column).where(id_column == record_id).with_for_update())
    return db.get(model, found) if found is not None else None


# --- Submitting a close-out -------------------------------------------------------


@dataclass
class _Refs:
    cng: FuelType | None
    gasoline: FuelType | None
    toll: ExpenseCategory | None
    maintenance: ExpenseCategory | None


def _validate(data: CloseoutIn) -> None:
    for prefix, label in (("gas", "الغاز"), ("gasoline", "البنزين")):
        amount: Decimal = getattr(data, f"{prefix}_amount")
        qty: Decimal | None = getattr(data, f"{prefix}_quantity")
        if amount > 0 and (qty is None or qty <= 0):
            raise field_error(f"{prefix}_quantity", f"أدخل كمية {label}", code="quantity_required")
        if amount == 0 and qty:
            raise field_error(f"{prefix}_amount", f"أدخل مبلغ {label}", code="amount_required")
    if data.maintenance_kind is MaintenanceKind.NONE:
        if data.maintenance_amount > 0:
            raise field_error("maintenance_kind", "حدد نوع الصيانة", code="maintenance_kind")
    else:
        if data.maintenance_amount <= 0:
            raise field_error("maintenance_amount", "أدخل تكلفة الصيانة", code="amount_required")
        if not (data.maintenance_note or "").strip():
            raise field_error(
                "maintenance_note", "اكتب ما الذي تم في الصيانة", code="maintenance_note_required"
            )


def _refs(db: Session, data: CloseoutIn) -> _Refs:
    def fuel_type(code: str) -> FuelType | None:
        return db.scalar(select(FuelType).where(FuelType.code == code, FuelType.is_active))

    def category(code: str) -> ExpenseCategory | None:
        return db.scalar(
            select(ExpenseCategory).where(ExpenseCategory.code == code, ExpenseCategory.is_active)
        )

    refs = _Refs(
        cng=fuel_type("CNG") if data.gas_amount > 0 else None,
        gasoline=fuel_type("GASOLINE") if data.gasoline_amount > 0 else None,
        toll=category("TOLL") if data.toll_amount > 0 else None,
        maintenance=(
            category(
                "OIL_CHANGE" if data.maintenance_kind is MaintenanceKind.OIL_CHANGE else "REPAIR"
            )
            if data.maintenance_kind is not MaintenanceKind.NONE
            else None
        ),
    )
    missing = [
        name
        for name, needed, ref in (
            ("الغاز", data.gas_amount > 0, refs.cng),
            ("البنزين", data.gasoline_amount > 0, refs.gasoline),
            ("الكارتة", data.toll_amount > 0, refs.toll),
            ("الصيانة", data.maintenance_kind is not MaintenanceKind.NONE, refs.maintenance),
        )
        if needed and ref is None
    ]
    if missing:
        raise ValidationFailed(
            "أنواع غير مفعّلة في النظام: " + "، ".join(missing), code="reference_missing"
        )
    return refs


def _book_collection(
    db: Session, *, actor: User, shift: Shift, amount: Decimal, at: datetime, source: RecordSource
) -> RevenueEntry | None:
    session = main_session(shift)
    op_type = session.operation_type if session else shift.planned_operation_type
    kind = REVENUE_KIND.get(op_type.kind, RevenueKind.OTHER) if op_type else RevenueKind.OTHER
    if amount <= 0 or kind is None:
        return None
    entry = revenue._new(
        db,
        actor=actor,
        data=RevenueFields(
            kind=kind,
            vehicle_id=shift.vehicle_id,
            driver_id=shift.driver_id,
            shift_id=shift.id,
            session_id=session.id if session else None,
            operation_type_id=op_type.id if op_type else None,
            occurred_on=to_local_date(shift.started_at or at),
            amount=amount,
            notes="تحصيل من تقفيل الوردية",
        ),
        source=source,
    )
    audit.record(
        db,
        action="revenue_entry.created",
        actor=actor,
        entity_type="revenue_entry",
        entity_id=entry.id,
        details={"source": source.value, "from": ENTITY},
    )
    revenue.add_receipt_to(
        db,
        entry,
        ReceiptIn(
            amount=amount,
            received_at=at,
            method=PaymentMethod.CASH,
            received_by=ReceivedBy.DRIVER,
            notes="لدى السائق حتى التسليم للإدارة",
        ),
        actor,
    )
    return entry


def _book_fuel(
    db: Session,
    *,
    actor: User,
    shift: Shift,
    fuel_type: FuelType,
    quantity: Decimal,
    amount: Decimal,
    at: datetime,
    source: RecordSource,
) -> FuelTransaction:
    tx = fuel._new(
        db,
        actor=actor,
        data=FuelCreate(
            vehicle_id=shift.vehicle_id,
            driver_id=shift.driver_id,
            shift_id=shift.id,
            fuel_type_id=fuel_type.id,
            quantity=quantity,
            total_amount=amount,
            occurred_at=at,
            payment_method=PaymentMethod.CASH,
            paid_by=PaidBy.DRIVER,
            notes="من تقفيل الوردية",
        ),
        source=source,
    )
    audit.record(
        db,
        action="fuel_transaction.created",
        actor=actor,
        entity_type="fuel_transaction",
        entity_id=tx.id,
        details={"source": source.value, "from": ENTITY},
    )
    return tx


def _book_expense(
    db: Session,
    *,
    actor: User,
    shift: Shift,
    category: ExpenseCategory,
    amount: Decimal,
    at: datetime,
    notes: str,
    source: RecordSource,
) -> Expense:
    expense = expenses._new(
        db,
        actor=actor,
        data=ExpenseCreate(
            vehicle_id=shift.vehicle_id,
            driver_id=shift.driver_id,
            shift_id=shift.id,
            category_id=category.id,
            amount=amount,
            occurred_at=at,
            payment_method=PaymentMethod.CASH,
            paid_by=PaidBy.DRIVER,
            notes=notes,
        ),
    )
    expense.source = source
    audit.record(
        db,
        action="expense.created",
        actor=actor,
        entity_type="expense",
        entity_id=expense.id,
        details={"source": source.value, "from": ENTITY},
    )
    return expense


def _end_or_check(
    db: Session, *, actor: User, shift: Shift, data: CloseoutIn, source: RecordSource
) -> None:
    if shift.status is ShiftStatus.ACTIVE:
        shifts_service.end_shift(
            db,
            actor=actor,
            shift_id=shift.id,
            data=ShiftEnd(end_odometer_km=data.end_odometer_km),
            source=ShiftSource.DRIVER_APP
            if source is RecordSource.DRIVER_APP
            else ShiftSource.ADMIN,
            commit=False,
        )
    elif shift.status is ShiftStatus.COMPLETED:
        if shift.end_odometer_km is not None and data.end_odometer_km != shift.end_odometer_km:
            raise field_error(
                "end_odometer_km",
                f"القراءة تختلف عن عداد إنهاء الوردية ({shift.end_odometer_km} كم)؛ "
                "صحّحها من صفحة الوردية أولًا",
                code="end_odometer_mismatch",
            )
    else:
        raise ConflictError("لا يمكن تقفيل وردية لم تبدأ أو ملغاة", code="invalid_shift_state")


def submit(
    db: Session,
    *,
    actor: User,
    shift_id: uuid.UUID,
    data: CloseoutIn,
    source: RecordSource,
    driver_id: uuid.UUID | None = None,
) -> ShiftCloseout:
    """End the shift if still running and record its close-out, atomically.

    `driver_id` scopes the call to the driver's own shifts (driver app).
    """
    shift = shifts_service.get_shift(db, shift_id, for_update=True)
    if driver_id is not None and shift.driver_id != driver_id:
        raise NotFoundError("الوردية غير موجودة")
    live = live_closeout(db, shift.id)
    if live is not None:
        # The phone resending a close-out it queued (lost response, long
        # offline): the same entry, recognised by its client id (U45).
        if data.client_entry_id and live.client_entry_id == data.client_entry_id:
            return live
        raise ConflictError("تم إرسال تقفيل هذه الوردية بالفعل", code="already_closed_out")
    _validate(data)
    refs = _refs(db, data)
    _end_or_check(db, actor=actor, shift=shift, data=data, source=source)
    assert shift.started_at is not None and shift.end_odometer_km is not None  # noqa: S101
    at = shift.ended_at or utcnow()

    closeout = ShiftCloseout(
        shift_id=shift.id,
        driver_id=shift.driver_id,
        vehicle_id=shift.vehicle_id,
        service_date=to_local_date(shift.started_at),
        submitted_at=utcnow(),
        source=source,
        end_odometer_km=shift.end_odometer_km,
        collection_amount=data.collection_amount,
        gas_quantity=data.gas_quantity if data.gas_amount > 0 else None,
        gas_amount=data.gas_amount,
        gasoline_quantity=data.gasoline_quantity if data.gasoline_amount > 0 else None,
        gasoline_amount=data.gasoline_amount,
        toll_amount=data.toll_amount,
        maintenance_kind=data.maintenance_kind,
        maintenance_amount=data.maintenance_amount,
        maintenance_note=(data.maintenance_note or "").strip() or None,
        notes=(data.notes or "").strip() or None,
        client_entry_id=data.client_entry_id,
        device_recorded_at=data.recorded_at,
        created_by_id=actor.id,
    )
    entry = _book_collection(
        db, actor=actor, shift=shift, amount=data.collection_amount, at=at, source=source
    )
    closeout.revenue_entry_id = entry.id if entry else None
    common: dict[str, Any] = {"actor": actor, "shift": shift, "at": at, "source": source}
    if refs.cng is not None and data.gas_quantity:
        gas = _book_fuel(
            db, fuel_type=refs.cng, quantity=data.gas_quantity, amount=data.gas_amount, **common
        )
        closeout.gas_fuel_id = gas.id
    if refs.gasoline is not None and data.gasoline_quantity:
        gasoline = _book_fuel(
            db,
            fuel_type=refs.gasoline,
            quantity=data.gasoline_quantity,
            amount=data.gasoline_amount,
            **common,
        )
        closeout.gasoline_fuel_id = gasoline.id
    if refs.toll is not None:
        toll = _book_expense(
            db,
            category=refs.toll,
            amount=data.toll_amount,
            notes="الكارتة — من تقفيل الوردية",
            **common,
        )
        closeout.toll_expense_id = toll.id
    if refs.maintenance is not None:
        upkeep = _book_expense(
            db,
            category=refs.maintenance,
            amount=data.maintenance_amount,
            notes=closeout.maintenance_note or "",
            **common,
        )
        closeout.maintenance_expense_id = upkeep.id
    db.add(closeout)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise ConflictError("تم إرسال تقفيل هذه الوردية بالفعل", code="already_closed_out") from exc
    audit.record(
        db,
        action=f"{ENTITY}.submitted",
        actor=actor,
        entity_type="shift",
        entity_id=shift.id,
        details={
            "closeout_id": closeout.id,
            "source": source.value,
            "collection": data.collection_amount,
            "gas": data.gas_amount,
            "gasoline": data.gasoline_amount,
            "toll": data.toll_amount,
            "maintenance": data.maintenance_amount,
            "maintenance_kind": data.maintenance_kind.value,
        },
    )
    db.commit()
    return closeout


def void_closeout(
    db: Session, *, actor: User, closeout_id: uuid.UUID, reason: str
) -> ShiftCloseout:
    """Void a close-out and the finance records it created; the shift stays ended."""
    closeout = _locked(db, ShiftCloseout, closeout_id)
    if closeout is None or closeout.voided_at is not None:
        raise NotFoundError("التقفيل غير موجود أو ملغي")
    has_collections = db.scalar(
        select(CashCollection.id).where(
            CashCollection.closeout_id == closeout.id, CashCollection.voided_at.is_(None)
        )
    )
    if has_collections is not None:
        raise ConflictError(
            "ألغِ التحصيلات المسجلة على هذا التقفيل أولًا", code="closeout_has_collections"
        )
    note = f"إلغاء تقفيل الوردية: {reason}"
    # Void the live version of each record (an office correction replaces the original).
    entries = _live_versions(db, RevenueEntry, {closeout.revenue_entry_id})
    for entry in entries.values():
        if entry.status is not RecordStatus.VOIDED:
            revenue.void_with_receipts(db, entry, actor, note)
    fuel_ids = {closeout.gas_fuel_id, closeout.gasoline_fuel_id}
    for tx in _live_versions(db, FuelTransaction, fuel_ids).values():
        if tx.status is not RecordStatus.VOIDED:
            fuel._void(db, tx, actor, note)
    expense_ids = {closeout.toll_expense_id, closeout.maintenance_expense_id}
    for expense in _live_versions(db, Expense, expense_ids).values():
        if expense.status is not RecordStatus.VOIDED:
            expenses._void(db, expense, actor, note)
    closeout.voided_at = utcnow()
    closeout.voided_by_id = actor.id
    closeout.void_reason = reason
    audit.record(
        db,
        action=f"{ENTITY}.voided",
        actor=actor,
        entity_type="shift",
        entity_id=closeout.shift_id,
        reason=reason,
        details={"closeout_id": closeout.id},
    )
    db.commit()
    return closeout


# --- Collections ------------------------------------------------------------------


def collect(
    db: Session,
    *,
    actor: User,
    driver_id: uuid.UUID,
    amount: Decimal,
    closeout_id: uuid.UUID | None,
    note: str | None,
) -> CashCollection:
    """Record cash a manager actually received from the driver."""
    # Lock the driver row so two collections cannot both pass the balance check.
    driver = _locked(db, Driver, driver_id)
    if driver is None:
        raise NotFoundError("السائق غير موجود")
    closeout = None
    if closeout_id is not None:
        closeout = db.get(ShiftCloseout, closeout_id)
        if closeout is None or closeout.voided_at is not None or closeout.driver_id != driver.id:
            raise field_error("closeout_id", "التقفيل غير موجود لهذا السائق")
    balance = outstanding(db, driver.id)
    if amount > balance:
        raise field_error(
            "amount",
            f"المبلغ أكبر من المستحق على السائق ({balance} ج.م)"
            if balance > 0
            else "لا يوجد مبلغ مستحق على السائق",
            code="over_collection",
        )
    now = utcnow()
    collection = CashCollection(
        driver_id=driver.id,
        closeout_id=closeout.id if closeout else None,
        amount=amount,
        collected_at=now,
        note=(note or "").strip() or None,
        collected_by_id=actor.id,
    )
    db.add(collection)
    db.flush()
    driver_ledger.post(
        db,
        driver_id=driver.id,
        entry_type=LedgerEntryType.CASH_HANDOVER,
        amount=amount,
        occurred_on=to_local_date(now),
        description="تسليم نقدية للإدارة",
        actor=actor,
        source_type=LedgerSource.CASH_COLLECTION,
        source_id=collection.id,
        vehicle_id=closeout.vehicle_id if closeout else None,
    )
    audit.record(
        db,
        action="cash_collection.recorded",
        actor=actor,
        entity_type="driver",
        entity_id=driver.id,
        details={
            "collection_id": collection.id,
            "closeout_id": collection.closeout_id,
            "amount": amount,
            "balance_before": balance,
        },
    )
    db.commit()
    return collection


def void_collection(
    db: Session, *, actor: User, collection_id: uuid.UUID, reason: str
) -> CashCollection:
    collection = _locked(db, CashCollection, collection_id)
    if collection is None or collection.voided_at is not None:
        raise NotFoundError("التحصيل غير موجود أو ملغي")
    collection.voided_at = utcnow()
    collection.voided_by_id = actor.id
    collection.void_reason = reason
    driver_ledger.void_source(db, LedgerSource.CASH_COLLECTION, collection.id, actor, reason)
    audit.record(
        db,
        action="cash_collection.voided",
        actor=actor,
        entity_type="driver",
        entity_id=collection.driver_id,
        reason=reason,
        details={"collection_id": collection.id, "amount": collection.amount},
    )
    db.commit()
    return collection


def collected_between(db: Session, start: datetime, end: datetime) -> Decimal:
    rows = db.scalars(
        select(CashCollection.amount).where(
            CashCollection.voided_at.is_(None),
            CashCollection.collected_at >= start,
            CashCollection.collected_at < end,
        )
    ).all()
    return fc.money(sum(rows, ZERO))


def closeouts_on(db: Session, day: date) -> list[ShiftCloseout]:
    return list(
        db.scalars(
            select(ShiftCloseout)
            .where(ShiftCloseout.service_date == day, ShiftCloseout.voided_at.is_(None))
            .order_by(ShiftCloseout.submitted_at)
        ).all()
    )


def shifts_without_closeout(db: Session, day: date) -> list[Shift]:
    """Shifts started that day that are running, or ended without a close-out."""
    start, end = local_day_bounds_utc(day)
    closed = select(ShiftCloseout.shift_id).where(ShiftCloseout.voided_at.is_(None))
    return list(
        db.scalars(
            select(Shift)
            .where(
                Shift.status.in_((ShiftStatus.ACTIVE, ShiftStatus.COMPLETED)),
                Shift.started_at >= start,
                Shift.started_at < end,
                Shift.id.not_in(closed),
            )
            .order_by(Shift.started_at)
        ).all()
    )


def account_window(days: int) -> tuple[date, date]:
    today = local_today()
    return today - timedelta(days=max(1, days) - 1), today


__all__ = [
    "DriverView",
    "Figures",
    "Position",
    "account_window",
    "closeouts_on",
    "collect",
    "collected_between",
    "driver_views",
    "get_closeout",
    "live_closeout",
    "main_session",
    "operation_label",
    "outstanding",
    "receipt_ids",
    "shifts_without_closeout",
    "submit",
    "void_closeout",
    "void_collection",
]
