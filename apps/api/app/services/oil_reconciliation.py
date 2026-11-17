"""Oil and service reconciliation (U17).

Buying oil is not changing it. Purchases of oil and other consumables are
fuel-ledger records; the service that used them is a maintenance record
that may link to the purchase and state the quantity put in. This view puts
the three sources side by side for a period:

- purchases of consumables, with the services linked to them and how much
  of each purchase they used;
- services whose type uses a consumable (the oil change), with what is
  missing: the quantity, or any purchase or parts cost;
- oil-change expenses a driver recorded at close-out, with whether a service
  record exists for the same vehicle within a few days.

Everything listed is "to check" («مراجعة مطلوبة» at most), never a finding:
a missing link is often just an entry not done yet.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_day_bounds_utc, to_local_date
from app.models.finance import (
    Expense,
    ExpenseCategory,
    FuelCategory,
    FuelTransaction,
    FuelType,
    RecordStatus,
)
from app.models.maintenance import MaintenanceRecord, MaintenanceType

LIVE = (RecordStatus.SUBMITTED, RecordStatus.APPROVED)
OIL_CHANGE_EXPENSE = "OIL_CHANGE"
# A field oil-change expense matches a service record this close in days.
MATCH_DAYS = 3

PURCHASE_STATUS = {
    "NOT_LINKED": "غير مرتبط بخدمة",
    "OVER_USED": "الكمية المستخدمة أكبر من المشتراة — مراجعة مطلوبة",
    "PARTLY_USED": "مستخدم جزئيًا",
    "USED": "مرتبط بخدمة",
}
SERVICE_STATUS = {
    "NO_QUANTITY": "الكمية غير مسجلة",
    "NO_PURCHASE": "بدون شراء مرتبط أو تكلفة قطع",
    "OK": "مكتمل",
}
EXPENSE_STATUS = {
    "NO_SERVICE": "مصروف تغيير زيت بدون سجل صيانة",
    "MATCHED": "له سجل صيانة",
}


@dataclass
class PurchaseRow:
    id: uuid.UUID
    vehicle: str
    vehicle_id: uuid.UUID
    day: date
    item: str
    quantity: Decimal
    unit: str
    total_amount: Decimal
    used: Decimal | None
    services: list[uuid.UUID]
    status: str
    label: str


@dataclass
class ServiceRow:
    id: uuid.UUID
    vehicle: str
    vehicle_id: uuid.UUID
    day: date
    service: str
    quantity: Decimal | None
    spec: str | None
    purchase_id: uuid.UUID | None
    parts_cost: Decimal
    next_due_km: int | None
    next_due_on: date | None
    status: str
    label: str


@dataclass
class ExpenseRow:
    id: uuid.UUID
    vehicle: str
    vehicle_id: uuid.UUID
    day: date
    amount: Decimal
    service_id: uuid.UUID | None
    status: str
    label: str


@dataclass
class Report:
    date_from: date
    date_to: date
    purchases: list[PurchaseRow] = field(default_factory=list)
    services: list[ServiceRow] = field(default_factory=list)
    expenses: list[ExpenseRow] = field(default_factory=list)
    to_check: int = 0


def _purchases(
    db: Session, start: object, end: object, vehicle_id: uuid.UUID | None
) -> list[FuelTransaction]:
    stmt = (
        select(FuelTransaction)
        .join(FuelType, FuelType.id == FuelTransaction.fuel_type_id)
        .where(
            FuelType.category == FuelCategory.CONSUMABLE,
            FuelTransaction.status.in_(LIVE),
            FuelTransaction.occurred_at >= start,
            FuelTransaction.occurred_at < end,
        )
        .order_by(FuelTransaction.occurred_at)
    )
    if vehicle_id:
        stmt = stmt.where(FuelTransaction.vehicle_id == vehicle_id)
    return list(db.scalars(stmt).all())


def _purchase_rows(db: Session, purchases: list[FuelTransaction]) -> list[PurchaseRow]:
    links: dict[uuid.UUID, list[MaintenanceRecord]] = defaultdict(list)
    if purchases:
        for r in db.scalars(
            select(MaintenanceRecord).where(
                MaintenanceRecord.fuel_transaction_id.in_([p.id for p in purchases]),
                MaintenanceRecord.status.in_(LIVE),
            )
        ).all():
            assert r.fuel_transaction_id is not None  # noqa: S101
            links[r.fuel_transaction_id].append(r)
    rows = []
    for p in purchases:
        linked = links.get(p.id, [])
        quantities = [r.consumable_quantity for r in linked if r.consumable_quantity is not None]
        used = sum(quantities, Decimal(0)) if quantities else None
        if not linked:
            status = "NOT_LINKED"
        elif used is not None and used > p.quantity:
            status = "OVER_USED"
        elif used is not None and used < p.quantity:
            status = "PARTLY_USED"
        else:
            status = "USED"
        rows.append(
            PurchaseRow(
                id=p.id,
                vehicle=p.vehicle.internal_code,
                vehicle_id=p.vehicle_id,
                day=to_local_date(p.occurred_at),
                item=p.fuel_type.name_ar,
                quantity=p.quantity,
                unit=p.unit.value,
                total_amount=p.total_amount,
                used=used,
                services=[r.id for r in linked],
                status=status,
                label=PURCHASE_STATUS[status],
            )
        )
    return rows


def _services(
    db: Session, date_from: date, date_to: date, vehicle_id: uuid.UUID | None
) -> list[MaintenanceRecord]:
    stmt = (
        select(MaintenanceRecord)
        .join(MaintenanceType, MaintenanceType.id == MaintenanceRecord.type_id)
        .where(
            MaintenanceType.consumable_type_id.is_not(None),
            MaintenanceRecord.status.in_(LIVE),
            MaintenanceRecord.performed_on >= date_from - timedelta(days=MATCH_DAYS),
            MaintenanceRecord.performed_on <= date_to + timedelta(days=MATCH_DAYS),
        )
        .order_by(MaintenanceRecord.performed_on)
    )
    if vehicle_id:
        stmt = stmt.where(MaintenanceRecord.vehicle_id == vehicle_id)
    return list(db.scalars(stmt).all())


def _service_row(r: MaintenanceRecord) -> ServiceRow:
    if r.consumable_quantity is None:
        status = "NO_QUANTITY"
    elif r.fuel_transaction_id is None and r.parts_cost == 0:
        status = "NO_PURCHASE"
    else:
        status = "OK"
    return ServiceRow(
        id=r.id,
        vehicle=r.vehicle.internal_code,
        vehicle_id=r.vehicle_id,
        day=r.performed_on,
        service=r.type.name_ar,
        quantity=r.consumable_quantity,
        spec=r.consumable_spec,
        purchase_id=r.fuel_transaction_id,
        parts_cost=r.parts_cost,
        next_due_km=r.next_due_km,
        next_due_on=r.next_due_on,
        status=status,
        label=SERVICE_STATUS[status],
    )


def _expense_rows(
    db: Session,
    start: object,
    end: object,
    vehicle_id: uuid.UUID | None,
    services: list[MaintenanceRecord],
) -> list[ExpenseRow]:
    stmt = (
        select(Expense)
        .join(ExpenseCategory, ExpenseCategory.id == Expense.category_id)
        .where(
            ExpenseCategory.code == OIL_CHANGE_EXPENSE,
            Expense.status.in_(LIVE),
            Expense.occurred_at >= start,
            Expense.occurred_at < end,
        )
        .order_by(Expense.occurred_at)
    )
    if vehicle_id:
        stmt = stmt.where(Expense.vehicle_id == vehicle_id)
    by_vehicle: dict[uuid.UUID, list[MaintenanceRecord]] = defaultdict(list)
    for s in services:
        by_vehicle[s.vehicle_id].append(s)
    rows = []
    for e in db.scalars(stmt).all():
        day = to_local_date(e.occurred_at)
        near = [
            s
            for s in by_vehicle.get(e.vehicle_id, [])
            if abs((s.performed_on - day).days) <= MATCH_DAYS
        ]
        match = min(near, key=lambda s: abs((s.performed_on - day).days)) if near else None
        status = "MATCHED" if match else "NO_SERVICE"
        rows.append(
            ExpenseRow(
                id=e.id,
                vehicle=e.vehicle.internal_code,
                vehicle_id=e.vehicle_id,
                day=day,
                amount=e.amount,
                service_id=match.id if match else None,
                status=status,
                label=EXPENSE_STATUS[status],
            )
        )
    return rows


def report(
    db: Session, date_from: date, date_to: date, vehicle_id: uuid.UUID | None = None
) -> Report:
    start, _ = local_day_bounds_utc(date_from)
    _, end = local_day_bounds_utc(date_to)
    services = _services(db, date_from, date_to, vehicle_id)
    out = Report(date_from=date_from, date_to=date_to)
    out.purchases = _purchase_rows(db, _purchases(db, start, end, vehicle_id))
    out.services = [_service_row(s) for s in services if date_from <= s.performed_on <= date_to]
    out.expenses = _expense_rows(db, start, end, vehicle_id, services)
    out.to_check = (
        sum(1 for p in out.purchases if p.status in ("NOT_LINKED", "OVER_USED"))
        + sum(1 for s in out.services if s.status != "OK")
        + sum(1 for e in out.expenses if e.status == "NO_SERVICE")
    )
    return out


__all__ = ["EXPENSE_STATUS", "PURCHASE_STATUS", "SERVICE_STATUS", "Report", "report"]
