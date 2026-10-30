"""Revenue ledger and receipts endpoints (Task 17)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, require_permissions
from app.api.finance_presenters import revenue_outs
from app.core.permissions import Permission, has_permission
from app.models.finance import RecordStatus, RevenueKind
from app.models.user import User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.finance import (
    ReceiptIn,
    RejectAction,
    RevenueCorrection,
    RevenueCreate,
    RevenueOut,
    RevenueSummary,
    RevenueUpdate,
    ReviewAction,
    VoidAction,
)
from app.services import revenue as revenue_service

router = APIRouter(tags=["revenue"])

Reader = Annotated[User, Depends(require_permissions(Permission.REVENUE_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.REVENUE_WRITE))]
Approver = Annotated[User, Depends(require_permissions(Permission.REVENUE_APPROVE))]


def _filters(
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    kind: RevenueKind | None = None,
    operation_type_id: uuid.UUID | None = None,
    status: RecordStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> revenue_service.RevenueFilters:
    return revenue_service.RevenueFilters(
        vehicle_id=vehicle_id,
        driver_id=driver_id,
        kind=kind,
        operation_type_id=operation_type_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )


Filters = Annotated[revenue_service.RevenueFilters, Depends(_filters)]


@router.get("/revenue", response_model=Page[RevenueOut])
def list_revenue(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    filters: Filters,
    outstanding_only: bool = False,
) -> Page[RevenueOut]:
    rows, total = revenue_service.list_entries(
        db, params, filters, outstanding_only=outstanding_only
    )
    return Page(
        items=revenue_outs(db, rows), total=total, page=params.page, page_size=params.page_size
    )


@router.get("/revenue/summary", response_model=RevenueSummary)
def revenue_summary(_: Reader, db: DbSession, filters: Filters) -> dict[str, object]:
    return revenue_service.summary(db, filters)


@router.post("/revenue", response_model=RevenueOut, status_code=status.HTTP_201_CREATED)
def create_revenue(body: RevenueCreate, actor: Writer, db: DbSession) -> RevenueOut:
    entry = revenue_service.create(
        db,
        actor=actor,
        data=body,
        can_approve=has_permission(actor.role, Permission.REVENUE_APPROVE),
    )
    return revenue_outs(db, [entry])[0]


@router.get("/revenue/{entry_id}", response_model=RevenueOut)
def get_revenue(entry_id: uuid.UUID, _: Reader, db: DbSession) -> RevenueOut:
    return revenue_outs(db, [revenue_service.get(db, entry_id)])[0]


@router.patch("/revenue/{entry_id}", response_model=RevenueOut)
def update_revenue(
    entry_id: uuid.UUID, body: RevenueUpdate, actor: Writer, db: DbSession
) -> RevenueOut:
    entry = revenue_service.update(db, actor=actor, entry_id=entry_id, data=body)
    return revenue_outs(db, [entry])[0]


@router.post(
    "/revenue/{entry_id}/receipts", response_model=RevenueOut, status_code=status.HTTP_201_CREATED
)
def add_receipt(entry_id: uuid.UUID, body: ReceiptIn, actor: Writer, db: DbSession) -> RevenueOut:
    entry = revenue_service.add_receipt(db, actor=actor, entry_id=entry_id, data=body)
    return revenue_outs(db, [entry])[0]


@router.post("/revenue/receipts/{receipt_id}/void", response_model=RevenueOut)
def void_receipt(
    receipt_id: uuid.UUID, body: VoidAction, actor: Approver, db: DbSession
) -> RevenueOut:
    entry = revenue_service.void_receipt(db, actor=actor, receipt_id=receipt_id, reason=body.reason)
    return revenue_outs(db, [entry])[0]


@router.post("/revenue/{entry_id}/approve", response_model=RevenueOut)
def approve_revenue(
    entry_id: uuid.UUID, body: ReviewAction, actor: Approver, db: DbSession
) -> RevenueOut:
    entry = revenue_service.approve(db, actor=actor, entry_id=entry_id, note=body.note)
    return revenue_outs(db, [entry])[0]


@router.post("/revenue/{entry_id}/reject", response_model=RevenueOut)
def reject_revenue(
    entry_id: uuid.UUID, body: RejectAction, actor: Approver, db: DbSession
) -> RevenueOut:
    entry = revenue_service.reject(db, actor=actor, entry_id=entry_id, reason=body.reason)
    return revenue_outs(db, [entry])[0]


@router.post("/revenue/{entry_id}/void", response_model=RevenueOut)
def void_revenue(
    entry_id: uuid.UUID, body: VoidAction, actor: Approver, db: DbSession
) -> RevenueOut:
    entry = revenue_service.void(db, actor=actor, entry_id=entry_id, reason=body.reason)
    return revenue_outs(db, [entry])[0]


@router.post(
    "/revenue/{entry_id}/correct", response_model=RevenueOut, status_code=status.HTTP_201_CREATED
)
def correct_revenue(
    entry_id: uuid.UUID, body: RevenueCorrection, actor: Approver, db: DbSession
) -> RevenueOut:
    entry = revenue_service.correct(db, actor=actor, entry_id=entry_id, data=body, can_approve=True)
    return revenue_outs(db, [entry])[0]
