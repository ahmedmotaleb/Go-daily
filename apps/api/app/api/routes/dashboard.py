"""Admin dashboard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    _: Annotated[User, Depends(require_permissions(Permission.VEHICLES_READ))], db: DbSession
) -> DashboardSummary:
    return dashboard_service.summary(db)
