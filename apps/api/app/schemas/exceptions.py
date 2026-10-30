"""Operational exception schemas (Task 20)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.exceptions import ExceptionLabel, ExceptionSeverity, ExceptionStatus
from app.schemas.finance import Notes, Ref, UserRef


class ExceptionOut(BaseModel):
    id: uuid.UUID
    rule_code: str
    rule_title: str
    severity: ExceptionSeverity
    label: ExceptionLabel
    summary: str
    evidence: dict[str, Any]
    occurred_at: datetime
    occurred_until: datetime | None
    detected_at: datetime
    last_detected_at: datetime
    cleared_at: datetime | None
    vehicle: Ref | None
    driver: Ref | None
    shift_id: uuid.UUID | None
    subject_type: str | None
    subject_id: uuid.UUID | None
    status: ExceptionStatus
    reviewer: UserRef | None
    reviewed_at: datetime | None
    review_notes: str | None
    resolution: str | None
    allowed_transitions: list[ExceptionStatus]
    updated_at: datetime


class ReviewIn(BaseModel):
    status: ExceptionStatus
    notes: Notes | None = None
    resolution: Notes | None = None


class RunIn(BaseModel):
    days: int | None = Field(default=None, ge=1, le=31)


class RunOut(BaseModel):
    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    window_start: datetime
    window_end: datetime
    trigger: str
    results: dict[str, Any]
    errors: dict[str, Any]


class RuleOut(BaseModel):
    code: str
    title_ar: str
    description_ar: str
    label: ExceptionLabel
    enabled: bool


class RulesOut(BaseModel):
    rules: list[RuleOut]
    thresholds: dict[str, Any]
    last_run: RunOut | None


class SummaryOut(BaseModel):
    active: int
    by_status: dict[str, int]
    by_severity: dict[str, int]
    by_rule: dict[str, int]
