"""Fuel, CNG, oil and consumables endpoints (Task 15)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, require_permissions
from app.api.finance_presenters import fuel_outs
from app.core.permissions import Permission, has_permission
from app.models.finance import FuelCategory, FuelType, RecordStatus
from app.models.user import User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.finance import (
    FuelCorrection,
    FuelCreate,
    FuelOut,
    FuelSummary,
    FuelTypeCreate,
    FuelTypeOut,
    FuelTypeUpdate,
    FuelUpdate,
    RejectAction,
    ReviewAction,
    VoidAction,
)
from app.services import fuel as fuel_service

router = APIRouter(tags=["fuel"])

Reader = Annotated[User, Depends(require_permissions(Permission.FUEL_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.FUEL_WRITE))]
Approver = Annotated[User, Depends(require_permissions(Permission.EXPENSES_APPROVE))]
SettingsAdmin = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]


def _filters(
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    fuel_type_id: uuid.UUID | None = None,
    category: FuelCategory | None = None,
    status: RecordStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> fuel_service.FuelFilters:
    return fuel_service.FuelFilters(
        vehicle_id=vehicle_id,
        driver_id=driver_id,
        fuel_type_id=fuel_type_id,
        category=category,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )


Filters = Annotated[fuel_service.FuelFilters, Depends(_filters)]


@router.get("/fuel-types", response_model=list[FuelTypeOut])
def list_fuel_types(_: Reader, db: DbSession, include_inactive: bool = False) -> list[FuelType]:
    return fuel_service.list_types(db, include_inactive=include_inactive)


@router.post("/fuel-types", response_model=FuelTypeOut, status_code=status.HTTP_201_CREATED)
def create_fuel_type(body: FuelTypeCreate, actor: SettingsAdmin, db: DbSession) -> FuelType:
    return fuel_service.create_type(db, actor=actor, data=body)


@router.patch("/fuel-types/{type_id}", response_model=FuelTypeOut)
def update_fuel_type(
    type_id: uuid.UUID, body: FuelTypeUpdate, actor: SettingsAdmin, db: DbSession
) -> FuelType:
    return fuel_service.update_type(db, actor=actor, type_id=type_id, data=body)


@router.get("/fuel", response_model=Page[FuelOut])
def list_fuel(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    filters: Filters,
) -> Page[FuelOut]:
    rows, total = fuel_service.list_transactions(db, params, filters)
    return Page(
        items=fuel_outs(db, rows), total=total, page=params.page, page_size=params.page_size
    )


@router.get("/fuel/summary", response_model=FuelSummary)
def fuel_summary(_: Reader, db: DbSession, filters: Filters) -> dict[str, object]:
    return fuel_service.summary(db, filters)


@router.post("/fuel", response_model=FuelOut, status_code=status.HTTP_201_CREATED)
def create_fuel(body: FuelCreate, actor: Writer, db: DbSession) -> FuelOut:
    tx = fuel_service.create(
        db,
        actor=actor,
        data=body,
        can_approve=has_permission(actor.role, Permission.EXPENSES_APPROVE),
    )
    return fuel_outs(db, [tx])[0]


@router.get("/fuel/{tx_id}", response_model=FuelOut)
def get_fuel(tx_id: uuid.UUID, _: Reader, db: DbSession) -> FuelOut:
    return fuel_outs(db, [fuel_service.get(db, tx_id)])[0]


@router.patch("/fuel/{tx_id}", response_model=FuelOut)
def update_fuel(tx_id: uuid.UUID, body: FuelUpdate, actor: Writer, db: DbSession) -> FuelOut:
    return fuel_outs(db, [fuel_service.update(db, actor=actor, tx_id=tx_id, data=body)])[0]


@router.post("/fuel/{tx_id}/approve", response_model=FuelOut)
def approve_fuel(tx_id: uuid.UUID, body: ReviewAction, actor: Approver, db: DbSession) -> FuelOut:
    return fuel_outs(db, [fuel_service.approve(db, actor=actor, tx_id=tx_id, note=body.note)])[0]


@router.post("/fuel/{tx_id}/reject", response_model=FuelOut)
def reject_fuel(tx_id: uuid.UUID, body: RejectAction, actor: Approver, db: DbSession) -> FuelOut:
    return fuel_outs(db, [fuel_service.reject(db, actor=actor, tx_id=tx_id, reason=body.reason)])[0]


@router.post("/fuel/{tx_id}/void", response_model=FuelOut)
def void_fuel(tx_id: uuid.UUID, body: VoidAction, actor: Approver, db: DbSession) -> FuelOut:
    return fuel_outs(db, [fuel_service.void(db, actor=actor, tx_id=tx_id, reason=body.reason)])[0]


@router.post("/fuel/{tx_id}/correct", response_model=FuelOut, status_code=status.HTTP_201_CREATED)
def correct_fuel(tx_id: uuid.UUID, body: FuelCorrection, actor: Approver, db: DbSession) -> FuelOut:
    tx = fuel_service.correct(db, actor=actor, tx_id=tx_id, data=body, can_approve=True)
    return fuel_outs(db, [tx])[0]
