"""Fuel, CNG, oil and consumables ledger (Task 15).

Each fill or purchase is one transaction with its own type, so CNG and
gasoline for the same vehicle and day are separate rows, and engine oil
(a CONSUMABLE) never enters fuel-efficiency figures. Costs paid by the
driver become a reimbursement on the driver account once approved.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, field_error
from app.core.time import local_day_bounds_utc, to_local_date, utcnow
from app.models.driver import Driver
from app.models.finance import (
    FuelCategory,
    FuelTransaction,
    FuelType,
    LedgerEntryType,
    LedgerSource,
    PaidBy,
    RecordSource,
    RecordStatus,
)
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.finance import (
    DriverFuelCreate,
    FuelCorrection,
    FuelCreate,
    FuelTypeCreate,
    FuelTypeUpdate,
    FuelUpdate,
)
from app.services import audit, driver_ledger
from app.services import finance_common as fc
from app.services import shifts as shifts_service
from app.services.common import apply_changes, paginate

ENTITY = "fuel_transaction"
AUDITED = (
    "vehicle_id",
    "driver_id",
    "shift_id",
    "fuel_type_id",
    "quantity",
    "unit",
    "unit_price",
    "total_amount",
    "occurred_at",
    "odometer_km",
    "vendor",
    "payment_method",
    "paid_by",
    "notes",
)
# |quantity × unit price − total| tolerated before refusing the entry.
TOTAL_TOLERANCE = Decimal("0.50")


# --- Types ----------------------------------------------------------------------------


def list_types(db: Session, *, include_inactive: bool = False) -> list[FuelType]:
    stmt = select(FuelType).order_by(FuelType.sort_order, FuelType.code)
    if not include_inactive:
        stmt = stmt.where(FuelType.is_active.is_(True))
    return list(db.scalars(stmt).all())


def create_type(db: Session, *, actor: User, data: FuelTypeCreate) -> FuelType:
    if db.scalar(select(FuelType.id).where(FuelType.code == data.code)):
        raise field_error("code", "الرمز مستخدم بالفعل", code="duplicate_code")
    fuel_type = FuelType(**data.model_dump())
    db.add(fuel_type)
    db.flush()
    audit.record(
        db,
        action="fuel_type.created",
        actor=actor,
        entity_type="fuel_type",
        entity_id=fuel_type.id,
        details=data.model_dump(mode="json"),
    )
    db.commit()
    return fuel_type


def update_type(db: Session, *, actor: User, type_id: uuid.UUID, data: FuelTypeUpdate) -> FuelType:
    fuel_type = db.get(FuelType, type_id)
    if fuel_type is None:
        raise NotFoundError("نوع الوقود غير موجود")
    changes = apply_changes(
        fuel_type, data.model_dump(exclude_unset=True), ("name_ar", "is_active", "sort_order")
    )
    if changes:
        audit.record(
            db,
            action="fuel_type.updated",
            actor=actor,
            entity_type="fuel_type",
            entity_id=fuel_type.id,
            changes=changes,
        )
    db.commit()
    return fuel_type


# --- Transactions ----------------------------------------------------------------------


def get(db: Session, tx_id: uuid.UUID) -> FuelTransaction:
    tx = db.get(FuelTransaction, tx_id)
    if tx is None:
        raise NotFoundError("سجل الوقود غير موجود")
    return tx


def _active_type(db: Session, type_id: uuid.UUID) -> FuelType:
    fuel_type = db.get(FuelType, type_id)
    if fuel_type is None or not fuel_type.is_active:
        raise field_error("fuel_type_id", "نوع الوقود غير موجود أو غير مفعل")
    return fuel_type


def _settle_amounts(tx: FuelTransaction) -> None:
    """Fill or cross-check total vs quantity × unit price."""
    if tx.unit_price is not None:
        computed = fc.money(tx.quantity * tx.unit_price)
        if tx.total_amount is None:
            tx.total_amount = computed
        elif abs(computed - tx.total_amount) > TOTAL_TOLERANCE:
            raise field_error(
                "total_amount",
                f"الإجمالي لا يطابق الكمية × سعر الوحدة ({computed})",
                code="total_mismatch",
            )
    if tx.total_amount is None or tx.total_amount <= 0:
        raise field_error("total_amount", "أدخل الإجمالي")


def _validate(tx: FuelTransaction) -> None:
    fc.check_time(tx.occurred_at)
    if tx.paid_by is PaidBy.DRIVER and tx.driver_id is None:
        raise field_error("driver_id", "حدد السائق الذي دفع المبلغ")
    _settle_amounts(tx)


def _post_reimbursement(db: Session, tx: FuelTransaction, actor: User | None) -> None:
    if tx.paid_by is not PaidBy.DRIVER or tx.driver_id is None:
        return
    driver_ledger.post(
        db,
        driver_id=tx.driver_id,
        entry_type=LedgerEntryType.REIMBURSEMENT,
        amount=tx.total_amount,
        occurred_on=to_local_date(tx.occurred_at),
        description=f"تعويض {tx.fuel_type.name_ar} — {tx.vehicle.internal_code}",
        actor=actor,
        source_type=LedgerSource.FUEL,
        source_id=tx.id,
        vehicle_id=tx.vehicle_id,
    )


def _new(
    db: Session,
    *,
    actor: User,
    data: FuelCreate,
    source: RecordSource,
    corrects: FuelTransaction | None = None,
) -> FuelTransaction:
    vehicle, driver, shift, _ = fc.resolve_refs(
        db, vehicle_id=data.vehicle_id, driver_id=data.driver_id, shift_id=data.shift_id
    )
    fuel_type = _active_type(db, data.fuel_type_id)
    tx = FuelTransaction(
        vehicle_id=vehicle.id,
        driver_id=driver.id if driver else None,
        shift_id=shift.id if shift else None,
        fuel_type_id=fuel_type.id,
        quantity=data.quantity,
        unit=data.unit or fuel_type.default_unit,
        unit_price=data.unit_price,
        total_amount=data.total_amount,
        occurred_at=data.occurred_at,
        odometer_km=data.odometer_km,
        vendor=data.vendor,
        payment_method=data.payment_method,
        paid_by=data.paid_by,
        receipt_attachment_id=data.receipt_attachment_id,
        notes=data.notes,
        source=source,
        status=RecordStatus.SUBMITTED,
        created_by_id=actor.id,
        corrects_id=corrects.id if corrects else None,
    )
    tx.vehicle = vehicle
    tx.fuel_type = fuel_type
    _validate(tx)
    db.add(tx)
    db.flush()
    return tx


def create(
    db: Session, *, actor: User, data: FuelCreate, can_approve: bool = False
) -> FuelTransaction:
    tx = _new(db, actor=actor, data=data, source=RecordSource.ADMIN)
    audit.record(
        db,
        action=f"{ENTITY}.created",
        actor=actor,
        entity_type=ENTITY,
        entity_id=tx.id,
        changes=audit.diff({}, audit.snapshot(tx, AUDITED)),
    )
    if data.approve_now and can_approve:
        _approve(db, tx, actor, note="اعتماد عند الإدخال")
    db.commit()
    return tx


def create_from_driver(
    db: Session, *, actor: User, driver: Driver, data: DriverFuelCreate
) -> FuelTransaction:
    """Driver-app entry: always for the driver's active shift, always SUBMITTED."""
    shift = shifts_service.active_shift_for_driver(db, driver.id)
    if shift is None:
        raise ConflictError("سجّل الوقود أثناء وردية نشطة", code="no_active_shift")
    tx = _new(
        db,
        actor=actor,
        data=FuelCreate(
            vehicle_id=shift.vehicle_id,
            driver_id=driver.id,
            shift_id=shift.id,
            fuel_type_id=data.fuel_type_id,
            quantity=data.quantity,
            unit_price=data.unit_price,
            total_amount=data.total_amount,
            occurred_at=utcnow(),
            odometer_km=data.odometer_km,
            vendor=data.vendor,
            payment_method=data.payment_method,
            paid_by=data.paid_by,
            notes=data.notes,
        ),
        source=RecordSource.DRIVER_APP,
    )
    tx.latitude = data.latitude
    tx.longitude = data.longitude
    tx.location_accuracy_m = data.location_accuracy_m
    audit.record(
        db,
        action=f"{ENTITY}.created",
        actor=actor,
        entity_type=ENTITY,
        entity_id=tx.id,
        changes=audit.diff({}, audit.snapshot(tx, AUDITED)),
        details={"source": "DRIVER_APP"},
    )
    db.commit()
    return tx


