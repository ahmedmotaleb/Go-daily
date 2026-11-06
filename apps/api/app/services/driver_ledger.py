"""Driver account ledger: postings, voids, balances and statements.

Balance = what the company owes the driver (negative: the driver owes the
company, e.g. cash collected but not yet handed over). Entries are never
edited or deleted; a mistake is voided and re-entered.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.time import utcnow
from app.models.driver import Driver
from app.models.finance import (
    CREDIT_TYPES,
    DEBIT_TYPES,
    DriverLedgerEntry,
    LedgerEntryType,
    LedgerSource,
)
from app.models.user import User
from app.schemas.finance import LedgerEntryIn
from app.services import audit

ZERO = Decimal("0")


def signed_amount(
    entry_type: LedgerEntryType,
    amount: Decimal,
    direction: Literal["CREDIT", "DEBIT"] | None = None,
) -> Decimal:
    if amount <= 0:
        raise ValueError("ledger amounts are positive magnitudes")
    if entry_type in CREDIT_TYPES:
        return amount
    if entry_type in DEBIT_TYPES:
        return -amount
    return amount if direction == "CREDIT" else -amount


def post(
    db: Session,
    *,
    driver_id: uuid.UUID,
    entry_type: LedgerEntryType,
    amount: Decimal,
    occurred_on: date,
    description: str,
    actor: User | None,
    source_type: LedgerSource = LedgerSource.MANUAL,
    source_id: uuid.UUID | None = None,
    settlement_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    period: tuple[date, date] | None = None,
    reason: str | None = None,
    direction: Literal["CREDIT", "DEBIT"] | None = None,
) -> DriverLedgerEntry:
    """Add an entry (caller commits). `amount` is a positive magnitude."""
    entry = DriverLedgerEntry(
        driver_id=driver_id,
        entry_type=entry_type,
        amount=signed_amount(entry_type, amount, direction),
        occurred_on=occurred_on,
        description=description[:300],
        reason=reason,
        source_type=source_type,
        source_id=source_id,
        settlement_id=settlement_id,
        vehicle_id=vehicle_id,
        period_start=period[0] if period else None,
        period_end=period[1] if period else None,
        created_by_id=actor.id if actor else None,
    )
    db.add(entry)
    db.flush()
    audit.record(
        db,
        action="driver_ledger.posted",
        actor=actor,
        entity_type="driver",
        entity_id=driver_id,
        details={
            "entry_id": entry.id,
            "entry_type": entry_type.value,
            "amount": entry.amount,
            "source_type": source_type.value,
            "source_id": source_id,
        },
        reason=reason,
    )
    return entry


def _void(db: Session, entry: DriverLedgerEntry, actor: User | None, reason: str) -> None:
    entry.voided_at = utcnow()
    entry.voided_by_id = actor.id if actor else None
    entry.void_reason = reason
    audit.record(
        db,
        action="driver_ledger.voided",
        actor=actor,
        entity_type="driver",
        entity_id=entry.driver_id,
        details={
            "entry_id": entry.id,
            "entry_type": entry.entry_type.value,
            "amount": entry.amount,
        },
        reason=reason,
    )


def void_source(
    db: Session, source_type: LedgerSource, source_id: uuid.UUID, actor: User | None, reason: str
) -> None:
    """Void the live entry posted by a source record, if any (caller commits)."""
    entry = db.scalar(
        select(DriverLedgerEntry).where(
            DriverLedgerEntry.source_type == source_type,
            DriverLedgerEntry.source_id == source_id,
            DriverLedgerEntry.voided_at.is_(None),
        )
    )
    if entry is not None:
        _void(db, entry, actor, reason)


def create_manual(
    db: Session, *, actor: User, driver_id: uuid.UUID, data: LedgerEntryIn
) -> DriverLedgerEntry:
    if db.get(Driver, driver_id) is None:
        raise NotFoundError("السائق غير موجود")
    entry = post(
        db,
        driver_id=driver_id,
        entry_type=data.entry_type,
        amount=data.amount,
        occurred_on=data.occurred_on,
        description=data.description,
        actor=actor,
        vehicle_id=data.vehicle_id,
        reason=data.reason,
        direction=data.direction,
    )
    db.commit()
    return entry


def void_manual(db: Session, *, actor: User, entry_id: uuid.UUID, reason: str) -> DriverLedgerEntry:
    entry = db.get(DriverLedgerEntry, entry_id)
    if entry is None:
        raise NotFoundError("القيد غير موجود")
    if entry.voided_at is not None:
        raise ConflictError("القيد ملغي بالفعل", code="invalid_state")
    if entry.source_type is not LedgerSource.MANUAL:
        raise ConflictError(
            "هذا القيد ناتج عن سجل آخر؛ ألغِ السجل الأصلي أو التسوية", code="system_entry"
        )
    _void(db, entry, actor, reason)
    db.commit()
    return entry


def balance(db: Session, driver_id: uuid.UUID, *, before: date | None = None) -> Decimal:
    """Live balance, optionally of entries dated strictly before `before`."""
    stmt = select(func.coalesce(func.sum(DriverLedgerEntry.amount), 0)).where(
        DriverLedgerEntry.driver_id == driver_id, DriverLedgerEntry.voided_at.is_(None)
    )
    if before is not None:
        stmt = stmt.where(DriverLedgerEntry.occurred_on < before)
    return Decimal(db.scalar(stmt) or 0)


def entries(
    db: Session,
    driver_id: uuid.UUID,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    include_voided: bool = True,
) -> list[DriverLedgerEntry]:
    stmt = select(DriverLedgerEntry).where(DriverLedgerEntry.driver_id == driver_id)
    if date_from:
        stmt = stmt.where(DriverLedgerEntry.occurred_on >= date_from)
    if date_to:
        stmt = stmt.where(DriverLedgerEntry.occurred_on <= date_to)
    if not include_voided:
        stmt = stmt.where(DriverLedgerEntry.voided_at.is_(None))
    stmt = stmt.order_by(DriverLedgerEntry.occurred_on, DriverLedgerEntry.created_at)
    return list(db.scalars(stmt).all())


@dataclass
class StatementTotals:
    opening: Decimal
    by_type: dict[LedgerEntryType, Decimal]
    closing: Decimal
    entries: list[DriverLedgerEntry]


def statement(db: Session, driver_id: uuid.UUID, date_from: date, date_to: date) -> StatementTotals:
    opening = balance(db, driver_id, before=date_from)
    rows = entries(db, driver_id, date_from=date_from, date_to=date_to)
    by_type: dict[LedgerEntryType, Decimal] = defaultdict(lambda: ZERO)
    for e in rows:
        if e.voided_at is None:
            by_type[e.entry_type] += e.amount
    closing = opening + sum(by_type.values(), ZERO)
    return StatementTotals(opening=opening, by_type=dict(by_type), closing=closing, entries=rows)
