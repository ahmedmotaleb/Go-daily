"""Dashboard schemas (all values come from the database; nothing synthetic)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.schemas.fleet import AssignmentSummary
from app.schemas.shift import ShiftOut
from app.services.expiry import ExpiryStatus


class Kpis(BaseModel):
    active_vehicles: int
    active_drivers: int
    active_shifts: int
    today_shifts: int


class VehicleStatusRow(BaseModel):
    id: uuid.UUID
    internal_code: str
    plate_number: str
    vehicle_type: str
    driver_name: str | None
    in_shift: bool
    current_operation: str | None


class ExpiringDocument(BaseModel):
    kind: Literal["VEHICLE_LICENSE", "VEHICLE_INSURANCE", "DRIVER_LICENSE"]
    entity_type: Literal["vehicle", "driver"]
    entity_id: uuid.UUID
    label: str
    expires_on: date
    status: ExpiryStatus


class ActivityItem(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    action: str
    entity_type: str | None
    entity_id: str | None
    actor_name: str | None


class DashboardSummary(BaseModel):
    generated_at: datetime
    kpis: Kpis
    active_shifts: list[ShiftOut]
    vehicles: list[VehicleStatusRow]
    assignments: list[AssignmentSummary]
    expiring_documents: list[ExpiringDocument]
    recent_activity: list[ActivityItem]


class MoneySplit(BaseModel):
    approved: Decimal
    pending: Decimal
    total: Decimal


class DayFiguresOut(BaseModel):
    day: date
    revenue: Decimal
    expenses: Decimal


class OperationTodayOut(BaseModel):
    kind: str
    name_ar: str
    vehicles: int
    active_sessions: int
    sessions_today: int
    activity_label: str
    activity_value: str
    progress_pct: int | None
    note: str | None
    note_is_warning: bool
    collection: Decimal | None


class TodayOverviewOut(BaseModel):
    """Money fields are null for users without the matching finance permission."""

    generated_at: datetime
    oldest_shift_started_at: datetime | None
    revenue: MoneySplit | None
    fuel: MoneySplit | None
    other_expenses: MoneySplit | None
    week: list[DayFiguresOut]
    operations: list[OperationTodayOut]
