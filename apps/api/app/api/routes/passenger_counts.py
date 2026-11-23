"""Passenger count endpoints (U11)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import AwareDatetime, BaseModel, Field

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission
from app.models.passengers import CountConfidence, CountSource, PassengerCount
from app.models.route_events import LegDirection
from app.models.user import User
from app.schemas.finance import Reason
from app.services import passenger_counts as service

router = APIRouter(tags=["passenger-counts"])

Reader = Annotated[User, Depends(require_permissions(Permission.SHIFTS_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.SHIFTS_WRITE))]


class CountIn(BaseModel):
    passengers: int = Field(ge=0, le=200)
    source: CountSource
    confidence: CountConfidence
    counted_at: AwareDatetime | None = None
    session_id: uuid.UUID | None = None
    direction: LegDirection | None = None
    note: str | None = Field(default=None, max_length=300)


class VoidIn(BaseModel):
    reason: Reason


class CountOut(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    session_id: uuid.UUID | None
    route_id: uuid.UUID | None
    direction: LegDirection | None
    counted_at: datetime
    passengers: int
    source: CountSource
    confidence: CountConfidence
    note: str | None
    voided_at: datetime | None
    void_reason: str | None


def _out(c: PassengerCount) -> CountOut:
    return CountOut.model_validate(c, from_attributes=True)


@router.get("/shifts/{shift_id}/passenger-counts", response_model=list[CountOut])
def list_counts(shift_id: uuid.UUID, _: Reader, db: DbSession) -> list[CountOut]:
    return [_out(c) for c in service.for_shift(db, shift_id)]


@router.post(
    "/shifts/{shift_id}/passenger-counts",
    response_model=CountOut,
    status_code=status.HTTP_201_CREATED,
)
def record_count(shift_id: uuid.UUID, body: CountIn, actor: Writer, db: DbSession) -> CountOut:
    return _out(
        service.record(
            db,
            actor=actor,
            shift_id=shift_id,
            passengers=body.passengers,
            source=body.source,
            confidence=body.confidence,
            counted_at=body.counted_at,
            session_id=body.session_id,
            direction=body.direction,
            note=body.note,
        )
    )


@router.post("/passenger-counts/{count_id}/void", response_model=CountOut)
def void_count(count_id: uuid.UUID, body: VoidIn, actor: Writer, db: DbSession) -> CountOut:
    return _out(service.void(db, actor=actor, count_id=count_id, reason=body.reason))
