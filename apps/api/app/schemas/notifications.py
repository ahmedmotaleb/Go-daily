"""Notification schemas (Task 22)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.notifications import NotificationSeverity
from app.schemas.common import ORMModel


class NotificationOut(ORMModel):
    id: uuid.UUID
    kind: str
    severity: NotificationSeverity
    title: str
    body: str | None
    link: str | None
    created_at: datetime
    read_at: datetime | None
    cleared_at: datetime | None


class UnreadCountOut(BaseModel):
    unread: int
    critical: int


class GenerateOut(BaseModel):
    results: dict[str, Any]
    errors: dict[str, str]


class MarkedOut(BaseModel):
    marked: int
