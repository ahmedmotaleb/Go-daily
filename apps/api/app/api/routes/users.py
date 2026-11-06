"""User management endpoints (staff only)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission, UserRole
from app.models.user import User
from app.schemas.common import Message, Page, PageParams, page_params
from app.schemas.user import PasswordReset, UserCreate, UserOut, UserUpdate
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])

Reader = Annotated[User, Depends(require_permissions(Permission.USERS_READ))]
Manager = Annotated[User, Depends(require_permissions(Permission.USERS_MANAGE))]


@router.get("", response_model=Page[UserOut])
def list_users(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Query(max_length=100)] = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> Page[UserOut]:
    rows, total = users_service.list_users(db, params, q=q, role=role, is_active=is_active)
    return Page(
        items=[UserOut.model_validate(u) for u in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, actor: Manager, db: DbSession) -> User:
    return users_service.create_user(db, actor=actor, data=body)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, _: Reader, db: DbSession) -> User:
    return users_service.get_user(db, user_id)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, actor: Manager, db: DbSession) -> User:
    return users_service.update_user(db, actor=actor, user_id=user_id, data=body)


@router.post("/{user_id}/reset-password", response_model=Message)
def reset_password(
    user_id: uuid.UUID, body: PasswordReset, actor: Manager, db: DbSession
) -> Message:
    users_service.reset_password(db, actor=actor, user_id=user_id, new_password=body.new_password)
    return Message(message="تم تعيين كلمة مرور جديدة وإنهاء جلسات المستخدم")
