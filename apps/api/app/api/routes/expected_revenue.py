"""Expected revenue rates per fixed route (U10)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission
from app.models.finance import RouteRevenueRate
from app.models.user import User
from app.schemas.expected_revenue import RateCreate, RateOut
from app.services import expected_revenue as service

router = APIRouter(tags=["expected-revenue"])

Reader = Annotated[User, Depends(require_permissions(Permission.REVENUE_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.REVENUE_WRITE))]


@router.get("/routes/{route_id}/revenue-rates", response_model=list[RateOut])
def list_rates(route_id: uuid.UUID, _: Reader, db: DbSession) -> list[RouteRevenueRate]:
    return service.list_rates(db, route_id)


@router.post(
    "/routes/{route_id}/revenue-rates",
    response_model=RateOut,
    status_code=status.HTTP_201_CREATED,
)
def add_rate(
    route_id: uuid.UUID, body: RateCreate, actor: Writer, db: DbSession
) -> RouteRevenueRate:
    return service.add_rate(db, actor=actor, route_id=route_id, data=body)
