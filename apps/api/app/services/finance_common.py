"""Shared rules for financial records: review lifecycle and references.

Lifecycle: SUBMITTED -> APPROVED | REJECTED; REJECTED -> SUBMITTED (edited
and resubmitted); any non-voided record -> VOIDED with a reason. Approved
records are never edited: a correction voids them and creates a
replacement linked through `corrects_id`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, field_error
from app.core.time import utcnow
from app.models.driver import Driver
from app.models.finance import (
    Expense,
    FuelTransaction,
    RecordStatus,
    RevenueEntry,
    RideHailingStatement,
)
from app.models.fleet import Vehicle
from app.models.maintenance import MaintenanceRecord
from app.models.shift import OperationSession, Shift
from app.models.user import User

type Reviewable = (
    FuelTransaction | Expense | RevenueEntry | RideHailingStatement | MaintenanceRecord
)

CENT = Decimal("0.01")
CLOCK_SKEW = timedelta(minutes=5)
MAX_BACKFILL = timedelta(days=400)

REVIEW_FIELDS = ("status", "reviewed_by_id", "review_note", "voided_by_id", "void_reason")


def fetch[M](
    db: Session,
    model: type[M],
    record_id: uuid.UUID,
    missing: str,
    *,
    lock: bool = False,
    options: Sequence[Any] = (),
) -> M:
    """Load a record. With `lock`, its row stays locked until commit, so two
    reviewers acting on the same record run one after the other and the
    second sees the first one's result (e.g. "already approved")."""
    obj = db.get(
        model,
        record_id,
        options=list(options),
        with_for_update={"of": model} if lock else None,
        populate_existing=lock,
    )
    if obj is None:
        raise NotFoundError(missing)
    return obj


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def ensure_editable(record: Reviewable) -> None:
    if record.status not in (RecordStatus.SUBMITTED, RecordStatus.REJECTED):
        raise ConflictError("لا يمكن تعديل سجل معتمد أو ملغي؛ استخدم التصحيح", code="record_locked")


def resubmit_if_rejected(record: Reviewable) -> None:
    if record.status is RecordStatus.REJECTED:
        record.status = RecordStatus.SUBMITTED
        record.reviewed_by_id = None
        record.reviewed_at = None
        record.review_note = None


def approve(record: Reviewable, actor: User, note: str | None) -> None:
    if record.status is not RecordStatus.SUBMITTED:
        raise ConflictError("يمكن اعتماد السجلات المقدمة فقط", code="invalid_state")
    record.status = RecordStatus.APPROVED
    record.reviewed_by_id = actor.id
    record.reviewed_at = utcnow()
    record.review_note = note


def reject(record: Reviewable, actor: User, reason: str) -> None:
    if record.status is not RecordStatus.SUBMITTED:
        raise ConflictError("يمكن رفض السجلات المقدمة فقط", code="invalid_state")
    record.status = RecordStatus.REJECTED
    record.reviewed_by_id = actor.id
    record.reviewed_at = utcnow()
    record.review_note = reason


def void(record: Reviewable, actor: User, reason: str) -> RecordStatus:
    """Void the record; returns the status it had (side effects depend on it)."""
    if record.status is RecordStatus.VOIDED:
        raise ConflictError("السجل ملغي بالفعل", code="invalid_state")
    previous = record.status
    record.status = RecordStatus.VOIDED
    record.voided_by_id = actor.id
    record.voided_at = utcnow()
    record.void_reason = reason
    return previous


def ensure_correctable(record: Reviewable) -> None:
    if record.status is not RecordStatus.APPROVED:
        raise ConflictError(
            "التصحيح للسجلات المعتمدة فقط؛ عدّل السجل مباشرة إذا لم يُعتمد بعد",
            code="invalid_state",
        )


def check_time(value: datetime, field: str = "occurred_at") -> None:
    now = utcnow()
    if value > now + CLOCK_SKEW:
        raise field_error(field, "لا يمكن أن يكون التاريخ في المستقبل", code="time_in_future")
    if value < now - MAX_BACKFILL:
        raise field_error(field, "التاريخ أقدم من المسموح (سنة)", code="time_too_old")


def check_day(value: date, field: str) -> None:
    today = utcnow().date()
    if value > today + timedelta(days=1):
        raise field_error(field, "لا يمكن أن يكون التاريخ في المستقبل", code="time_in_future")
    if value < today - MAX_BACKFILL:
        raise field_error(field, "التاريخ أقدم من المسموح (سنة)", code="time_too_old")


def resolve_refs(
    db: Session,
    *,
    vehicle_id: uuid.UUID,
    driver_id: uuid.UUID | None = None,
    shift_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> tuple[Vehicle, Driver | None, Shift | None, OperationSession | None]:
    """Load and cross-check vehicle, driver, shift and session references."""
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise field_error("vehicle_id", "المركبة غير موجودة")
    session = db.get(OperationSession, session_id) if session_id else None
    if session_id and session is None:
        raise field_error("session_id", "التشغيل غير موجود")
    if session is not None:
        if shift_id and session.shift_id != shift_id:
            raise field_error("session_id", "التشغيل لا يتبع هذه الوردية")
        shift_id = session.shift_id
    shift = db.get(Shift, shift_id) if shift_id else None
    if shift_id and shift is None:
        raise field_error("shift_id", "الوردية غير موجودة")
    if shift is not None:
        if shift.vehicle_id != vehicle.id:
            raise field_error("shift_id", "الوردية على مركبة أخرى")
        if driver_id and shift.driver_id != driver_id:
            raise field_error("driver_id", "السائق لا يطابق سائق الوردية")
        driver_id = shift.driver_id
    driver = db.get(Driver, driver_id) if driver_id else None
    if driver_id and driver is None:
        raise field_error("driver_id", "السائق غير موجود")
    return vehicle, driver, shift, session


def corrected_by_map(
    db: Session, model: type[Reviewable], ids: list[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """Map original id -> id of the record that corrects it."""
    if not ids:
        return {}
    rows = db.execute(select(model.corrects_id, model.id).where(model.corrects_id.in_(ids))).all()
    return {orig: new for orig, new in rows if orig is not None}


def period_share(item_start: date, item_end: date, range_start: date, range_end: date) -> Decimal:
    """Fraction (by days) of [item_start, item_end] that falls inside the range."""
    start = max(item_start, range_start)
    end = min(item_end, range_end)
    if end < start:
        return Decimal("0")
    total = (item_end - item_start).days + 1
    return Decimal((end - start).days + 1) / Decimal(total)
