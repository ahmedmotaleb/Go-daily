"""Maintenance types, schedules, service records and due list (Task 21)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, require_permissions
from app.api.finance_presenters import maintenance_outs
from app.core.permissions import Permission, has_permission
from app.models.finance import RecordStatus
from app.models.maintenance import MaintenanceType
from app.models.user import User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.finance import Ref, RejectAction, ReviewAction, VoidAction
from app.schemas.maintenance import (
    DueItem,
    MaintenanceTypeCreate,
    MaintenanceTypeOut,
    MaintenanceTypeUpdate,
    RecordCorrection,
    RecordCreate,
    RecordFields,
    RecordOut,
    ScheduleIn,
)
from app.services import maintenance as maintenance_service

router = APIRouter(prefix="/maintenance", tags=["maintenance"])

Reader = Annotated[User, Depends(require_permissions(Permission.MAINTENANCE_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.MAINTENANCE_WRITE))]
# Service records are costs: approving them is a finance permission.
Approver = Annotated[
    User, Depends(require_permissions(Permission.MAINTENANCE_READ, Permission.EXPENSES_APPROVE))
]
SettingsAdmin = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]


@router.get("/types", response_model=list[MaintenanceTypeOut])
def list_types(_: Reader, db: DbSession, include_inactive: bool = False) -> list[MaintenanceType]:
    return maintenance_service.list_types(db, include_inactive=include_inactive)


@router.post("/types", response_model=MaintenanceTypeOut, status_code=status.HTTP_201_CREATED)
def create_type(
    body: MaintenanceTypeCreate, actor: SettingsAdmin, db: DbSession
) -> MaintenanceType:
    return maintenance_service.create_type(db, actor=actor, data=body)


@router.patch("/types/{type_id}", response_model=MaintenanceTypeOut)
def update_type(
    type_id: uuid.UUID, body: MaintenanceTypeUpdate, actor: SettingsAdmin, db: DbSession
) -> MaintenanceType:
    return maintenance_service.update_type(db, actor=actor, type_id=type_id, data=body)


def _due_items(rows: list[maintenance_service.DueRow]) -> list[DueItem]:
    return [
        DueItem(
            schedule_id=r.schedule.id,
            vehicle=Ref(id=r.schedule.vehicle.id, name=r.schedule.vehicle.internal_code),
            type=MaintenanceTypeOut.model_validate(r.schedule.type),
            interval_km=r.interval_km,
            interval_days=r.interval_days,
            last_performed_on=r.last.performed_on if r.last else None,
            last_odometer_km=r.last.odometer_km if r.last else None,
            current_odometer_km=r.schedule.vehicle.current_odometer_km,
            next_due_km=r.next_due_km,
            next_due_date=r.next_due_date,
            km_left=r.km_left,
            days_left=r.days_left,
            state=r.state,
            is_active=r.schedule.is_active,
        )
        for r in rows
    ]


@router.get("/due", response_model=list[DueItem])
def due(
    _: Reader, db: DbSession, vehicle_id: uuid.UUID | None = None, include_inactive: bool = False
) -> list[DueItem]:
    return _due_items(
        maintenance_service.due_status(db, vehicle_id=vehicle_id, include_inactive=include_inactive)
    )


@router.put("/vehicles/{vehicle_id}/schedules", response_model=list[DueItem])
def save_schedule(
    vehicle_id: uuid.UUID, body: ScheduleIn, actor: Writer, db: DbSession
) -> list[DueItem]:
    maintenance_service.upsert_schedule(db, actor=actor, vehicle_id=vehicle_id, data=body)
    return _due_items(
        maintenance_service.due_status(db, vehicle_id=vehicle_id, include_inactive=True)
    )


@router.get("/records", response_model=Page[RecordOut])
def list_records(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    vehicle_id: uuid.UUID | None = None,
    type_id: uuid.UUID | None = None,
    status: RecordStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page[RecordOut]:
    rows, total = maintenance_service.list_records(
        db,
        params,
        maintenance_service.RecordFilters(
            vehicle_id=vehicle_id,
            type_id=type_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
        ),
    )
    return Page(
        items=maintenance_outs(db, rows), total=total, page=params.page, page_size=params.page_size
    )


@router.post("/records", response_model=RecordOut, status_code=status.HTTP_201_CREATED)
def create_record(body: RecordCreate, actor: Writer, db: DbSession) -> RecordOut:
    record = maintenance_service.create(
        db,
        actor=actor,
        data=body,
        can_approve=has_permission(actor.role, Permission.EXPENSES_APPROVE),
    )
    return maintenance_outs(db, [record])[0]


@router.get("/records/{record_id}", response_model=RecordOut)
def get_record(record_id: uuid.UUID, _: Reader, db: DbSession) -> RecordOut:
    return maintenance_outs(db, [maintenance_service.get(db, record_id)])[0]


@router.put("/records/{record_id}", response_model=RecordOut)
def update_record(
    record_id: uuid.UUID, body: RecordFields, actor: Writer, db: DbSession
) -> RecordOut:
    record = maintenance_service.update(db, actor=actor, record_id=record_id, data=body)
    return maintenance_outs(db, [record])[0]


@router.post("/records/{record_id}/approve", response_model=RecordOut)
def approve_record(
    record_id: uuid.UUID, body: ReviewAction, actor: Approver, db: DbSession
) -> RecordOut:
    record = maintenance_service.approve(db, actor=actor, record_id=record_id, note=body.note)
    return maintenance_outs(db, [record])[0]


@router.post("/records/{record_id}/reject", response_model=RecordOut)
def reject_record(
    record_id: uuid.UUID, body: RejectAction, actor: Approver, db: DbSession
) -> RecordOut:
    record = maintenance_service.reject(db, actor=actor, record_id=record_id, reason=body.reason)
    return maintenance_outs(db, [record])[0]


@router.post("/records/{record_id}/void", response_model=RecordOut)
def void_record(
    record_id: uuid.UUID, body: VoidAction, actor: Approver, db: DbSession
) -> RecordOut:
    record = maintenance_service.void(db, actor=actor, record_id=record_id, reason=body.reason)
    return maintenance_outs(db, [record])[0]


@router.post(
    "/records/{record_id}/correct", response_model=RecordOut, status_code=status.HTTP_201_CREATED
)
def correct_record(
    record_id: uuid.UUID, body: RecordCorrection, actor: Approver, db: DbSession
) -> RecordOut:
    record = maintenance_service.correct(
        db, actor=actor, record_id=record_id, data=body, can_approve=True
    )
    return maintenance_outs(db, [record])[0]
