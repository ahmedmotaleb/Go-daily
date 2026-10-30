"""Shift and operation session endpoints (staff)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, require_permissions
from app.api.presenters import session_out, shift_out
from app.core.permissions import Permission
from app.models.shift import ShiftStatus
from app.models.user import User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.shift import (
    OdometerCorrection,
    SessionCancel,
    SessionEnd,
    SessionOut,
    SessionStart,
    ShiftCancel,
    ShiftCreate,
    ShiftEnd,
    ShiftOut,
    ShiftStart,
    ShiftUpdate,
)
from app.services import shifts as shifts_service

router = APIRouter(tags=["shifts"])

Reader = Annotated[User, Depends(require_permissions(Permission.SHIFTS_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.SHIFTS_WRITE))]


@router.get("/shifts", response_model=Page[ShiftOut])
def list_shifts(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    status: ShiftStatus | None = None,
    driver_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    day: date | None = None,
) -> Page[ShiftOut]:
    rows, total = shifts_service.list_shifts(
        db, params, status=status, driver_id=driver_id, vehicle_id=vehicle_id, day=day
    )
    return Page(
        items=[shift_out(s) for s in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/shifts", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
def create_shift(body: ShiftCreate, actor: Writer, db: DbSession) -> ShiftOut:
    return shift_out(shifts_service.create_shift(db, actor=actor, data=body))


@router.get("/shifts/{shift_id}", response_model=ShiftOut)
def get_shift(shift_id: uuid.UUID, _: Reader, db: DbSession) -> ShiftOut:
    return shift_out(shifts_service.get_shift(db, shift_id))


@router.patch("/shifts/{shift_id}", response_model=ShiftOut)
def update_shift(shift_id: uuid.UUID, body: ShiftUpdate, actor: Writer, db: DbSession) -> ShiftOut:
    return shift_out(shifts_service.update_shift(db, actor=actor, shift_id=shift_id, data=body))


@router.post("/shifts/{shift_id}/start", response_model=ShiftOut)
def start_shift(shift_id: uuid.UUID, body: ShiftStart, actor: Writer, db: DbSession) -> ShiftOut:
    return shift_out(shifts_service.start_shift(db, actor=actor, shift_id=shift_id, data=body))


@router.post("/shifts/{shift_id}/end", response_model=ShiftOut)
def end_shift(shift_id: uuid.UUID, body: ShiftEnd, actor: Writer, db: DbSession) -> ShiftOut:
    return shift_out(shifts_service.end_shift(db, actor=actor, shift_id=shift_id, data=body))


@router.post("/shifts/{shift_id}/cancel", response_model=ShiftOut)
def cancel_shift(shift_id: uuid.UUID, body: ShiftCancel, actor: Writer, db: DbSession) -> ShiftOut:
    return shift_out(
        shifts_service.cancel_shift(db, actor=actor, shift_id=shift_id, reason=body.reason)
    )


@router.post("/shifts/{shift_id}/odometer-correction", response_model=ShiftOut)
def correct_odometer(
    shift_id: uuid.UUID, body: OdometerCorrection, actor: Writer, db: DbSession
) -> ShiftOut:
    return shift_out(shifts_service.correct_odometer(db, actor=actor, shift_id=shift_id, data=body))


@router.post(
    "/shifts/{shift_id}/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED
)
def start_session(
    shift_id: uuid.UUID, body: SessionStart, actor: Writer, db: DbSession
) -> SessionOut:
    return session_out(shifts_service.start_session(db, actor=actor, shift_id=shift_id, data=body))


@router.post("/operation-sessions/{session_id}/end", response_model=SessionOut)
def end_session(
    session_id: uuid.UUID, body: SessionEnd, actor: Writer, db: DbSession
) -> SessionOut:
    return session_out(
        shifts_service.end_session(db, actor=actor, session_id=session_id, data=body)
    )


@router.post("/operation-sessions/{session_id}/cancel", response_model=SessionOut)
def cancel_session(
    session_id: uuid.UUID, body: SessionCancel, actor: Writer, db: DbSession
) -> SessionOut:
    return session_out(
        shifts_service.cancel_session(db, actor=actor, session_id=session_id, reason=body.reason)
    )
