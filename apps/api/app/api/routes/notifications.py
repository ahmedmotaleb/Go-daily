"""In-app notifications for the signed-in user (Task 22)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission
from app.models.notifications import Notification
from app.models.user import User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.notifications import GenerateOut, MarkedOut, NotificationOut, UnreadCountOut
from app.services import notifications as notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])

Reader = Annotated[User, Depends(require_permissions(Permission.NOTIFICATIONS_READ))]
Admin = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]


@router.get("", response_model=Page[NotificationOut])
def inbox(
    user: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    unread_only: bool = False,
    include_cleared: bool = False,
) -> Page[NotificationOut]:
    rows, total = notification_service.list_for(
        db, user, params, unread_only=unread_only, include_cleared=include_cleared
    )
    return Page(
        items=[NotificationOut.model_validate(n) for n in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(user: Reader, db: DbSession) -> UnreadCountOut:
    return UnreadCountOut(**notification_service.unread_counts(db, user))


@router.post("/read-all", response_model=MarkedOut)
def read_all(user: Reader, db: DbSession) -> MarkedOut:
    return MarkedOut(marked=notification_service.mark_all_read(db, user))


@router.post("/generate", response_model=GenerateOut)
def generate(_: Admin, db: DbSession) -> GenerateOut:
    """Run the generators now (normally scheduled with the CLI)."""
    return GenerateOut(**notification_service.generate(db))


@router.post("/{notification_id}/read", response_model=NotificationOut)
def read(notification_id: uuid.UUID, user: Reader, db: DbSession) -> Notification:
    return notification_service.mark_read(db, user, notification_id)
