"""General expense endpoints (Task 16)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, require_permissions
from app.api.finance_presenters import expense_outs
from app.core.permissions import Permission, has_permission
from app.models.finance import ExpenseCategory, ExpenseGroup, RecordStatus
from app.models.user import User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.finance import (
    ExpenseCategoryCreate,
    ExpenseCategoryOut,
    ExpenseCategoryUpdate,
    ExpenseCorrection,
    ExpenseCreate,
    ExpenseOut,
    ExpenseSummary,
    ExpenseUpdate,
    RejectAction,
    ReviewAction,
    VoidAction,
)
from app.services import expenses as expenses_service

router = APIRouter(tags=["expenses"])

Reader = Annotated[User, Depends(require_permissions(Permission.EXPENSES_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.EXPENSES_WRITE))]
Approver = Annotated[User, Depends(require_permissions(Permission.EXPENSES_APPROVE))]
SettingsAdmin = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]


def _filters(
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    group: ExpenseGroup | None = None,
    status: RecordStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> expenses_service.ExpenseFilters:
    return expenses_service.ExpenseFilters(
        vehicle_id=vehicle_id,
        driver_id=driver_id,
        category_id=category_id,
        group=group,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )


Filters = Annotated[expenses_service.ExpenseFilters, Depends(_filters)]


@router.get("/expense-categories", response_model=list[ExpenseCategoryOut])
def list_categories(
    _: Reader, db: DbSession, include_inactive: bool = False
) -> list[ExpenseCategory]:
    return expenses_service.list_categories(db, include_inactive=include_inactive)


@router.post(
    "/expense-categories", response_model=ExpenseCategoryOut, status_code=status.HTTP_201_CREATED
)
def create_category(
    body: ExpenseCategoryCreate, actor: SettingsAdmin, db: DbSession
) -> ExpenseCategory:
    return expenses_service.create_category(db, actor=actor, data=body)


@router.patch("/expense-categories/{category_id}", response_model=ExpenseCategoryOut)
def update_category(
    category_id: uuid.UUID, body: ExpenseCategoryUpdate, actor: SettingsAdmin, db: DbSession
) -> ExpenseCategory:
    return expenses_service.update_category(db, actor=actor, category_id=category_id, data=body)


@router.get("/expenses", response_model=Page[ExpenseOut])
def list_expenses(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    filters: Filters,
) -> Page[ExpenseOut]:
    rows, total = expenses_service.list_expenses(db, params, filters)
    return Page(
        items=expense_outs(db, rows), total=total, page=params.page, page_size=params.page_size
    )


@router.get("/expenses/summary", response_model=ExpenseSummary)
def expense_summary(_: Reader, db: DbSession, filters: Filters) -> dict[str, object]:
    return expenses_service.summary(db, filters)


@router.post("/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
def create_expense(body: ExpenseCreate, actor: Writer, db: DbSession) -> ExpenseOut:
    expense = expenses_service.create(
        db,
        actor=actor,
        data=body,
        can_approve=has_permission(actor.role, Permission.EXPENSES_APPROVE),
    )
    return expense_outs(db, [expense])[0]


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: uuid.UUID, _: Reader, db: DbSession) -> ExpenseOut:
    return expense_outs(db, [expenses_service.get(db, expense_id)])[0]


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: uuid.UUID, body: ExpenseUpdate, actor: Writer, db: DbSession
) -> ExpenseOut:
    expense = expenses_service.update(db, actor=actor, expense_id=expense_id, data=body)
    return expense_outs(db, [expense])[0]


@router.post("/expenses/{expense_id}/approve", response_model=ExpenseOut)
def approve_expense(
    expense_id: uuid.UUID, body: ReviewAction, actor: Approver, db: DbSession
) -> ExpenseOut:
    expense = expenses_service.approve(db, actor=actor, expense_id=expense_id, note=body.note)
    return expense_outs(db, [expense])[0]


@router.post("/expenses/{expense_id}/reject", response_model=ExpenseOut)
def reject_expense(
    expense_id: uuid.UUID, body: RejectAction, actor: Approver, db: DbSession
) -> ExpenseOut:
    expense = expenses_service.reject(db, actor=actor, expense_id=expense_id, reason=body.reason)
    return expense_outs(db, [expense])[0]


@router.post("/expenses/{expense_id}/void", response_model=ExpenseOut)
def void_expense(
    expense_id: uuid.UUID, body: VoidAction, actor: Approver, db: DbSession
) -> ExpenseOut:
    expense = expenses_service.void(db, actor=actor, expense_id=expense_id, reason=body.reason)
    return expense_outs(db, [expense])[0]


@router.post(
    "/expenses/{expense_id}/correct",
    response_model=ExpenseOut,
    status_code=status.HTTP_201_CREATED,
)
def correct_expense(
    expense_id: uuid.UUID, body: ExpenseCorrection, actor: Approver, db: DbSession
) -> ExpenseOut:
    expense = expenses_service.correct(
        db, actor=actor, expense_id=expense_id, data=body, can_approve=True
    )
    return expense_outs(db, [expense])[0]
