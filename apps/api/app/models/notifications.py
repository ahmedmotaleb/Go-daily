"""In-app notifications, one row per recipient (Task 22).

Rows are generated from the current state of the system (expiring
documents, maintenance due, tracking interruptions, open exceptions,
pending reviews). The same condition never notifies the same user twice:
(user, dedupe_key) is unique. When the condition stops being true the row
is marked cleared instead of deleted.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base, UUIDPrimaryKeyMixin, enum_column_type


class NotificationSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Notification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[NotificationSeverity] = mapped_column(
        enum_column_type(NotificationSeverity, "notification_severity")
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    # Relative admin-web path, e.g. /vehicles/<id>.
    link: Mapped[str | None] = mapped_column(String(300))
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None]
    dedupe_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    read_at: Mapped[datetime | None]
    # The condition is no longer true (renewed, serviced, tracking back...).
    cleared_at: Mapped[datetime | None]

    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_kind_open", "kind", "cleared_at"),
    )
