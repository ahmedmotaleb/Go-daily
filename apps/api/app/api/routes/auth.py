"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import CurrentSession, CurrentUser, DbSession
from app.core import ratelimit
from app.core.config import get_settings
from app.core.errors import PermissionDenied, TooManyRequests
from app.core.permissions import STAFF_ROLES, permissions_for
from app.models.user import ClientType, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginCodeRequest,
    LoginRequest,
    LoginResponse,
    RecoveryCodesOut,
    TwoFactorCodeIn,
    TwoFactorReauthIn,
    TwoFactorSetupOut,
    TwoFactorStatusOut,
)
from app.schemas.common import Message
from app.schemas.user import CurrentUserOut, UserOut
from app.services import auth as auth_service
from app.services import two_factor

router = APIRouter(prefix="/auth", tags=["auth"])


def _staff(user: CurrentUser) -> User:
    # Two-factor login is for the admin web; driver accounts use the app.
    if user.role not in STAFF_ROLES:
        raise PermissionDenied()
    return user


StaffUser = Annotated[User, Depends(_staff)]


def current_user_out(user: User) -> CurrentUserOut:
    return CurrentUserOut(
        **UserOut.model_validate(user).model_dump(),
        permissions=sorted(p.value for p in permissions_for(user.role)),
        twofa_required=two_factor.required_for(user.role),
        twofa_setup_required=two_factor.setup_needed(user),
    )


def _login_out(result: auth_service.LoginResult) -> LoginResponse:
    if result.challenge is not None:
        return LoginResponse(twofa_required=True, challenge=result.challenge)
    assert result.session is not None  # noqa: S101
    return LoginResponse(
        access_token=result.token,
        expires_at=result.session.expires_at,
        user=current_user_out(result.user),
    )


def _limit(request: Request, limiter: ratelimit.RateLimiter | None = None) -> None:
    retry_after = (limiter or login_limiter).hit(
        request.client.host if request.client else "unknown"
    )
    if retry_after is not None:
        raise TooManyRequests(
            "محاولات دخول كثيرة من هذا الجهاز، حاول بعد قليل",
            code="rate_limited",
            details={"retry_after_seconds": retry_after},
        )


_settings = get_settings()
_redis = _settings.redis_url.get_secret_value() if _settings.redis_url else None
# U32: shared through Redis when REDIS_URL is set (see app.core.ratelimit).
login_limiter = ratelimit.build(
    "login", _settings.login_rate_limit, _settings.login_rate_window_seconds, _redis
)
code_limiter = ratelimit.build(
    "login_2fa", _settings.login_rate_limit, _settings.login_rate_window_seconds, _redis
)
sensitive_limiter = ratelimit.build(
    "sensitive", _settings.sensitive_rate_limit, _settings.sensitive_rate_window_seconds, _redis
)


def _limit_user(user: User) -> None:
    retry_after = sensitive_limiter.hit(f"user:{user.id}")
    if retry_after is not None:
        raise TooManyRequests(
            "محاولات كثيرة، حاول بعد قليل",
            code="rate_limited",
            details={"retry_after_seconds": retry_after},
        )


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: DbSession) -> LoginResponse:
    _limit(request)
    result = auth_service.login(
        db,
        phone=body.phone,
        password=body.password,
        client=ClientType.WEB if body.client == "web" else ClientType.MOBILE,
        device_name=body.device_name,
    )
    return _login_out(result)


@router.post("/login/2fa", response_model=LoginResponse)
def login_code(body: LoginCodeRequest, request: Request, db: DbSession) -> LoginResponse:
    """Second step: the code from the authenticator app, or a recovery code."""
    _limit(request, code_limiter)
    return _login_out(auth_service.login_with_code(db, challenge=body.challenge, code=body.code))


@router.get("/2fa", response_model=TwoFactorStatusOut)
def twofa_status(user: CurrentUser, db: DbSession) -> TwoFactorStatusOut:
    return TwoFactorStatusOut(
        enabled=two_factor.enabled(user),
        required=two_factor.required_for(user.role),
        recovery_codes_left=two_factor.recovery_left(db, user),
    )


@router.post("/2fa/setup", response_model=TwoFactorSetupOut)
def twofa_setup(user: StaffUser, db: DbSession) -> TwoFactorSetupOut:
    secret, uri = two_factor.setup(db, user=user)
    return TwoFactorSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/2fa/enable", response_model=RecoveryCodesOut)
def twofa_enable(body: TwoFactorCodeIn, user: StaffUser, db: DbSession) -> RecoveryCodesOut:
    _limit_user(user)
    return RecoveryCodesOut(recovery_codes=two_factor.enable(db, user=user, code=body.code))


@router.post("/2fa/disable", response_model=Message)
def twofa_disable(body: TwoFactorReauthIn, user: StaffUser, db: DbSession) -> Message:
    _limit_user(user)
    two_factor.disable(db, user=user, password=body.password, code=body.code)
    return Message(message="تم إيقاف التحقق بخطوتين")


@router.post("/2fa/recovery-codes", response_model=RecoveryCodesOut)
def twofa_recovery_codes(
    body: TwoFactorReauthIn, user: StaffUser, db: DbSession
) -> RecoveryCodesOut:
    _limit_user(user)
    codes = two_factor.regenerate_codes(db, user=user, password=body.password, code=body.code)
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/logout", response_model=Message)
def logout(session: CurrentSession, db: DbSession) -> Message:
    auth_service.logout(db, session)
    return Message(message="تم تسجيل الخروج")


@router.get("/me", response_model=CurrentUserOut)
def me(user: CurrentUser) -> CurrentUserOut:
    return current_user_out(user)


@router.post("/change-password", response_model=Message, status_code=status.HTTP_200_OK)
def change_password(body: ChangePasswordRequest, session: CurrentSession, db: DbSession) -> Message:
    _limit_user(session.user)
    auth_service.change_password(
        db,
        session=session,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    return Message(message="تم تغيير كلمة المرور")
