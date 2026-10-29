"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentSession, CurrentUser, DbSession
from app.core.permissions import permissions_for
from app.models.user import ClientType, User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse
from app.schemas.common import Message
from app.schemas.user import CurrentUserOut, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def current_user_out(user: User) -> CurrentUserOut:
    return CurrentUserOut(
        **UserOut.model_validate(user).model_dump(),
        permissions=sorted(p.value for p in permissions_for(user.role)),
    )


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: DbSession) -> LoginResponse:
    result = auth_service.login(
        db,
        phone=body.phone,
        password=body.password,
        client=ClientType.WEB if body.client == "web" else ClientType.MOBILE,
        device_name=body.device_name,
    )
    return LoginResponse(
        access_token=result.token,
        expires_at=result.session.expires_at,
        user=current_user_out(result.user),
    )


@router.post("/logout", response_model=Message)
def logout(session: CurrentSession, db: DbSession) -> Message:
    auth_service.logout(db, session)
    return Message(message="تم تسجيل الخروج")


@router.get("/me", response_model=CurrentUserOut)
def me(user: CurrentUser) -> CurrentUserOut:
    return current_user_out(user)


@router.post("/change-password", response_model=Message, status_code=status.HTTP_200_OK)
def change_password(body: ChangePasswordRequest, session: CurrentSession, db: DbSession) -> Message:
    auth_service.change_password(
        db,
        session=session,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    return Message(message="تم تغيير كلمة المرور")
