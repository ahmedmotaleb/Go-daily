"""Driver-app endpoints for the daily workflow: day-off, start photo, close-out, account.

Everything is scoped to the logged-in driver. Writes accept an
`Idempotency-Key` header so a retry after a lost response is safe.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request, UploadFile, status

from app.api.deps import CurrentDriver, CurrentDriverUser, DbSession
from app.api.routes.attachments import read_limited
from app.core.errors import NotFoundError
from app.core.time import local_today
from app.models.attachment import AttachmentKind, AttachmentOwner
from app.models.cash import ShiftCloseout
from app.models.finance import RecordSource
from app.schemas.cash import CashAccountOut, CloseoutIn, CloseoutOut, DayOffIn, DayOffOut, PhotoOut
from app.services import attachments as attachments_service
from app.services import cash, cash_views, day_offs, idempotency

router = APIRouter(prefix="/driver", tags=["driver-app"])

IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.get("/day-off", response_model=DayOffOut | None)
def today_day_off(driver: CurrentDriver, db: DbSession) -> DayOffOut | None:
    off = day_offs.live(db, driver.id, local_today())
    return cash_views.day_off_out(off) if off else None


@router.post("/day-off", response_model=DayOffOut, status_code=status.HTTP_201_CREATED)
def register_day_off(
    body: DayOffIn,
    request: Request,
    driver: CurrentDriver,
    user: CurrentDriverUser,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> Any:
    """«تسجيل اليوم إجازة» for today: no shift can start and nothing is tracked."""

    def action() -> DayOffOut:
        off = day_offs.register(
            db,
            actor=user,
            driver_id=driver.id,
            day=local_today(),
            note=body.note,
            source=RecordSource.DRIVER_APP,
        )
        return cash_views.day_off_out(off)

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


@router.post("/day-off/cancel", response_model=DayOffOut)
def cancel_day_off(driver: CurrentDriver, user: CurrentDriverUser, db: DbSession) -> DayOffOut:
    off = day_offs.cancel(
        db, actor=user, driver_id=driver.id, day=local_today(), reason="ألغاها السائق"
    )
    return cash_views.day_off_out(off)


@router.post("/odometer-photo", response_model=PhotoOut, status_code=status.HTTP_201_CREATED)
async def upload_odometer_photo(
    file: UploadFile, driver: CurrentDriver, user: CurrentDriverUser, db: DbSession
) -> PhotoOut:
    """Odometer photo taken right before starting; its id goes with the start request."""
    data = await read_limited(file)
    attachment, _ = attachments_service.upload(
        db,
        actor=user,
        owner_type=AttachmentOwner.DRIVER,
        owner_id=driver.id,
        data=data,
        filename=file.filename,
        kind=AttachmentKind.ODOMETER_PHOTO,
    )
    return PhotoOut(attachment_id=attachment.id, created_at=attachment.created_at)


@router.post(
    "/shifts/{shift_id}/closeout",
    response_model=CloseoutOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_closeout(
    shift_id: uuid.UUID,
    body: CloseoutIn,
    request: Request,
    driver: CurrentDriver,
    user: CurrentDriverUser,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> Any:
    """«إنهاء وتقفيل الوردية»: ends the shift and records the day's money in one step."""

    def action() -> CloseoutOut:
        closeout = cash.submit(
            db,
            actor=user,
            shift_id=shift_id,
            data=body,
            source=RecordSource.DRIVER_APP,
            driver_id=driver.id,
        )
        return cash_views.closeout_detail(db, closeout.id)

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


@router.post(
    "/closeouts/{closeout_id}/receipt",
    response_model=PhotoOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_closeout_receipt(
    closeout_id: uuid.UUID,
    file: UploadFile,
    driver: CurrentDriver,
    user: CurrentDriverUser,
    db: DbSession,
) -> PhotoOut:
    """Photo of the fuel receipt(s) for the driver's own close-out."""
    closeout = db.get(ShiftCloseout, closeout_id)
    if closeout is None or closeout.driver_id != driver.id or closeout.voided_at is not None:
        raise NotFoundError("التقفيل غير موجود")
    data = await read_limited(file)
    attachment, _ = attachments_service.upload(
        db,
        actor=user,
        owner_type=AttachmentOwner.SHIFT_CLOSEOUT,
        owner_id=closeout.id,
        data=data,
        filename=file.filename,
    )
    return PhotoOut(attachment_id=attachment.id, created_at=attachment.created_at)


@router.get("/account", response_model=CashAccountOut)
def my_account(
    driver: CurrentDriver,
    db: DbSession,
    days: Annotated[int, Query(ge=1, le=60)] = 14,
) -> CashAccountOut:
    """«حسابي مع الإدارة»: what was handed over, what is still due, and day-offs."""
    return cash_views.account(db, driver.id, days)
