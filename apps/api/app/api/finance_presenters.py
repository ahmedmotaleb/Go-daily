"""Response builders for financial records (batch-loads user names)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import (
    DriverLedgerEntry,
    DriverSettlement,
    Expense,
    FuelTransaction,
    RevenueEntry,
    RevenueReceipt,
    RideHailingStatement,
)
from app.models.user import User
from app.schemas.finance import (
    ExpenseCategoryOut,
    ExpenseOut,
    FuelOut,
    FuelTypeOut,
    LedgerEntryOut,
    ReceiptOut,
    Ref,
    RevenueOut,
    SettlementOut,
    StatementOut,
    UserRef,
)
from app.services import finance_common as fc
from app.services import revenue as revenue_service
from app.services import ride_hailing as ride_hailing_service

type Users = dict[uuid.UUID, User]


def load_users(db: Session, ids: Iterable[uuid.UUID | None]) -> Users:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(wanted))).all()}


def _money(value: Decimal | None) -> Decimal | None:
    return fc.money(value) if value is not None else None


def _user(users: Users, user_id: uuid.UUID | None) -> UserRef | None:
    user = users.get(user_id) if user_id else None
    return UserRef(id=user.id, full_name=user.full_name) if user else None


def _review(record: Any, users: Users, corrected: dict[uuid.UUID, uuid.UUID]) -> dict[str, Any]:
    return {
        "status": record.status,
        "source": record.source,
        "notes": record.notes,
        "created_by": _user(users, record.created_by_id),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "reviewed_by": _user(users, record.reviewed_by_id),
        "reviewed_at": record.reviewed_at,
        "review_note": record.review_note,
        "voided_by": _user(users, record.voided_by_id),
        "voided_at": record.voided_at,
        "void_reason": record.void_reason,
        "corrects_id": record.corrects_id,
        "corrected_by_id": corrected.get(record.id),
    }


def _review_user_ids(records: Sequence[Any]) -> list[uuid.UUID | None]:
    return [uid for r in records for uid in (r.created_by_id, r.reviewed_by_id, r.voided_by_id)]


def fuel_outs(db: Session, records: Sequence[FuelTransaction]) -> list[FuelOut]:
    users = load_users(db, _review_user_ids(records))
    corrected = fc.corrected_by_map(db, FuelTransaction, [r.id for r in records])
    return [
        FuelOut(
            **_review(r, users, corrected),
            id=r.id,
            vehicle=Ref(id=r.vehicle.id, name=r.vehicle.internal_code),
            driver=Ref(id=r.driver.id, name=r.driver.full_name) if r.driver else None,
            shift_id=r.shift_id,
            fuel_type=FuelTypeOut.model_validate(r.fuel_type),
            quantity=r.quantity,
            unit=r.unit,
            unit_price=r.unit_price,
            effective_unit_price=(r.total_amount / r.quantity).quantize(fc.CENT),
            total_amount=fc.money(r.total_amount),
            occurred_at=r.occurred_at,
            odometer_km=r.odometer_km,
            vendor=r.vendor,
            payment_method=r.payment_method,
            paid_by=r.paid_by,
            receipt_attachment_id=r.receipt_attachment_id,
            latitude=r.latitude,
            longitude=r.longitude,
            location_accuracy_m=r.location_accuracy_m,
        )
        for r in records
    ]


def expense_outs(db: Session, records: Sequence[Expense]) -> list[ExpenseOut]:
    users = load_users(db, _review_user_ids(records))
    corrected = fc.corrected_by_map(db, Expense, [r.id for r in records])
    return [
        ExpenseOut(
            **_review(r, users, corrected),
            id=r.id,
            vehicle=Ref(id=r.vehicle.id, name=r.vehicle.internal_code),
            driver=Ref(id=r.driver.id, name=r.driver.full_name) if r.driver else None,
            shift_id=r.shift_id,
            session_id=r.session_id,
            category=ExpenseCategoryOut.model_validate(r.category),
            amount=fc.money(r.amount),
            occurred_at=r.occurred_at,
            vendor=r.vendor,
            payment_method=r.payment_method,
            paid_by=r.paid_by,
            receipt_attachment_id=r.receipt_attachment_id,
        )
        for r in records
    ]


def _receipt_out(r: RevenueReceipt, users: Users) -> ReceiptOut:
    return ReceiptOut(
        id=r.id,
        amount=fc.money(r.amount),
        received_at=r.received_at,
        method=r.method,
        received_by=r.received_by,
        reference=r.reference,
        notes=r.notes,
        created_by=_user(users, r.created_by_id),
        created_at=r.created_at,
        voided_at=r.voided_at,
        void_reason=r.void_reason,
    )


def revenue_outs(db: Session, records: Sequence[RevenueEntry]) -> list[RevenueOut]:
    receipts = [rc for r in records for rc in r.receipts]
    users = load_users(db, [*_review_user_ids(records), *(rc.created_by_id for rc in receipts)])
    corrected = fc.corrected_by_map(db, RevenueEntry, [r.id for r in records])
    out = []
    for r in records:
        cash, electronic = revenue_service.received_split(r)
        m = fc.money
        out.append(
            RevenueOut(
                **_review(r, users, corrected),
                id=r.id,
                kind=r.kind,
                vehicle=Ref(id=r.vehicle.id, name=r.vehicle.internal_code),
                driver=Ref(id=r.driver.id, name=r.driver.full_name) if r.driver else None,
                shift_id=r.shift_id,
                session_id=r.session_id,
                operation_type=(
                    Ref(id=r.operation_type.id, name=r.operation_type.name_ar)
                    if r.operation_type
                    else None
                ),
                occurred_on=r.occurred_on,
                period_start=r.period_start,
                period_end=r.period_end,
                amount=m(r.amount),
                fees_withheld=m(r.fees_withheld),
                net_amount=m(revenue_service.net_amount(r)),
                received_amount=m(cash + electronic),
                received_cash=m(cash),
                received_electronic=m(electronic),
                outstanding_amount=m(revenue_service.outstanding(r)),
                loops_count=r.loops_count,
                customer_name=r.customer_name,
                reference=r.reference,
                statement_id=r.statement_id,
                receipts=[_receipt_out(rc, users) for rc in r.receipts],
            )
        )
    return out


def statement_outs(db: Session, records: Sequence[RideHailingStatement]) -> list[StatementOut]:
    users = load_users(db, _review_user_ids(records))
    corrected = fc.corrected_by_map(db, RideHailingStatement, [r.id for r in records])
    revenue_ids = ride_hailing_service.revenue_ids(db, [r.id for r in records])
    return [
        StatementOut(
            **_review(r, users, corrected),
            id=r.id,
            platform=Ref(id=r.platform.id, name=r.platform.name),
            driver=Ref(id=r.driver.id, name=r.driver.full_name),
            vehicle=Ref(id=r.vehicle.id, name=r.vehicle.internal_code),
            period_start=r.period_start,
            period_end=r.period_end,
            trips_count=r.trips_count,
            gross_earnings=fc.money(r.gross_earnings),
            platform_fees=fc.money(r.platform_fees),
            tips=fc.money(r.tips),
            adjustments=fc.money(r.adjustments),
            income=fc.money(r.income),
            net_earnings=fc.money(r.net_earnings),
            cash_collected=fc.money(r.cash_collected),
            platform_payout=fc.money(r.platform_payout),
            payout_recipient=r.payout_recipient,
            statement_reference=r.statement_reference,
            attachment_id=r.attachment_id,
            revenue_entry_id=revenue_ids.get(r.id),
        )
        for r in records
    ]


def ledger_outs(db: Session, entries: Sequence[DriverLedgerEntry]) -> list[LedgerEntryOut]:
    users = load_users(db, (e.created_by_id for e in entries))
    return [
        LedgerEntryOut(
            id=e.id,
            driver_id=e.driver_id,
            entry_type=e.entry_type,
            amount=fc.money(e.amount),
            occurred_on=e.occurred_on,
            description=e.description,
            reason=e.reason,
            source_type=e.source_type,
            source_id=e.source_id,
            settlement_id=e.settlement_id,
            vehicle_id=e.vehicle_id,
            period_start=e.period_start,
            period_end=e.period_end,
            created_by=_user(users, e.created_by_id),
            created_at=e.created_at,
            voided_at=e.voided_at,
            void_reason=e.void_reason,
        )
        for e in entries
    ]


def settlement_outs(db: Session, records: Sequence[DriverSettlement]) -> list[SettlementOut]:
    users = load_users(db, (s.finalized_by_id for s in records))
    return [
        SettlementOut(
            id=s.id,
            driver=Ref(id=s.driver.id, name=s.driver.full_name),
            period_start=s.period_start,
            period_end=s.period_end,
            status=s.status,
            earnings_amount=fc.money(s.earnings_amount),
            details=s.details,
            opening_balance=_money(s.opening_balance),
            closing_balance=_money(s.closing_balance),
            notes=s.notes,
            created_at=s.created_at,
            finalized_at=s.finalized_at,
            finalized_by=_user(users, s.finalized_by_id),
            voided_at=s.voided_at,
            void_reason=s.void_reason,
        )
        for s in records
    ]
