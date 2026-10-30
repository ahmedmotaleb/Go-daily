"""Reports: catalog, JSON and CSV export (Task 23)."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission
from app.core.time import local_today
from app.models.user import User
from app.schemas.reports import ColumnOut, ReportInfo, ReportOut, SummaryOut
from app.services import reports as report_service

router = APIRouter(prefix="/reports", tags=["reports"])

Reader = Annotated[User, Depends(require_permissions(Permission.REPORTS_READ))]


def report_filters(
    date_from: date | None = None,
    date_to: date | None = None,
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    operation_type_id: uuid.UUID | None = None,
    route_id: uuid.UUID | None = None,
    fuel_type_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
) -> report_service.Filters:
    today = local_today()
    return report_service.Filters(
        date_from=date_from or today.replace(day=1),
        date_to=date_to or today,
        vehicle_id=vehicle_id,
        driver_id=driver_id,
        operation_type_id=operation_type_id,
        route_id=route_id,
        fuel_type_id=fuel_type_id,
        category_id=category_id,
    )


Filters = Annotated[report_service.Filters, Depends(report_filters)]


def _columns(table: report_service.Table) -> list[ColumnOut]:
    return [ColumnOut(**asdict(c)) for c in table.columns]


@router.get("", response_model=list[ReportInfo])
def catalog(user: Reader) -> list[ReportInfo]:
    """Reports this user may open (each also needs its data's permissions)."""
    return [
        ReportInfo(code=r.code, title=r.title, description=r.description, filters=list(r.filters))
        for r in report_service.available(user)
    ]


@router.get("/{code}", response_model=ReportOut)
def report(code: str, user: Reader, db: DbSession, filters: Filters) -> ReportOut:
    definition, result = report_service.run(db, user, code, filters)
    return ReportOut(
        code=definition.code,
        title=definition.title,
        date_from=filters.date_from,
        date_to=filters.date_to,
        columns=_columns(result.table),
        rows=result.table.rows,
        totals=result.table.totals(),
        summaries=[
            SummaryOut(title=title, columns=_columns(t), rows=t.rows, totals=t.totals())
            for title, t in result.summaries
        ],
        notes=result.notes,
    )


@router.get("/{code}/csv")
def report_csv(
    code: str,
    user: Reader,
    db: DbSession,
    filters: Filters,
) -> Response:
    definition, result = report_service.run(db, user, code, filters)
    filename = f"{definition.code}_{filters.date_from}_{filters.date_to}.csv"
    return Response(
        content=report_service.to_csv(definition, result).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
