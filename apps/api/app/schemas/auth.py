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
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_at: datetime
    user: CurrentUserOut


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
