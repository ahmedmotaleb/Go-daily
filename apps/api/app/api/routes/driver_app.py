"""Endpoints used by the Android driver app.

Every endpoint is scoped to the logged-in driver: a driver can only see
and change their own shifts, on vehicles they are assigned to. Writes
accept an `Idempotency-Key` header so network retries are safe.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request, UploadFile, status
from sqlalchemy import or_, select

from app.api.deps import CurrentDriver, CurrentDriverUser, DbSession
from app.api.presenters import session_out, shift_out
from app.api.routes.attachments import read_limited
from app.core.errors import NotFoundError, PermissionDenied
from app.core.time import local_today, utcnow
from app.models.assignment import DriverVehicleAssignment
from app.models.attachment import AttachmentOwner
from app.models.driver import Driver
from app.models.finance import FuelTransaction
from app.models.shift import OperationSession, Shift, ShiftSource, ShiftStatus
from app.schemas.attachment import AttachmentOut, DuplicateRef, UploadResult
from app.schemas.common import PageParams
from app.schemas.driver_app import (
    DriverCatalogOut,
    DriverFuelOut,
    DriverFuelTypeOut,
    DriverMeOut,
    DriverRouteOut,
    DriverSessionStart,
    DriverShiftEnd,
    DriverShiftStart,
    DriverVehicleOut,
)
from app.schemas.finance import DriverFuelCreate
from app.schemas.operations import OperationTypeOut
from app.schemas.shift import (
    SessionEnd,
    SessionOut,
    SessionStart,
    ShiftCreate,
    ShiftEnd,
    ShiftOut,
    ShiftStart,
)
from app.services import attachments as attachments_service
from app.services import fuel as fuel_service
from app.services import idempotency
from app.services import operations as ops_service
from app.services import shifts as shifts_service
from app.services.expiry import expiry_status

router = APIRouter(prefix="/driver", tags=["driver-app"])

IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


def _vehicles(db: DbSession, driver: Driver) -> list[DriverVehicleOut]:
    now = utcnow()
    rows = db.scalars(
        select(DriverVehicleAssignment)
        .where(
            DriverVehicleAssignment.driver_id == driver.id,
            DriverVehicleAssignment.starts_at <= now,
            or_(DriverVehicleAssignment.ends_at.is_(None), DriverVehicleAssignment.ends_at > now),
        )
        .order_by(DriverVehicleAssignment.role)
    ).all()
    return [
        DriverVehicleOut(
            id=a.vehicle.id,
            internal_code=a.vehicle.internal_code,
            plate_number=a.vehicle.plate_number,
            vehicle_type=a.vehicle.vehicle_type.name_ar,
            assignment_role=a.role.value,
            last_odometer_km=a.vehicle.current_odometer_km,
        )
        for a in rows
        if a.vehicle.is_active
    ]


def _own_shift(db: DbSession, driver: Driver, shift_id: uuid.UUID) -> Shift:
    shift = shifts_service.get_shift(db, shift_id)
    if shift.driver_id != driver.id:
        # Do not reveal whether another driver's shift exists.
        raise NotFoundError("الوردية غير موجودة")
    return shift


@router.get("/me", response_model=DriverMeOut)
def me(driver: CurrentDriver, db: DbSession) -> DriverMeOut:
    active = shifts_service.active_shift_for_driver(db, driver.id)
    return DriverMeOut(
        driver_id=driver.id,
        full_name=driver.full_name,
        phone=driver.phone,
        license_expiry=driver.license_expiry,
        license_status=expiry_status(driver.license_expiry),
        vehicles=_vehicles(db, driver),
        active_shift=shift_out(active) if active else None,
    )


@router.get("/catalog", response_model=DriverCatalogOut)
def catalog(_: CurrentDriver, db: DbSession) -> DriverCatalogOut:
    types = ops_service.list_operation_types(db)
    routes, _total = ops_service.list_routes(db, PageParams(page=1, page_size=500), is_active=True)
    return DriverCatalogOut(
        operation_types=[OperationTypeOut.model_validate(t) for t in types],
        routes=[
            DriverRouteOut(id=r.id, name=r.name, operation_type_id=r.operation_type_id)
            for r in routes
        ],
        fuel_types=[
            DriverFuelTypeOut(
                id=t.id, code=t.code, name_ar=t.name_ar, default_unit=t.default_unit.value
            )
            for t in fuel_service.list_types(db)
        ],
    )


@router.get("/shifts/today", response_model=list[ShiftOut])
def today_shifts(driver: CurrentDriver, db: DbSession) -> list[ShiftOut]:
    rows, _ = shifts_service.list_shifts(
        db, PageParams(page=1, page_size=50), driver_id=driver.id, day=local_today()
    )
    return [shift_out(s) for s in rows if s.status is not ShiftStatus.CANCELLED]


@router.get("/shifts/active", response_model=ShiftOut | None)
def active_shift(driver: CurrentDriver, db: DbSession) -> ShiftOut | None:
    s = shifts_service.active_shift_for_driver(db, driver.id)
    return shift_out(s) if s else None


@router.post("/shifts/start", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
def start_shift(
    body: DriverShiftStart,
    request: Request,
    driver: CurrentDriver,
    user: CurrentDriverUser,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> Any:
    def action() -> ShiftOut:
        if body.planned_shift_id is not None:
            planned = _own_shift(db, driver, body.planned_shift_id)
            if planned.vehicle_id != body.vehicle_id:
                raise PermissionDenied("الوردية المخططة على مركبة أخرى", code="vehicle_mismatch")
            shift = shifts_service.start_shift(
                db,
                actor=user,
                shift_id=planned.id,
                data=ShiftStart(
                    start_odometer_km=body.start_odometer_km,
                    operation_type_id=body.operation_type_id,
                    route_id=body.route_id,
                ),
                source=ShiftSource.DRIVER_APP,
            )
        else:
            shift = shifts_service.create_shift(
                db,
                actor=user,
                data=ShiftCreate(
                    driver_id=driver.id,
                    vehicle_id=body.vehicle_id,
                    start_now=True,
                    start_odometer_km=body.start_odometer_km,
                    planned_operation_type_id=body.operation_type_id,
                    planned_route_id=body.route_id,
                ),
                source=ShiftSource.DRIVER_APP,
            )
        return shift_out(shift)

    result, _ = idempotency.run_idempotent(
        db,
        user=user,
        key=idempotency_key,
        method="POST",
        path=request.url.path,
        body=body.model_dump(),
        status_code=201,
        action=action,
    )
    return result


@router.post("/shifts/{shift_id}/end", response_model=ShiftOut)
def end_shift(
    shift_id: uuid.UUID,
    body: DriverShiftEnd,
    request: Request,
    driver: CurrentDriver,
    user: CurrentDriverUser,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> Any:
    def action() -> ShiftOut:
        _own_shift(db, driver, shift_id)
        shift = shifts_service.end_shift(
            db,
            actor=user,
            shift_id=shift_id,
            data=ShiftEnd(end_odometer_km=body.end_odometer_km, notes=body.notes),
            source=ShiftSource.DRIVER_APP,
        )
        return shift_out(shift)

    result, _ = idempotency.run_idempotent(
        db,
        user=user,
        key=idempotency_key,
        method="POST",
        path=request.url.path,
        body=body.model_dump(),
        status_code=200,
        action=action,
    )
    return result


@router.post(
    "/shifts/{shift_id}/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED
)
def start_session(
    shift_id: uuid.UUID,
    body: DriverSessionStart,
    request: Request,
    driver: CurrentDriver,
    user: CurrentDriverUser,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> Any:
    def action() -> SessionOut:
        _own_shift(db, driver, shift_id)
        session = shifts_service.start_session(
            db,
            actor=user,
            shift_id=shift_id,
            data=SessionStart(operation_type_id=body.operation_type_id, route_id=body.route_id),
            source=ShiftSource.DRIVER_APP,
        )
        return session_out(session)

    result, _ = idempotency.run_idempotent(
        db,
        user=user,
        key=idempotency_key,
        method="POST",
        path=request.url.path,
        body=body.model_dump(),
        status_code=201,
        action=action,
    )
    return result


@router.post("/sessions/{session_id}/end", response_model=SessionOut)
def end_session(
    session_id: uuid.UUID,
    driver: CurrentDriver,
    user: CurrentDriverUser,
    db: DbSession,
) -> SessionOut:
    session = db.get(OperationSession, session_id)
    if session is None or session.shift.driver_id != driver.id:
        raise NotFoundError("التشغيل غير موجود")
    return session_out(
        shifts_service.end_session(
            db, actor=user, session_id=session_id, data=SessionEnd(), source=ShiftSource.DRIVER_APP
        )
    )


def _fuel_out(tx: FuelTransaction) -> DriverFuelOut:
    return DriverFuelOut(
        id=tx.id,
        fuel_type=tx.fuel_type.name_ar,
        quantity=tx.quantity,
        unit=tx.unit.value,
        total_amount=tx.total_amount,
        occurred_at=tx.occurred_at,
        status=tx.status.value,
        paid_by=tx.paid_by.value,
    )


@router.post("/fuel", response_model=DriverFuelOut, status_code=status.HTTP_201_CREATED)
def record_fuel(
    body: DriverFuelCreate,
    request: Request,
    driver: CurrentDriver,
    user: CurrentDriverUser,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> Any:
    """Fuel/oil entry during the active shift; reviewed by the office before it counts."""

    def action() -> DriverFuelOut:
        tx = fuel_service.create_from_driver(db, actor=user, driver=driver, data=body)
        return _fuel_out(tx)

    result, _ = idempotency.run_idempotent(
        db,
        user=user,
        key=idempotency_key,
        method="POST",
        path=request.url.path,
        body=body.model_dump(mode="json"),
        status_code=201,
        action=action,
    )
    return result


@router.get("/fuel", response_model=list[DriverFuelOut])
def my_fuel(driver: CurrentDriver, db: DbSession) -> list[DriverFuelOut]:
    rows = db.scalars(
        select(FuelTransaction)
        .where(FuelTransaction.driver_id == driver.id)
        .order_by(FuelTransaction.occurred_at.desc())
        .limit(20)
    ).all()
    return [_fuel_out(tx) for tx in rows]


@router.post(
    "/fuel/{tx_id}/receipt", response_model=UploadResult, status_code=status.HTTP_201_CREATED
)
async def upload_fuel_receipt(
    tx_id: uuid.UUID,
    file: UploadFile,
    driver: CurrentDriver,
    user: CurrentDriverUser,
    db: DbSession,
) -> UploadResult:
    """Photo of the receipt for the driver's own entry, before office review."""
    tx = db.get(FuelTransaction, tx_id)
    if tx is None or tx.driver_id != driver.id:
        raise NotFoundError("سجل الوقود غير موجود")
    data = await read_limited(file)
    attachment, duplicates = attachments_service.upload(
        db,
        actor=user,
        owner_type=AttachmentOwner.FUEL_TRANSACTION,
        owner_id=tx.id,
        data=data,
        filename=file.filename,
    )
    return UploadResult(
        attachment=AttachmentOut(
            id=attachment.id,
            owner_type=attachment.owner_type,
            owner_id=attachment.owner_id,
            kind=attachment.kind,
            original_filename=attachment.original_filename,
            content_type=attachment.content_type,
            size_bytes=attachment.size_bytes,
            sha256=attachment.sha256,
            uploaded_by=None,
            created_at=attachment.created_at,
            deleted_at=None,
            delete_reason=None,
        ),
        duplicates=[
            DuplicateRef(attachment_id=d.id, owner_type=d.owner_type, owner_id=d.owner_id)
            for d in duplicates
        ],
    )
