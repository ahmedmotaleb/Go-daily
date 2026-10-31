"""Assignment schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, StringConstraints

from app.models.assignment import AssignmentRole
from app.schemas.common import ORMModel

Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class AssignmentCreate(BaseModel):
    driver_id: uuid.UUID
    vehicle_id: uuid.UUID
    role: AssignmentRole = AssignmentRole.PRIMARY
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    notes: Notes | None = None
    # End the vehicle's/driver's current PRIMARY assignment at `starts_at`.
    replace_current: bool = False


class AssignmentEnd(BaseModel):
    ends_at: AwareDatetime | None = None
    notes: Notes | None = None


class AssignmentCorrection(BaseModel):
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    notes: Notes | None = None
    reason: Reason | None = None


class AssignmentOut(ORMModel):
    id: uuid.UUID
    driver_id: uuid.UUID
    driver_name: str
    vehicle_id: uuid.UUID
    vehicle_code: str
    vehicle_plate: str
    role: AssignmentRole
    starts_at: datetime
    ends_at: datetime | None
    is_active: bool
    notes: str | None
    created_at: datetime
