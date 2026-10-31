"""Vehicle profit & loss (Task 19)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_permissions
from app.core.errors import ValidationFailed
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.finance import FleetPnl, VehiclePnl
from app.services import profitability

router = APIRouter(prefix="/profitability", tags=["profitability"])

Reader = Annotated[User, Depends(require_permissions(Permission.PROFITABILITY_READ))]


@router.get("/vehicles", response_model=FleetPnl)
def fleet_pnl(
    _: Reader,
    db: DbSession,
    date_from: date,
    date_to: date,
    vehicle_id: uuid.UUID | None = None,
) -> FleetPnl:
    if date_to < date_from or (date_to - date_from).days > 366:
        raise ValidationFailed("اختر فترة صحيحة لا تتجاوز سنة", code="invalid_range")
    rows, totals = profitability.compute(db, date_from, date_to, vehicle_id)
    return FleetPnl(
        date_from=date_from,
        date_to=date_to,
        vehicles=[VehiclePnl.model_validate(r) for r in rows],
        totals=totals,
    )
