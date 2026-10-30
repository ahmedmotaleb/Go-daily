"""Maintenance types, schedules, service records and due status (Task 21)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, field_error
from app.core.time import local_today
from app.models.finance import FuelCategory, FuelTransaction, RecordStatus
from app.models.fleet import Vehicle
from app.models.maintenance import MaintenanceRecord, MaintenanceSchedule, MaintenanceType
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.maintenance import (
    DueState,
    MaintenanceTypeCreate,
    MaintenanceTypeUpdate,
    RecordCorrection,
    RecordCreate,
    RecordFields,
    ScheduleIn,
)
from app.services import audit
from app.services import finance_common as fc
from app.services.common import apply_changes, paginate

ENTITY = "maintenance_record"
AUDITED = (
    "vehicle_id",
    "type_id",
    "performed_on",
    "odometer_km",
    "vendor",
    "parts_cost",
    "labor_cost",
    "other_cost",
    "description",
    "downtime_start",
    "downtime_end",
    "fuel_transaction_id",
    "notes",
)
DUE_SOON_DAYS = 14
DUE_SOON_KM_MIN = 500


# --- Types ---------------------------------------------------------------------------


def list_types(db: Session, *, include_inactive: bool = False) -> list[MaintenanceType]:
    stmt = select(MaintenanceType).order_by(MaintenanceType.sort_order, MaintenanceType.code)
    if not include_inactive:
        stmt = stmt.where(MaintenanceType.is_active.is_(True))
    return list(db.scalars(stmt).all())


def create_type(db: Session, *, actor: User, data: MaintenanceTypeCreate) -> MaintenanceType:
    if db.scalar(select(MaintenanceType.id).where(MaintenanceType.code == data.code)):
        raise field_error("code", "الرمز مستخدم بالفعل", code="duplicate_code")
    mtype = MaintenanceType(**data.model_dump())
    db.add(mtype)
    db.flush()
    audit.record(
        db,
        action="maintenance_type.created",
        actor=actor,
        entity_type="maintenance_type",
        entity_id=mtype.id,
        details=data.model_dump(mode="json"),
    )
    db.commit()
    return mtype


def update_type(
    db: Session, *, actor: User, type_id: uuid.UUID, data: MaintenanceTypeUpdate
) -> MaintenanceType:
    mtype = db.get(MaintenanceType, type_id)
    if mtype is None:
        raise NotFoundError("نوع الصيانة غير موجود")
    changes = apply_changes(
        mtype,
        data.model_dump(exclude_unset=True),
        ("name_ar", "interval_km", "interval_days", "is_active", "sort_order"),
    )
    if changes:
        audit.record(
            db,
            action="maintenance_type.updated",
            actor=actor,
            entity_type="maintenance_type",
            entity_id=mtype.id,
            changes=changes,
        )
    db.commit()
    return mtype


# --- Schedules -----------------------------------------------------------------------


def upsert_schedule(
    db: Session, *, actor: User, vehicle_id: uuid.UUID, data: ScheduleIn
) -> MaintenanceSchedule:
    if db.get(Vehicle, vehicle_id) is None:
        raise NotFoundError("المركبة غير موجودة")
    mtype = db.get(MaintenanceType, data.type_id)
    if mtype is None:
        raise field_error("type_id", "نوع الصيانة غير موجود")
    if not (data.interval_km or mtype.interval_km or data.interval_days or mtype.interval_days):
        raise field_error("interval_km", "حدد فترة بالكيلومتر أو بالأيام لهذا النوع")
    schedule = db.scalar(
        select(MaintenanceSchedule).where(
            MaintenanceSchedule.vehicle_id == vehicle_id,
            MaintenanceSchedule.type_id == data.type_id,
        )
    )
    fields = data.model_dump(exclude={"type_id"})
    if schedule is None:
        schedule = MaintenanceSchedule(vehicle_id=vehicle_id, type_id=data.type_id, **fields)
        db.add(schedule)
        db.flush()
        changes = audit.diff({}, fields)
    else:
        changes = apply_changes(schedule, fields, tuple(fields))
    audit.record(
        db,
        action="maintenance_schedule.saved",
        actor=actor,
        entity_type="vehicle",
        entity_id=vehicle_id,
        changes=changes,
        details={"type": mtype.code},
    )
    db.commit()
    return schedule


@dataclass
class DueRow:
    schedule: MaintenanceSchedule
    interval_km: int | None
    interval_days: int | None
    last: MaintenanceRecord | None
    next_due_km: int | None
    next_due_date: date | None
    km_left: int | None
    days_left: int | None
    state: DueState


def _state(km_left: int | None, days_left: int | None, interval_km: int | None) -> DueState:
    if km_left is None and days_left is None:
        return "UNKNOWN"
    if (km_left is not None and km_left < 0) or (days_left is not None and days_left < 0):
        return "OVERDUE"
    soon_km = max(DUE_SOON_KM_MIN, (interval_km or 0) // 10)
    if (km_left is not None and km_left <= soon_km) or (
        days_left is not None and days_left <= DUE_SOON_DAYS
    ):
        return "DUE_SOON"
    return "OK"


def due_status(
    db: Session, *, vehicle_id: uuid.UUID | None = None, include_inactive: bool = False
) -> list[DueRow]:
    stmt = select(MaintenanceSchedule).join(Vehicle, Vehicle.id == MaintenanceSchedule.vehicle_id)
    if vehicle_id:
        stmt = stmt.where(MaintenanceSchedule.vehicle_id == vehicle_id)
    if not include_inactive:
        stmt = stmt.where(MaintenanceSchedule.is_active.is_(True), Vehicle.is_active.is_(True))
    schedules = list(db.scalars(stmt).all())
    if not schedules:
        return []
    records = db.scalars(
        select(MaintenanceRecord)
        .where(
            MaintenanceRecord.status == RecordStatus.APPROVED,
            MaintenanceRecord.vehicle_id.in_({s.vehicle_id for s in schedules}),
        )
        .order_by(MaintenanceRecord.performed_on.desc(), MaintenanceRecord.created_at.desc())
    ).all()
    latest: dict[tuple[uuid.UUID, uuid.UUID], MaintenanceRecord] = {}
    for r in records:
        latest.setdefault((r.vehicle_id, r.type_id), r)
    today = local_today()
    rows = []
    for s in schedules:
        interval_km = s.interval_km or s.type.interval_km
        interval_days = s.interval_days or s.type.interval_days
        last = latest.get((s.vehicle_id, s.type_id))
        base_km = last.odometer_km if last and last.odometer_km is not None else s.baseline_km
        base_date = last.performed_on if last else s.baseline_date
        next_km = base_km + interval_km if base_km is not None and interval_km else None
        next_date = (
            base_date + timedelta(days=interval_days) if base_date and interval_days else None
        )
        current = s.vehicle.current_odometer_km
        km_left = next_km - current if next_km is not None and current is not None else None
        days_left = (next_date - today).days if next_date else None
        rows.append(
            DueRow(
                schedule=s,
                interval_km=interval_km,
                interval_days=interval_days,
                last=last,
                next_due_km=next_km,
                next_due_date=next_date,
                km_left=km_left,
                days_left=days_left,
                state=_state(km_left, days_left, interval_km),
            )
        )
    order = {"OVERDUE": 0, "DUE_SOON": 1, "UNKNOWN": 2, "OK": 3}
    rows.sort(key=lambda r: (order[r.state], r.days_left if r.days_left is not None else 99999))
    return rows


# --- Records -------------------------------------------------------------------------


def get(db: Session, record_id: uuid.UUID, *, lock: bool = False) -> MaintenanceRecord:
    return fc.fetch(db, MaintenanceRecord, record_id, "سجل الصيانة غير موجود", lock=lock)


def _validate(db: Session, r: MaintenanceRecord) -> None:
    fc.check_day(r.performed_on, "performed_on")
    if r.fuel_transaction_id is not None:
        tx = db.get(FuelTransaction, r.fuel_transaction_id)
        if tx is None or tx.vehicle_id != r.vehicle_id:
            raise field_error("fuel_transaction_id", "سجل الشراء غير موجود أو لمركبة أخرى")
        if tx.fuel_type.category is not FuelCategory.CONSUMABLE:
            raise field_error(
                "fuel_transaction_id", "يمكن ربط مشتريات الزيوت والمستهلكات فقط، وليس الوقود"
            )


def _new(
    db: Session, *, actor: User, data: RecordFields, corrects: MaintenanceRecord | None = None
) -> MaintenanceRecord:
    vehicle = db.get(Vehicle, data.vehicle_id)
    if vehicle is None:
        raise field_error("vehicle_id", "المركبة غير موجودة")
    mtype = db.get(MaintenanceType, data.type_id)
    if mtype is None or not mtype.is_active:
        raise field_error("type_id", "نوع الصيانة غير موجود أو غير مفعل")
    record = MaintenanceRecord(
        **data.model_dump(include=set(AUDITED)),
        status=RecordStatus.SUBMITTED,
        created_by_id=actor.id,
        corrects_id=corrects.id if corrects else None,
    )
    record.vehicle = vehicle
    record.type = mtype
    _validate(db, record)
    db.add(record)
    db.flush()
    return record


def _approve(db: Session, record: MaintenanceRecord, actor: User, note: str | None) -> None:
    fc.approve(record, actor, note)
    audit.record(
        db,
        action=f"{ENTITY}.approved",
        actor=actor,
        entity_type=ENTITY,
        entity_id=record.id,
        details={"note": note} if note else None,
    )


def create(
    db: Session, *, actor: User, data: RecordCreate, can_approve: bool = False
) -> MaintenanceRecord:
    record = _new(db, actor=actor, data=data)
    audit.record(
        db,
        action=f"{ENTITY}.created",
        actor=actor,
        entity_type=ENTITY,
        entity_id=record.id,
        changes=audit.diff({}, audit.snapshot(record, AUDITED)),
    )
    if data.approve_now and can_approve:
        _approve(db, record, actor, note="اعتماد عند الإدخال")
    db.commit()
    return record


def update(
    db: Session, *, actor: User, record_id: uuid.UUID, data: RecordFields
) -> MaintenanceRecord:
    record = get(db, record_id, lock=True)
    fc.ensure_editable(record)
    if data.vehicle_id != record.vehicle_id:
        raise field_error("vehicle_id", "لا يمكن تغيير المركبة؛ أنشئ سجلًا جديدًا")
    if data.type_id != record.type_id:
        mtype = db.get(MaintenanceType, data.type_id)
        if mtype is None:
            raise field_error("type_id", "نوع الصيانة غير موجود")
        record.type = mtype
    changes = apply_changes(record, data.model_dump(include=set(AUDITED)), AUDITED)
    _validate(db, record)
    fc.resubmit_if_rejected(record)
    if changes:
        audit.record(
            db,
            action=f"{ENTITY}.updated",
            actor=actor,
            entity_type=ENTITY,
            entity_id=record.id,
            changes=changes,
        )
    db.commit()
    return record


def approve(
    db: Session, *, actor: User, record_id: uuid.UUID, note: str | None
) -> MaintenanceRecord:
    record = get(db, record_id, lock=True)
    _approve(db, record, actor, note)
    db.commit()
    return record


def reject(db: Session, *, actor: User, record_id: uuid.UUID, reason: str) -> MaintenanceRecord:
    record = get(db, record_id, lock=True)
    fc.reject(record, actor, reason)
    audit.record(
        db,
        action=f"{ENTITY}.rejected",
        actor=actor,
        entity_type=ENTITY,
        entity_id=record.id,
        reason=reason,
    )
    db.commit()
    return record


def _void(db: Session, record: MaintenanceRecord, actor: User, reason: str) -> None:
    fc.void(record, actor, reason)
    audit.record(
        db,
        action=f"{ENTITY}.voided",
        actor=actor,
        entity_type=ENTITY,
        entity_id=record.id,
        reason=reason,
    )


def void(db: Session, *, actor: User, record_id: uuid.UUID, reason: str) -> MaintenanceRecord:
    record = get(db, record_id, lock=True)
    _void(db, record, actor, reason)
    db.commit()
    return record


def correct(
    db: Session, *, actor: User, record_id: uuid.UUID, data: RecordCorrection, can_approve: bool
) -> MaintenanceRecord:
    original = get(db, record_id, lock=True)
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
class RecordFilters:
    vehicle_id: uuid.UUID | None = None
    type_id: uuid.UUID | None = None
    status: RecordStatus | None = None
    date_from: date | None = None
    date_to: date | None = None


def _filtered(f: RecordFilters) -> Select[MaintenanceRecord]:
    stmt = select(MaintenanceRecord)
    if f.vehicle_id:
        stmt = stmt.where(MaintenanceRecord.vehicle_id == f.vehicle_id)
    if f.type_id:
        stmt = stmt.where(MaintenanceRecord.type_id == f.type_id)
    if f.status:
        stmt = stmt.where(MaintenanceRecord.status == f.status)
    if f.date_from:
        stmt = stmt.where(MaintenanceRecord.performed_on >= f.date_from)
    if f.date_to:
        stmt = stmt.where(MaintenanceRecord.performed_on <= f.date_to)
    return stmt


def list_records(
    db: Session, params: PageParams, filters: RecordFilters
) -> tuple[list[MaintenanceRecord], int]:
    stmt = _filtered(filters).order_by(
        MaintenanceRecord.performed_on.desc(), MaintenanceRecord.created_at.desc()
    )
    return paginate(db, stmt, params)
