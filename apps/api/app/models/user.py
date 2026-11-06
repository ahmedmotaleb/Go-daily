"""Users and authentication sessions."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.permissions import UserRole
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column_type


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    email: Mapped[str | None] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(enum_column_type(UserRole, "user_role"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    last_login_at: Mapped[datetime | None]
    password_changed_at: Mapped[datetime | None]
    failed_login_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None]

    sessions: Mapped[list[AuthSession]] = relationship(back_populates="user")

    __table_args__ = (
        # Emails are optional but unique (case-insensitive) when present.
        Index(
            "uq_users_email_lower",
            func.lower(text("email")),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
    )


class ClientType(StrEnum):
    WEB = "WEB"
    MOBILE = "MOBILE"


class AuthSession(UUIDPrimaryKeyMixin, Base):
    """Opaque server-side session. Only the SHA-256 of the token is stored."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    client_type: Mapped[ClientType] = mapped_column(enum_column_type(ClientType, "client_type"))
    device_name: Mapped[str | None] = mapped_column(String(120))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    last_used_at: Mapped[datetime] = mapped_column(server_default=func.now())
    revoked_at: Mapped[datetime | None]
    revoke_reason: Mapped[str | None] = mapped_column(String(50))

    user: Mapped[User] = relationship(back_populates="sessions")

    __table_args__ = (Index("ix_auth_sessions_user_active", "user_id", "revoked_at"),)
