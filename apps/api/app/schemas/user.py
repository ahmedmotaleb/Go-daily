"""User schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.permissions import UserRole
from app.schemas.common import ORMModel, PhoneMixin, ShortText


def _lower_email(value: object) -> object:
    if isinstance(value, str):
        value = value.strip().lower()
        return value or None
    return value


class UserOut(ORMModel):
    id: uuid.UUID
    full_name: str
    phone: str
    email: str | None
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CurrentUserOut(UserOut):
    permissions: list[str]


class UserCreate(PhoneMixin):
    full_name: ShortText
    phone: str
    email: EmailStr | None = None
    role: UserRole
    password: str = Field(min_length=1, max_length=256)
    is_active: bool = True

    _email = field_validator("email", mode="before")(_lower_email)


class UserUpdate(PhoneMixin):
    full_name: ShortText | None = None
    phone: str | None = None
    email: EmailStr | None = None
    role: UserRole | None = None
    is_active: bool | None = None

    _email = field_validator("email", mode="before")(_lower_email)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=1, max_length=256)
