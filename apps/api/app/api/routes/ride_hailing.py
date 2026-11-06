"""Ride-hailing platforms, statements and reconciliation (Task 14)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, require_permissions
from app.api.finance_presenters import statement_outs
from app.core.errors import ValidationFailed
from app.core.permissions import Permission, has_permission
from app.models.finance import RecordStatus, RideHailingPlatform
from app.models.user import User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.finance import (
    PlatformCreate,
    PlatformOut,
    PlatformUpdate,
    Reconciliation,
    ReconciliationFlag,
    ReconciliationRow,
    Ref,
    RejectAction,
    ReviewAction,
    StatementCorrection,
    StatementCreate,
    StatementFields,
    StatementOut,
    VoidAction,
)
from app.services import ride_hailing as rh

router = APIRouter(prefix="/ride-hailing", tags=["ride-hailing"])

Reader = Annotated[User, Depends(require_permissions(Permission.REVENUE_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.REVENUE_WRITE))]
Approver = Annotated[User, Depends(require_permissions(Permission.REVENUE_APPROVE))]
SettingsAdmin = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]


@router.get("/platforms", response_model=list[PlatformOut])
def list_platforms(
    _: Reader, db: DbSession, include_inactive: bool = False
) -> list[RideHailingPlatform]:
    return rh.list_platforms(db, include_inactive=include_inactive)


@router.post("/platforms", response_model=PlatformOut, status_code=status.HTTP_201_CREATED)
def create_platform(
    body: PlatformCreate, actor: SettingsAdmin, db: DbSession
) -> RideHailingPlatform:
    return rh.create_platform(db, actor=actor, data=body)


@router.patch("/platforms/{platform_id}", response_model=PlatformOut)
def update_platform(
    platform_id: uuid.UUID, body: PlatformUpdate, actor: SettingsAdmin, db: DbSession
) -> RideHailingPlatform:
    return rh.update_platform(db, actor=actor, platform_id=platform_id, data=body)


@router.get("/statements", response_model=Page[StatementOut])
def list_statements(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    platform_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    status: RecordStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page[StatementOut]:
    rows, total = rh.list_statements(
        db,
        params,
        rh.StatementFilters(
            platform_id=platform_id,
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
        ),
    )
    return Page(
        items=statement_outs(db, rows), total=total, page=params.page, page_size=params.page_size
    )


@router.post("/statements", response_model=StatementOut, status_code=status.HTTP_201_CREATED)
def create_statement(body: StatementCreate, actor: Writer, db: DbSession) -> StatementOut:
    statement = rh.create(
        db,
        actor=actor,
        data=body,
        can_approve=has_permission(actor.role, Permission.REVENUE_APPROVE),
    )
    return statement_outs(db, [statement])[0]


@router.get("/statements/{statement_id}", response_model=StatementOut)
def get_statement(statement_id: uuid.UUID, _: Reader, db: DbSession) -> StatementOut:
    return statement_outs(db, [rh.get(db, statement_id)])[0]


@router.put("/statements/{statement_id}", response_model=StatementOut)
def update_statement(
    statement_id: uuid.UUID, body: StatementFields, actor: Writer, db: DbSession
) -> StatementOut:
    statement = rh.update(db, actor=actor, statement_id=statement_id, data=body)
    return statement_outs(db, [statement])[0]


@router.post("/statements/{statement_id}/approve", response_model=StatementOut)
def approve_statement(
    statement_id: uuid.UUID, body: ReviewAction, actor: Approver, db: DbSession
) -> StatementOut:
    statement = rh.approve(db, actor=actor, statement_id=statement_id, note=body.note)
    return statement_outs(db, [statement])[0]


@router.post("/statements/{statement_id}/reject", response_model=StatementOut)
def reject_statement(
    statement_id: uuid.UUID, body: RejectAction, actor: Approver, db: DbSession
) -> StatementOut:
    statement = rh.reject(db, actor=actor, statement_id=statement_id, reason=body.reason)
    return statement_outs(db, [statement])[0]


@router.post("/statements/{statement_id}/void", response_model=StatementOut)
def void_statement(
    statement_id: uuid.UUID, body: VoidAction, actor: Approver, db: DbSession
) -> StatementOut:
    statement = rh.void(db, actor=actor, statement_id=statement_id, reason=body.reason)
    return statement_outs(db, [statement])[0]


@router.post(
    "/statements/{statement_id}/correct",
    response_model=StatementOut,
    status_code=status.HTTP_201_CREATED,
)
def correct_statement(
    statement_id: uuid.UUID, body: StatementCorrection, actor: Approver, db: DbSession
) -> StatementOut:
    statement = rh.correct(db, actor=actor, statement_id=statement_id, data=body, can_approve=True)
    return statement_outs(db, [statement])[0]


def _row(db: DbSession, row: rh.ReconRow) -> ReconciliationRow:
    return ReconciliationRow(
        statement=statement_outs(db, [row.statement])[0] if row.statement else None,
        driver=Ref(id=row.driver.id, name=row.driver.full_name),
        vehicle=Ref(id=row.vehicle.id, name=row.vehicle.internal_code),
        period_start=row.period_start,
        period_end=row.period_end,
        shifts_count=row.shifts_count,
        ride_hailing_minutes=row.ride_hailing_minutes,
        odometer_km=row.odometer_km,
        gps_km=row.gps_km,
        net_per_hour=row.net_per_hour,
        net_per_km=row.net_per_km,
        flags=[ReconciliationFlag(code=c, message=m) for c, m in row.flags],
    )


@router.get("/reconciliation", response_model=Reconciliation)
def reconciliation(
    _: Reader,
    db: DbSession,
    date_from: date,
    date_to: date,
    driver_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
) -> Reconciliation:
    if date_to < date_from or (date_to - date_from).days > 92:
        raise ValidationFailed("اختر فترة صحيحة لا تتجاوز ثلاثة أشهر", code="invalid_range")
    rows, uncovered = rh.reconciliation(
        db, date_from=date_from, date_to=date_to, driver_id=driver_id, vehicle_id=vehicle_id
    )
    return Reconciliation(
        rows=[_row(db, r) for r in rows], uncovered=[_row(db, r) for r in uncovered]
    )
