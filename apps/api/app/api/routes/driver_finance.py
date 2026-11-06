"""Driver account ledger, statements and settlements (Task 18)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, require_permissions
from app.api.finance_presenters import ledger_outs, settlement_outs
from app.core.errors import NotFoundError, ValidationFailed
from app.core.permissions import Permission
from app.core.time import local_today
from app.models.driver import Driver
from app.models.finance import LedgerEntryType, SettlementStatus
from app.models.user import User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.finance import (
    DriverStatement,
    LedgerEntryIn,
    LedgerEntryOut,
    Ref,
    SettlementCreate,
    SettlementOut,
    VoidAction,
)
from app.services import driver_ledger
from app.services import settlements as settlements_service
from app.services.finance_common import money

router = APIRouter(tags=["driver-finance"])

Reader = Annotated[User, Depends(require_permissions(Permission.SETTLEMENTS_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.SETTLEMENTS_WRITE))]
Finalizer = Annotated[User, Depends(require_permissions(Permission.SETTLEMENTS_FINALIZE))]


def _driver(db: DbSession, driver_id: uuid.UUID) -> Driver:
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise NotFoundError("السائق غير موجود")
    return driver


@router.get("/drivers/{driver_id}/statement", response_model=DriverStatement)
def driver_statement(
    driver_id: uuid.UUID,
    _: Reader,
    db: DbSession,
    date_from: date,
    date_to: date | None = None,
) -> DriverStatement:
    driver = _driver(db, driver_id)
    end = date_to or local_today()
    if end < date_from or (end - date_from).days > 400:
        raise ValidationFailed("اختر فترة صحيحة لا تتجاوز سنة", code="invalid_range")
    s = driver_ledger.statement(db, driver.id, date_from, end)

    def t(*types: LedgerEntryType) -> Decimal:
        return money(sum((s.by_type.get(x, Decimal(0)) for x in types), Decimal(0)))

    return DriverStatement(
        driver=Ref(id=driver.id, name=driver.full_name),
        date_from=date_from,
        date_to=end,
        opening_balance=money(s.opening),
        earned=t(LedgerEntryType.EARNING),
        bonuses=t(LedgerEntryType.BONUS),
        reimbursements=t(LedgerEntryType.REIMBURSEMENT),
        cash_collected=t(LedgerEntryType.CASH_COLLECTED),
        cash_handed_over=t(LedgerEntryType.CASH_HANDOVER),
        advances=t(LedgerEntryType.ADVANCE),
        deductions=t(LedgerEntryType.DEDUCTION),
        paid=t(LedgerEntryType.PAYMENT),
        adjustments=t(LedgerEntryType.ADJUSTMENT),
        closing_balance=money(s.closing),
        entries=ledger_outs(db, s.entries),
    )


@router.post(
    "/drivers/{driver_id}/ledger",
    response_model=LedgerEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def add_ledger_entry(
    driver_id: uuid.UUID, body: LedgerEntryIn, actor: Writer, db: DbSession
) -> LedgerEntryOut:
    entry = driver_ledger.create_manual(db, actor=actor, driver_id=driver_id, data=body)
    return ledger_outs(db, [entry])[0]


@router.post("/driver-ledger/{entry_id}/void", response_model=LedgerEntryOut)
def void_ledger_entry(
    entry_id: uuid.UUID, body: VoidAction, actor: Finalizer, db: DbSession
) -> LedgerEntryOut:
    entry = driver_ledger.void_manual(db, actor=actor, entry_id=entry_id, reason=body.reason)
    return ledger_outs(db, [entry])[0]


@router.get("/settlements", response_model=Page[SettlementOut])
def list_settlements(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    driver_id: uuid.UUID | None = None,
    status: SettlementStatus | None = None,
) -> Page[SettlementOut]:
    rows, total = settlements_service.list_settlements(
        db, params, driver_id=driver_id, status=status
    )
    return Page(
        items=settlement_outs(db, rows), total=total, page=params.page, page_size=params.page_size
    )


@router.post("/settlements", response_model=SettlementOut, status_code=status.HTTP_201_CREATED)
def create_settlement(body: SettlementCreate, actor: Writer, db: DbSession) -> SettlementOut:
    return settlement_outs(db, [settlements_service.create_draft(db, actor=actor, data=body)])[0]


@router.get("/settlements/{settlement_id}", response_model=SettlementOut)
def get_settlement(settlement_id: uuid.UUID, _: Reader, db: DbSession) -> SettlementOut:
    return settlement_outs(db, [settlements_service.get(db, settlement_id)])[0]


@router.post("/settlements/{settlement_id}/recalculate", response_model=SettlementOut)
def recalculate_settlement(settlement_id: uuid.UUID, actor: Writer, db: DbSession) -> SettlementOut:
    settlement = settlements_service.recalculate(db, actor=actor, settlement_id=settlement_id)
    return settlement_outs(db, [settlement])[0]


@router.post("/settlements/{settlement_id}/finalize", response_model=SettlementOut)
def finalize_settlement(settlement_id: uuid.UUID, actor: Finalizer, db: DbSession) -> SettlementOut:
    settlement = settlements_service.finalize(db, actor=actor, settlement_id=settlement_id)
    return settlement_outs(db, [settlement])[0]


@router.post("/settlements/{settlement_id}/void", response_model=SettlementOut)
def void_settlement(
    settlement_id: uuid.UUID, body: VoidAction, actor: Finalizer, db: DbSession
) -> SettlementOut:
    settlement = settlements_service.void(
        db, actor=actor, settlement_id=settlement_id, reason=body.reason
    )
    return settlement_outs(db, [settlement])[0]
