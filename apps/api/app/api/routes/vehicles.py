"""Fleet endpoints: vehicle types and vehicles."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from app.api.deps import DbSession, require_permissions
from app.api.presenters import assignment_out, vehicle_out
from app.core.permissions import Permission, has_permission
from app.core.time import local_today
from app.models.fleet import OwnershipStatus, VehicleType
from app.models.user import User
from app.schemas.assignment import AssignmentOut
from app.schemas.common import Page, PageParams, page_params
from app.schemas.fleet import (
    StatusChange,
    VehicleCreate,
    VehicleOut,
    VehicleTypeCreate,
    VehicleTypeOut,
    VehicleTypeUpdate,
    VehicleUpdate,
)
from app.services import assignments as assignments_service
from app.services import vehicle_timeline
from app.services import vehicles as vehicles_service

router = APIRouter(tags=["fleet"])

Reader = Annotated[User, Depends(require_permissions(Permission.VEHICLES_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.VEHICLES_WRITE))]
SettingsAdmin = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]


@router.get("/vehicle-types", response_model=list[VehicleTypeOut])
def list_vehicle_types(
    _: Reader, db: DbSession, include_inactive: bool = False
) -> list[VehicleType]:
    return vehicles_service.list_vehicle_types(db, include_inactive=include_inactive)


@router.post("/vehicle-types", response_model=VehicleTypeOut, status_code=status.HTTP_201_CREATED)
def create_vehicle_type(
    body: VehicleTypeCreate, actor: SettingsAdmin, db: DbSession
) -> VehicleType:
    return vehicles_service.create_vehicle_type(db, actor=actor, data=body)


@router.patch("/vehicle-types/{type_id}", response_model=VehicleTypeOut)
def update_vehicle_type(
    type_id: uuid.UUID, body: VehicleTypeUpdate, actor: SettingsAdmin, db: DbSession
) -> VehicleType:
    return vehicles_service.update_vehicle_type(db, actor=actor, type_id=type_id, data=body)


@router.get("/vehicles", response_model=Page[VehicleOut])
def list_vehicles(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Query(max_length=100)] = None,
    vehicle_type_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    ownership_status: OwnershipStatus | None = None,
    expiry: vehicles_service.ExpiryFilter | None = None,
    sort: vehicles_service.VehicleSort = "code",
) -> Page[VehicleOut]:
    rows, total = vehicles_service.list_vehicles(
        db,
        params,
        q=q,
        vehicle_type_id=vehicle_type_id,
        is_active=is_active,
        ownership_status=ownership_status,
        expiry=expiry,
        sort=sort,
    )
    current = assignments_service.current_for_vehicles(db, [v.id for v in rows])
    return Page(
        items=[vehicle_out(v, current.get(v.id)) for v in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/vehicles", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
def create_vehicle(body: VehicleCreate, actor: Writer, db: DbSession) -> VehicleOut:
    return vehicle_out(vehicles_service.create_vehicle(db, actor=actor, data=body))


def _detail(db: DbSession, vehicle_id: uuid.UUID) -> VehicleOut:
    v = vehicles_service.get_vehicle(db, vehicle_id)
    return vehicle_out(v, assignments_service.current_for_vehicles(db, [v.id])[v.id])


@router.get("/vehicles/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: uuid.UUID, _: Reader, db: DbSession) -> VehicleOut:
    return _detail(db, vehicle_id)


@router.patch("/vehicles/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: uuid.UUID, body: VehicleUpdate, actor: Writer, db: DbSession
) -> VehicleOut:
    vehicles_service.update_vehicle(db, actor=actor, vehicle_id=vehicle_id, data=body)
    return _detail(db, vehicle_id)


@router.post("/vehicles/{vehicle_id}/activate", response_model=VehicleOut)
def activate_vehicle(
    vehicle_id: uuid.UUID, body: StatusChange, actor: Writer, db: DbSession
) -> VehicleOut:
    vehicles_service.set_vehicle_active(
        db, actor=actor, vehicle_id=vehicle_id, active=True, reason=body.reason
    )
    return _detail(db, vehicle_id)


@router.post("/vehicles/{vehicle_id}/deactivate", response_model=VehicleOut)
def deactivate_vehicle(
    vehicle_id: uuid.UUID, body: StatusChange, actor: Writer, db: DbSession
) -> VehicleOut:
    vehicles_service.set_vehicle_active(
        db, actor=actor, vehicle_id=vehicle_id, active=False, reason=body.reason
    )
    return _detail(db, vehicle_id)


@router.get("/vehicles/{vehicle_id}/assignments", response_model=Page[AssignmentOut])
def vehicle_assignments(
    vehicle_id: uuid.UUID,
    _: Annotated[User, Depends(require_permissions(Permission.ASSIGNMENTS_READ))],
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[AssignmentOut]:
    vehicles_service.get_vehicle(db, vehicle_id)
    rows, total = assignments_service.list_assignments(db, params, vehicle_id=vehicle_id)
    return Page(
        items=[assignment_out(a) for a in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


class TimelineItemOut(BaseModel):
    at: datetime | None
    kind: str
    title: str
    detail: str | None
    amount: Decimal | None
    status: str | None
    until: datetime | None
    link: str | None


SECTION_PERMISSIONS = {
    vehicle_timeline.Section.ASSIGNMENTS: Permission.ASSIGNMENTS_READ,
    vehicle_timeline.Section.SHIFTS: Permission.SHIFTS_READ,
    vehicle_timeline.Section.TRACKING: Permission.TRACKING_READ,
    vehicle_timeline.Section.FUEL: Permission.FUEL_READ,
    vehicle_timeline.Section.EXPENSES: Permission.EXPENSES_READ,
    vehicle_timeline.Section.REVENUE: Permission.REVENUE_READ,
    vehicle_timeline.Section.CASH: Permission.CASH_READ,
    vehicle_timeline.Section.MAINTENANCE: Permission.MAINTENANCE_READ,
    vehicle_timeline.Section.REVIEW: Permission.EXCEPTIONS_READ,
}


@router.get("/vehicles/{vehicle_id}/timeline", response_model=list[TimelineItemOut])
def vehicle_day_timeline(
    vehicle_id: uuid.UUID, user: Reader, db: DbSession, day: date | None = None
) -> list[TimelineItemOut]:
    """Vehicle daily timeline (U24); each kind only with its own read permission."""
    vehicles_service.get_vehicle(db, vehicle_id)
    sections = {s for s, p in SECTION_PERMISSIONS.items() if has_permission(user.role, p)}
    items = vehicle_timeline.timeline(db, vehicle_id, day or local_today(), sections)
    return [TimelineItemOut(**i.__dict__) for i in items]
