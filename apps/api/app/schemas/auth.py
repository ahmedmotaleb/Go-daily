"""Authentication schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.user import CurrentUserOut


class LoginRequest(BaseModel):
    # Not normalised here: invalid formats must fail like wrong credentials.
    phone: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=256)
    client: Literal["web", "mobile"] = "web"
    device_name: str | None = Field(default=None, max_length=120)


class LoginResponse(BaseModel):
    """A session, or, for users with two-factor login, a challenge for the code step."""

    access_token: str | None = None
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_at: datetime | None = None
    user: CurrentUserOut | None = None
    twofa_required: bool = False
    challenge: str | None = None


class LoginCodeRequest(BaseModel):
    challenge: str = Field(min_length=1, max_length=1000)
    # A 6-digit code from the authenticator app, or a recovery code.
    code: str = Field(min_length=6, max_length=20)


class TwoFactorSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class TwoFactorCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class TwoFactorReauthIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=20)


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


class TwoFactorStatusOut(BaseModel):
    enabled: bool
    required: bool
    recovery_codes_left: int


class TwoFactorResetIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