def update(db: Session, *, actor: User, tx_id: uuid.UUID, data: FuelUpdate) -> FuelTransaction:
    tx = get(db, tx_id)
    fc.ensure_editable(tx)
    fields = data.model_dump(exclude_unset=True)
    if {"driver_id", "shift_id"} & fields.keys():
        _, driver, shift, _ = fc.resolve_refs(
            db,
            vehicle_id=tx.vehicle_id,
            driver_id=fields.get("driver_id", tx.driver_id),
            shift_id=fields.get("shift_id", tx.shift_id),
        )
        fields["driver_id"] = driver.id if driver else None
        fields["shift_id"] = shift.id if shift else None
    if "fuel_type_id" in fields:
        tx.fuel_type = _active_type(db, fields["fuel_type_id"])
    if "unit_price" in fields and "total_amount" not in fields:
        fields["total_amount"] = None  # recompute from the new price
    changes = apply_changes(tx, fields, AUDITED)
    _validate(tx)
    fc.resubmit_if_rejected(tx)
    if changes:
        audit.record(
            db,
            action=f"{ENTITY}.updated",
            actor=actor,
            entity_type=ENTITY,
            entity_id=tx.id,
            changes=changes,
        )
    db.commit()
    return tx


def _approve(db: Session, tx: FuelTransaction, actor: User, note: str | None) -> None:
    fc.approve(tx, actor, note)
    _post_reimbursement(db, tx, actor)
    audit.record(
        db,
        action=f"{ENTITY}.approved",
        actor=actor,
        entity_type=ENTITY,
        entity_id=tx.id,
        details={"note": note} if note else None,
    )


