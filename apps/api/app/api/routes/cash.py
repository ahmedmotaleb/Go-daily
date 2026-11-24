"""Staff endpoints: the daily cash board, collections, close-outs and day-offs."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DbSession, require_permissions
from app.core.errors import NotFoundError
from app.core.permissions import Permission
from app.core.time import local_today
from app.models.driver import Driver
from app.models.finance import RecordSource
from app.models.user import User
from app.schemas.cash import (
    CancelIn,
    CashAccountOut,
    CashBoardOut,
    CloseoutOut,
    CollectionIn,
    CollectionOut,
    DayOffOut,
    StaffCloseoutIn,
    StaffDayOffIn,
    VoidIn,
)
from app.services import cash, cash_views, day_offs

router = APIRouter(tags=["cash"])

CashReader = Annotated[User, Depends(require_permissions(Permission.CASH_READ))]
Collector = Annotated[User, Depends(require_permissions(Permission.CASH_COLLECT))]
ShiftReader = Annotated[User, Depends(require_permissions(Permission.SHIFTS_READ))]
ShiftWriter = Annotated[User, Depends(require_permissions(Permission.SHIFTS_WRITE))]


@router.get("/cash/board", response_model=CashBoardOut)
def cash_board(_: CashReader, db: DbSession, day: date | None = None) -> CashBoardOut:
    """«تحصيل نقدية السائقين» for one day (default today, Cairo)."""
    return cash_views.board(db, day or local_today())


@router.get("/cash/closeouts/{closeout_id}", response_model=CloseoutOut)
def get_closeout(closeout_id: uuid.UUID, _: CashReader, db: DbSession) -> CloseoutOut:
    return cash_views.closeout_detail(db, closeout_id)


@router.post("/cash/closeouts/{closeout_id}/void", response_model=CloseoutOut)
def void_closeout(
    closeout_id: uuid.UUID, body: VoidIn, actor: Collector, db: DbSession
) -> CloseoutOut:
    cash.void_closeout(db, actor=actor, closeout_id=closeout_id, reason=body.reason)
    return cash_views.closeout_detail(db, closeout_id)


@router.post(
    "/cash/shifts/{shift_id}/closeout",
    response_model=CloseoutOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_closeout(
    shift_id: uuid.UUID, body: StaffCloseoutIn, actor: Collector, db: DbSession
) -> CloseoutOut:
    """Office entry of a close-out on the driver's behalf."""
    closeout = cash.submit(db, actor=actor, shift_id=shift_id, data=body, source=RecordSource.ADMIN)
    return cash_views.closeout_detail(db, closeout.id)


@router.post("/cash/collections", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
def record_collection(body: CollectionIn, actor: Collector, db: DbSession) -> CollectionOut:
    """«تأكيد: تم التحصيل»: cash actually received; the rest carries over."""
    collection = cash.collect(
        db,
        actor=actor,
        driver_id=body.driver_id,
        amount=body.amount,
        closeout_id=body.closeout_id,
        note=body.note,
    )
    return cash_views.collection_out(collection)


@router.post("/cash/collections/{collection_id}/void", response_model=CollectionOut)
def void_collection(
    collection_id: uuid.UUID, body: VoidIn, actor: Collector, db: DbSession
) -> CollectionOut:
    collection = cash.void_collection(
        db, actor=actor, collection_id=collection_id, reason=body.reason
    )
    return cash_views.collection_out(collection)


@router.get("/drivers/{driver_id}/cash-account", response_model=CashAccountOut)
def driver_cash_account(
    driver_id: uuid.UUID,
    _: CashReader,
    db: DbSession,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> CashAccountOut:
    if db.get(Driver, driver_id) is None:
        raise NotFoundError("السائق غير موجود")
    return cash_views.account(db, driver_id, days)


@router.get("/day-offs", response_model=list[DayOffOut])
def list_day_offs(_: ShiftReader, db: DbSession, day: date | None = None) -> list[DayOffOut]:
    return [cash_views.day_off_out(o) for o in day_offs.for_day(db, day or local_today())]


@router.post("/day-offs", response_model=DayOffOut, status_code=status.HTTP_201_CREATED)
def register_day_off(body: StaffDayOffIn, actor: ShiftWriter, db: DbSession) -> DayOffOut:
    off = day_offs.register(
        db,
        actor=actor,
        driver_id=body.driver_id,
        day=body.day,
        note=body.note,
        source=RecordSource.ADMIN,
    )
    return cash_views.day_off_out(off)


@router.post("/day-offs/{day_off_id}/cancel", response_model=DayOffOut)
def cancel_day_off(
    day_off_id: uuid.UUID, body: CancelIn, actor: ShiftWriter, db: DbSession
) -> DayOffOut:
    off = day_offs.cancel_by_id(db, actor=actor, day_off_id=day_off_id, reason=body.reason)
    return cash_views.day_off_out(off)
