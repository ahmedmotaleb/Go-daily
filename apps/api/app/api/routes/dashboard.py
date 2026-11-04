"""Admin dashboard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission, has_permission
from app.core.time import utcnow
from app.models.user import User
from app.schemas.dashboard import (
    DashboardSummary,
    DayFiguresOut,
    MoneySplit,
    OperationTodayOut,
    TodayOverviewOut,
)
from app.services import dashboard as dashboard_service
from app.services import dashboard_today

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    _: Annotated[User, Depends(require_permissions(Permission.VEHICLES_READ))], db: DbSession
) -> DashboardSummary:
    return dashboard_service.summary(db)


def _split(m: dashboard_today.Money | None) -> MoneySplit | None:
    if m is None:
        return None
    return MoneySplit(approved=m.approved, pending=m.pending, total=m.total)


@router.get("/today", response_model=TodayOverviewOut)
def dashboard_today_overview(
    user: Annotated[User, Depends(require_permissions(Permission.VEHICLES_READ))], db: DbSession
) -> TodayOverviewOut:
    """Today's activity for everyone with dashboard access; money only for finance roles."""
    with_money = has_permission(user.role, Permission.REVENUE_READ)
    with_expenses = has_permission(user.role, Permission.FUEL_READ) and has_permission(
        user.role, Permission.EXPENSES_READ
    )
    o = dashboard_today.overview(db, with_money=with_money, with_expenses=with_expenses)
    return TodayOverviewOut(
        generated_at=utcnow(),
        oldest_shift_started_at=o.oldest_shift_started_at,
        revenue=_split(o.revenue),
        fuel=_split(o.fuel),
        other_expenses=_split(o.other_expenses),
        week=[DayFiguresOut(day=d.day, revenue=d.revenue, expenses=d.expenses) for d in o.week],
        operations=[
            OperationTodayOut(
                kind=op.kind.value,
                name_ar=op.name_ar,
                vehicles=op.vehicles,
                active_sessions=op.active_sessions,
                sessions_today=op.sessions_today,
                activity_label=op.activity_label,
                activity_value=op.activity_value,
                progress_pct=op.progress_pct,
                note=op.note,
                note_is_warning=op.note_is_warning,
                collection=op.collection,
            )
            for op in o.operations
        ],
    )