def approve(db: Session, *, actor: User, tx_id: uuid.UUID, note: str | None) -> FuelTransaction:
    tx = get(db, tx_id)
    _approve(db, tx, actor, note)
    db.commit()
    return tx


def reject(db: Session, *, actor: User, tx_id: uuid.UUID, reason: str) -> FuelTransaction:
    tx = get(db, tx_id)
    fc.reject(tx, actor, reason)
    audit.record(
        db,
        action=f"{ENTITY}.rejected",
        actor=actor,
        entity_type=ENTITY,
        entity_id=tx.id,
        reason=reason,
    )
    db.commit()
    return tx


def _void(db: Session, tx: FuelTransaction, actor: User, reason: str) -> None:
    previous = fc.void(tx, actor, reason)
    if previous is RecordStatus.APPROVED:
        driver_ledger.void_source(db, LedgerSource.FUEL, tx.id, actor, reason)
    audit.record(
        db,
        action=f"{ENTITY}.voided",
        actor=actor,
        entity_type=ENTITY,
        entity_id=tx.id,
        reason=reason,
    )


def void(db: Session, *, actor: User, tx_id: uuid.UUID, reason: str) -> FuelTransaction:
    tx = get(db, tx_id)
    _void(db, tx, actor, reason)
    db.commit()
    return tx


def correct(
    db: Session, *, actor: User, tx_id: uuid.UUID, data: FuelCorrection, can_approve: bool
) -> FuelTransaction:
    original = get(db, tx_id)
    fc.ensure_correctable(original)
    _void(db, original, actor, f"تصحيح: {data.reason}")
    replacement = _new(db, actor=actor, data=data, source=RecordSource.ADMIN, corrects=original)
    replacement.source = original.source
    replacement.latitude = original.latitude
    replacement.longitude = original.longitude
    replacement.location_accuracy_m = original.location_accuracy_m
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
class FuelFilters:
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None
    fuel_type_id: uuid.UUID | None = None
    category: FuelCategory | None = None
    status: RecordStatus | None = None
    date_from: date | None = None
    date_to: date | None = None


def _filtered(f: FuelFilters) -> Select[FuelTransaction]:
    stmt = select(FuelTransaction)
    if f.vehicle_id:
        stmt = stmt.where(FuelTransaction.vehicle_id == f.vehicle_id)
    if f.driver_id:
        stmt = stmt.where(FuelTransaction.driver_id == f.driver_id)
    if f.fuel_type_id:
        stmt = stmt.where(FuelTransaction.fuel_type_id == f.fuel_type_id)
    if f.category:
        stmt = stmt.join(FuelType, FuelType.id == FuelTransaction.fuel_type_id).where(
            FuelType.category == f.category
        )
    if f.status:
        stmt = stmt.where(FuelTransaction.status == f.status)
    if f.date_from:
        stmt = stmt.where(FuelTransaction.occurred_at >= local_day_bounds_utc(f.date_from)[0])
    if f.date_to:
        stmt = stmt.where(FuelTransaction.occurred_at < local_day_bounds_utc(f.date_to)[1])
    return stmt


def list_transactions(
    db: Session, params: PageParams, filters: FuelFilters
) -> tuple[list[FuelTransaction], int]:
    stmt = _filtered(filters).order_by(
        FuelTransaction.occurred_at.desc(), FuelTransaction.created_at.desc()
    )
    return paginate(db, stmt, params)


def summary(db: Session, filters: FuelFilters) -> dict[str, object]:
    """Approved totals per type for the filtered set, plus the pending count."""
    base = _filtered(replace(filters, status=None)).subquery()
    rows = db.execute(
        select(
            base.c.fuel_type_id,
            func.count(),
            func.coalesce(func.sum(base.c.quantity), 0),
            func.coalesce(func.sum(base.c.total_amount), 0),
        )
        .where(base.c.status == RecordStatus.APPROVED.value)
        .group_by(base.c.fuel_type_id)
    ).all()
    pending = db.scalar(
        select(func.count()).select_from(base).where(base.c.status == RecordStatus.SUBMITTED.value)
    )
    types = {t.id: t for t in list_types(db, include_inactive=True)}
    by_type: list[dict[str, object]] = []
    fuel_amount = consumables_amount = Decimal("0")
    for type_id, count, quantity, total in sorted(
        rows, key=lambda r: (types[r[0]].sort_order, types[r[0]].code)
    ):
        fuel_type = types[type_id]
        by_type.append(
            {
                "fuel_type": fuel_type,
                "count": count,
                "quantity": Decimal(quantity),
                "total_amount": Decimal(total),
            }
        )
        if fuel_type.category is FuelCategory.FUEL:
            fuel_amount += Decimal(total)
        else:
            consumables_amount += Decimal(total)
    return {
        "by_type": by_type,
        "fuel_amount": fc.money(fuel_amount),
        "consumables_amount": fc.money(consumables_amount),
        "pending_count": pending or 0,
    }
