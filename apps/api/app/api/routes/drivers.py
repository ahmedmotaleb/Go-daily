"""Driver endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DbSession, require_permissions
from app.api.presenters import assignment_out, driver_out
from app.core.permissions import Permission
from app.models.driver import DriverCompensationPlan, EmploymentStatus
from app.models.user import User
from app.schemas.assignment import AssignmentOut
from app.schemas.common import Message, Page, PageParams, page_params
from app.schemas.driver import (
    CompensationPlanCreate,
    CompensationPlanOut,
    DriverAccountCreate,
    DriverCreate,
    DriverOut,
    DriverSensitiveOut,
    DriverUpdate,
)
from app.schemas.user import PasswordReset
from app.services import assignments as assignments_service
from app.services import drivers as drivers_service

router = APIRouter(prefix="/drivers", tags=["drivers"])

Reader = Annotated[User, Depends(require_permissions(Permission.DRIVERS_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.DRIVERS_WRITE))]


def _detail(db: DbSession, driver_id: uuid.UUID) -> DriverOut:
    d = drivers_service.get_driver(db, driver_id)
    return driver_out(d, assignments_service.current_for_drivers(db, [d.id])[d.id])


@router.get("", response_model=Page[DriverOut])
def list_drivers(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Query(max_length=100)] = None,
    employment_status: EmploymentStatus | None = None,
    license: drivers_service.LicenseFilter | None = None,
    has_account: bool | None = None,
) -> Page[DriverOut]:
    rows, total = drivers_service.list_drivers(
        db,
        params,
        q=q,
        employment_status=employment_status,
        license=license,
        has_account=has_account,
    )
    current = assignments_service.current_for_drivers(db, [d.id for d in rows])
    return Page(
        items=[driver_out(d, current.get(d.id)) for d in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("", response_model=DriverOut, status_code=status.HTTP_201_CREATED)
def create_driver(body: DriverCreate, actor: Writer, db: DbSession) -> DriverOut:
    return driver_out(drivers_service.create_driver(db, actor=actor, data=body))


@router.get("/{driver_id}", response_model=DriverOut)
def get_driver(driver_id: uuid.UUID, _: Reader, db: DbSession) -> DriverOut:
    return _detail(db, driver_id)


@router.patch("/{driver_id}", response_model=DriverOut)
def update_driver(
    driver_id: uuid.UUID, body: DriverUpdate, actor: Writer, db: DbSession
) -> DriverOut:
    drivers_service.update_driver(db, actor=actor, driver_id=driver_id, data=body)
    return _detail(db, driver_id)


@router.get("/{driver_id}/sensitive", response_model=DriverSensitiveOut)
def get_driver_sensitive(
    driver_id: uuid.UUID,
    actor: Annotated[User, Depends(require_permissions(Permission.DRIVERS_READ_SENSITIVE))],
    db: DbSession,
) -> DriverSensitiveOut:
    return DriverSensitiveOut(
        national_id=drivers_service.read_national_id(db, actor=actor, driver_id=driver_id)
    )


@router.post("/{driver_id}/account", response_model=DriverOut, status_code=status.HTTP_201_CREATED)
def create_driver_account(
    driver_id: uuid.UUID, body: DriverAccountCreate, actor: Writer, db: DbSession
) -> DriverOut:
    drivers_service.create_app_account(db, actor=actor, driver_id=driver_id, password=body.password)
    return _detail(db, driver_id)


@router.post("/{driver_id}/account/reset-password", response_model=Message)
def reset_driver_account_password(
    driver_id: uuid.UUID, body: PasswordReset, actor: Writer, db: DbSession
) -> Message:
    drivers_service.reset_app_password(
        db, actor=actor, driver_id=driver_id, password=body.new_password
    )
    return Message(message="تم تعيين كلمة مرور جديدة لتطبيق السائق")


@router.post("/{driver_id}/account/activate", response_model=DriverOut)
def activate_driver_account(driver_id: uuid.UUID, actor: Writer, db: DbSession) -> DriverOut:
    drivers_service.set_app_account_active(db, actor=actor, driver_id=driver_id, active=True)
    return _detail(db, driver_id)


@router.post("/{driver_id}/account/deactivate", response_model=DriverOut)
def deactivate_driver_account(driver_id: uuid.UUID, actor: Writer, db: DbSession) -> DriverOut:
    drivers_service.set_app_account_active(db, actor=actor, driver_id=driver_id, active=False)
    return _detail(db, driver_id)


@router.get("/{driver_id}/assignments", response_model=Page[AssignmentOut])
def driver_assignments(
    driver_id: uuid.UUID,
    _: Annotated[User, Depends(require_permissions(Permission.ASSIGNMENTS_READ))],
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[AssignmentOut]:
    drivers_service.get_driver(db, driver_id)
    rows, total = assignments_service.list_assignments(db, params, driver_id=driver_id)
    return Page(
        items=[assignment_out(a) for a in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


# Compensation terms are payroll data: finance permissions, not drivers:read.
@router.get("/{driver_id}/compensation-plans", response_model=list[CompensationPlanOut])
def list_compensation_plans(
    driver_id: uuid.UUID,
    _: Annotated[User, Depends(require_permissions(Permission.SETTLEMENTS_READ))],
    db: DbSession,
) -> list[DriverCompensationPlan]:
    return drivers_service.list_compensation_plans(db, driver_id)


@router.post(
    "/{driver_id}/compensation-plans",
    response_model=CompensationPlanOut,
    status_code=status.HTTP_201_CREATED,
)
def add_compensation_plan(
    driver_id: uuid.UUID,
    body: CompensationPlanCreate,
    actor: Annotated[User, Depends(require_permissions(Permission.SETTLEMENTS_WRITE))],
    db: DbSession,
) -> DriverCompensationPlan:
    return drivers_service.add_compensation_plan(db, actor=actor, driver_id=driver_id, data=body)
