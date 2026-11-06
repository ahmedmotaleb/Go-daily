"""Fleet use cases: vehicle types and vehicles."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.text import plate_key, to_latin_digits
from app.core.time import local_today
from app.models.assignment import DriverVehicleAssignment
from app.models.fleet import OwnershipStatus, Vehicle, VehicleType
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.fleet import (
    VehicleCreate,
    VehicleTypeCreate,
    VehicleTypeUpdate,
    VehicleUpdate,
)
from app.services import audit
from app.services.common import apply_changes, like_pattern, paginate
from app.services.expiry import warning_cutoff

VEHICLE_AUDITED = (
    "internal_code",
    "plate_number",
    "vehicle_type_id",
    "manufacturer",
    "model",
    "model_year",
    "color",
    "ownership_status",
    "is_active",
    "current_odometer_km",
    "license_expiry",
    "insurance_expiry",
    "notes",
)

ExpiryFilter = Literal["expired", "expiring", "attention"]
VehicleSort = Literal["code", "plate", "license_expiry", "insurance_expiry", "created"]


# ------------------------------------------------------------------ types


def list_vehicle_types(db: Session, *, include_inactive: bool = False) -> list[VehicleType]:
    stmt = select(VehicleType).order_by(VehicleType.sort_order, VehicleType.code)
    if not include_inactive:
        stmt = stmt.where(VehicleType.is_active.is_(True))
    return list(db.scalars(stmt).all())


def create_vehicle_type(db: Session, *, actor: User, data: VehicleTypeCreate) -> VehicleType:
    if db.scalar(select(VehicleType.id).where(VehicleType.code == data.code)):
        raise ConflictError("كود نوع المركبة مستخدم بالفعل", code="vehicle_type_code_taken")
    vt = VehicleType(**data.model_dump())
    db.add(vt)
    db.flush()
    audit.record(
        db,
        action="vehicle_type.created",
        actor=actor,
        entity_type="vehicle_type",
        entity_id=vt.id,
        changes=audit.diff({}, audit.snapshot(vt, ("code", "name_ar", "name_en", "sort_order"))),
    )
    db.commit()
    return vt


def update_vehicle_type(
    db: Session, *, actor: User, type_id: uuid.UUID, data: VehicleTypeUpdate
) -> VehicleType:
    vt = db.get(VehicleType, type_id)
    if vt is None:
        raise NotFoundError("نوع المركبة غير موجود")
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    changes = apply_changes(vt, fields, ("name_ar", "name_en", "is_active", "sort_order"))
    if changes:
        audit.record(
            db,
            action="vehicle_type.updated",
            actor=actor,
            entity_type="vehicle_type",
            entity_id=vt.id,
            changes=changes,
        )
        db.commit()
    return vt


# ------------------------------------------------------------------ vehicles


def get_vehicle(db: Session, vehicle_id: uuid.UUID, *, for_update: bool = False) -> Vehicle:
    stmt = select(Vehicle).where(Vehicle.id == vehicle_id)
    if for_update:
        stmt = stmt.with_for_update(of=Vehicle).execution_options(populate_existing=True)
    vehicle = db.scalar(stmt)
    if vehicle is None:
        raise NotFoundError("المركبة غير موجودة")
    return vehicle


def list_vehicles(
    db: Session,
    params: PageParams,
    *,
    q: str | None = None,
    vehicle_type_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    ownership_status: OwnershipStatus | None = None,
    expiry: ExpiryFilter | None = None,
    sort: VehicleSort = "code",
) -> tuple[list[Vehicle], int]:
    stmt = select(Vehicle)
    if q and q.strip():
        pattern = like_pattern(to_latin_digits(q))
        key = plate_key(q)
        conditions = [
            Vehicle.internal_code.ilike(pattern),
            Vehicle.plate_number.ilike(pattern),
            Vehicle.manufacturer.ilike(pattern),
            Vehicle.model.ilike(pattern),
        ]
        if key:
            conditions.append(Vehicle.plate_key.like(f"%{key}%"))
        stmt = stmt.where(or_(*conditions))
    if vehicle_type_id:
        stmt = stmt.where(Vehicle.vehicle_type_id == vehicle_type_id)
    if is_active is not None:
        stmt = stmt.where(Vehicle.is_active.is_(is_active))
    if ownership_status:
        stmt = stmt.where(Vehicle.ownership_status == ownership_status)
    if expiry:
        today = local_today()
        cutoff = warning_cutoff(today)
        if expiry == "expired":
            stmt = stmt.where(or_(Vehicle.license_expiry < today, Vehicle.insurance_expiry < today))
        elif expiry == "expiring":
            stmt = stmt.where(
                or_(
                    Vehicle.license_expiry.between(today, cutoff),
                    Vehicle.insurance_expiry.between(today, cutoff),
                )
            )
        else:  # attention: expired or expiring
            stmt = stmt.where(
                or_(Vehicle.license_expiry <= cutoff, Vehicle.insurance_expiry <= cutoff)
            )
    order = {
        "code": (Vehicle.internal_code,),
        "plate": (Vehicle.plate_key,),
        "license_expiry": (Vehicle.license_expiry.asc().nulls_last(), Vehicle.internal_code),
        "insurance_expiry": (Vehicle.insurance_expiry.asc().nulls_last(), Vehicle.internal_code),
        "created": (Vehicle.created_at.desc(),),
    }[sort]
    return paginate(db, stmt.order_by(*order, Vehicle.id), params)


def _ensure_type(db: Session, type_id: uuid.UUID) -> None:
    vt = db.get(VehicleType, type_id)
    if vt is None or not vt.is_active:
        raise ValidationFailed("نوع المركبة غير صحيح", code="invalid_vehicle_type")


def _ensure_unique(
    db: Session, *, code: str | None, pkey: str | None, exclude: uuid.UUID | None = None
) -> None:
    if code:
        stmt = select(Vehicle.id).where(func.upper(Vehicle.internal_code) == code.upper())
        if exclude:
            stmt = stmt.where(Vehicle.id != exclude)
        if db.scalar(stmt):
            raise ConflictError("الكود الداخلي مستخدم لمركبة أخرى", code="vehicle_code_taken")
    if pkey:
        stmt = select(Vehicle.id).where(Vehicle.plate_key == pkey)
        if exclude:
            stmt = stmt.where(Vehicle.id != exclude)
        if db.scalar(stmt):
            raise ConflictError("رقم اللوحة مسجل لمركبة أخرى", code="vehicle_plate_taken")


def create_vehicle(db: Session, *, actor: User, data: VehicleCreate) -> Vehicle:
    _ensure_type(db, data.vehicle_type_id)
    pkey = plate_key(data.plate_number)
    if not pkey:
        raise ValidationFailed("رقم اللوحة غير صحيح", code="invalid_plate")
    _ensure_unique(db, code=data.internal_code, pkey=pkey)
    vehicle = Vehicle(**data.model_dump(), plate_key=pkey)
    db.add(vehicle)
    db.flush()
    audit.record(
        db,
        action="vehicle.created",
        actor=actor,
        entity_type="vehicle",
        entity_id=vehicle.id,
        changes=audit.diff({}, audit.snapshot(vehicle, VEHICLE_AUDITED)),
    )
    db.commit()
    db.refresh(vehicle)
    return vehicle


def update_vehicle(
    db: Session, *, actor: User, vehicle_id: uuid.UUID, data: VehicleUpdate
) -> Vehicle:
    vehicle = get_vehicle(db, vehicle_id, for_update=True)
    fields: dict[str, Any] = data.model_dump(exclude_unset=True)
    reason = fields.pop("odometer_correction_reason", None)

    # Required columns cannot be cleared; optional ones may be set to null.
    for key in ("internal_code", "plate_number", "vehicle_type_id", "ownership_status"):
        if key in fields and fields[key] is None:
            fields.pop(key)

    if "vehicle_type_id" in fields and fields["vehicle_type_id"] != vehicle.vehicle_type_id:
        _ensure_type(db, fields["vehicle_type_id"])
    pkey = None
    if "plate_number" in fields:
        pkey = plate_key(fields["plate_number"])
        if not pkey:
            raise ValidationFailed("رقم اللوحة غير صحيح", code="invalid_plate")
        fields["plate_key"] = pkey
    _ensure_unique(db, code=fields.get("internal_code"), pkey=pkey, exclude=vehicle.id)

    old_odo = vehicle.current_odometer_km
    new_odo = fields.get("current_odometer_km", old_odo)
    lowering = (
        "current_odometer_km" in fields
        and old_odo is not None
        and (new_odo is None or new_odo < old_odo)
    )
    if lowering and not reason:
        raise ValidationFailed(
            "لا يمكن تقليل قراءة العداد بدون ذكر سبب التصحيح",
            code="odometer_decrease_requires_reason",
        )

    changes = apply_changes(vehicle, fields, VEHICLE_AUDITED)
    if changes:
        audit.record(
            db,
            action="vehicle.updated",
            actor=actor,
            entity_type="vehicle",
            entity_id=vehicle.id,
            changes=changes,
            reason=reason,
        )
        db.commit()
        db.refresh(vehicle)
    return vehicle


def set_vehicle_active(
    db: Session, *, actor: User, vehicle_id: uuid.UUID, active: bool, reason: str | None
) -> Vehicle:
    vehicle = get_vehicle(db, vehicle_id, for_update=True)
    if vehicle.is_active == active:
        return vehicle
    if not active:
        open_assignment = db.scalar(
            select(DriverVehicleAssignment.id).where(
                DriverVehicleAssignment.vehicle_id == vehicle.id,
                DriverVehicleAssignment.ends_at.is_(None),
            )
        )
        if open_assignment:
            raise ConflictError(
                "أنهِ تكليف السائق الحالي قبل إيقاف المركبة", code="vehicle_has_open_assignment"
            )
    vehicle.is_active = active
    audit.record(
        db,
        action="vehicle.activated" if active else "vehicle.deactivated",
        actor=actor,
        entity_type="vehicle",
        entity_id=vehicle.id,
        changes={"is_active": {"old": not active, "new": active}},
        reason=reason,
    )
    db.commit()
    return vehicle
