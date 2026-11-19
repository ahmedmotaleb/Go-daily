"""Versioned company policies (U47): review thresholds set by authorized staff."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class PolicyVersion(UUIDPrimaryKeyMixin, Base):
    """One immutable version: the full set of overrides in force from created_at.

    The newest version applies; earlier ones stay as history. Values not in
    `values` use the defaults from the environment settings.
    """

    __tablename__ = "policy_versions"

    version: Mapped[int] = mapped_column(Integer, unique=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
