"""Assignment endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, require_permissions
from app.api.presenters import assignment_out
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.assignment import (
    AssignmentCorrection,
    AssignmentCreate,
    AssignmentEnd,
    AssignmentOut,
)
from app.schemas.common import Page, PageParams, page_params
from app.services import assignments as assignments_service

router = APIRouter(prefix="/assignments", tags=["assignments"])

Reader = Annotated[User, Depends(require_permissions(Permission.ASSIGNMENTS_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.ASSIGNMENTS_WRITE))]


@router.get("", response_model=Page[AssignmentOut])
def list_assignments(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    driver_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    active: bool = False,
) -> Page[AssignmentOut]:
    rows, total = assignments_service.list_assignments(
        db, params, driver_id=driver_id, vehicle_id=vehicle_id, active_only=active
    )
    return Page(
        items=[assignment_out(a) for a in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(body: AssignmentCreate, actor: Writer, db: DbSession) -> AssignmentOut:
    return assignment_out(assignments_service.create_assignment(db, actor=actor, data=body))


@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: uuid.UUID, _: Reader, db: DbSession) -> AssignmentOut:
    return assignment_out(assignments_service.get_assignment(db, assignment_id))


@router.post("/{assignment_id}/end", response_model=AssignmentOut)
def end_assignment(
    assignment_id: uuid.UUID, body: AssignmentEnd, actor: Writer, db: DbSession
) -> AssignmentOut:
    return assignment_out(
        assignments_service.end_assignment(db, actor=actor, assignment_id=assignment_id, data=body)
    )


@router.patch("/{assignment_id}", response_model=AssignmentOut)
def correct_assignment(
    assignment_id: uuid.UUID, body: AssignmentCorrection, actor: Writer, db: DbSession
) -> AssignmentOut:
    return assignment_out(
        assignments_service.correct_assignment(
            db, actor=actor, assignment_id=assignment_id, data=body
        )
    )
