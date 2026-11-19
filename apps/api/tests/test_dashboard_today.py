"""Dashboard today overview (design: لوحة التشغيل)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_day_bounds_utc, local_today
from app.models.finance import (
    Expense,
    PaidBy,
    PaymentMethod,
    RecordStatus,
    RevenueEntry,
    RevenueKind,
)
from app.models.route_events import EventSource, EventStatus, RouteEvent, RouteEventType
from tests.factories import expense_category_id, login_as, make_completed_shift, operation_type_id
from tests.test_exceptions import fuel, pair
from tests.test_expected_revenue import _rate, _route

TODAY = local_today()
URL = "/api/v1/dashboard/today"


def _revenue(db: Session, vehicle_id: uuid.UUID, amount: str, status: RecordStatus) -> None:
    db.add(
        RevenueEntry(
            kind=RevenueKind.FIXED_ROUTE_COLLECTION,
            vehicle_id=vehicle_id,
            operation_type_id=uuid.UUID(operation_type_id(db, "FIXED_ROUTE")),
            occurred_on=TODAY,
            amount=Decimal(amount),
            status=status,
        )
    )
    db.commit()


def test_money_is_split_and_only_for_finance_roles(client: TestClient, db: Session) -> None:
    _, vehicle = pair(db)
    _revenue(db, vehicle.id, "900.00", RecordStatus.APPROVED)
    _revenue(db, vehicle.id, "100.00", RecordStatus.SUBMITTED)
    noon = local_day_bounds_utc(TODAY)[0] + timedelta(hours=12)
    fuel(db, vehicle, at=noon, amount="300")
    db.add(
        Expense(
            vehicle_id=vehicle.id,
            category_id=uuid.UUID(expense_category_id(db, "TOLL")),
            amount=Decimal("40.00"),
            occurred_at=noon,
            payment_method=PaymentMethod.CASH,
            paid_by=PaidBy.COMPANY,
            status=RecordStatus.SUBMITTED,
        )
    )
    db.commit()

    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    body = client.get(URL, headers=acc).json()
    assert Decimal(body["revenue"]["approved"]) >= Decimal("900.00")
    assert Decimal(body["revenue"]["pending"]) >= Decimal("100.00")
    assert Decimal(body["fuel"]["total"]) >= Decimal("300.00")
    assert Decimal(body["other_expenses"]["pending"]) >= Decimal("40.00")
    assert len(body["week"]) == 7 and body["week"][-1]["day"] == TODAY.isoformat()
    assert Decimal(body["week"][-1]["revenue"]) >= Decimal("1000.00")

    _, ops = login_as(client, db, UserRole.OPERATIONS)
    restricted = client.get(URL, headers=ops).json()
    assert restricted["revenue"] is None and restricted["week"] == []
    assert all(op["collection"] is None for op in restricted["operations"])


def test_operations_show_real_activity(client: TestClient, db: Session) -> None:
    route = _route(db)
    _rate(db, route, amount_per_loop=Decimal("100.00"), effective_from=TODAY - timedelta(days=30))
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=TODAY, minutes=240)
    session = shift.sessions[0]
    session.route = route
    db.flush()
    assert shift.started_at
    for i in range(3):
        db.add(
            RouteEvent(
                shift_id=shift.id,
                session_id=session.id,
                route_id=route.id,
                vehicle_id=vehicle.id,
                event_type=RouteEventType.LOOP_COMPLETED,
                occurred_at=shift.started_at + timedelta(minutes=30 * (i + 1)),
                source=EventSource.AUTO,
                status=EventStatus.ACTIVE,
                dedupe_key=f"t:{uuid.uuid4()}",
            )
        )
    db.commit()
    _revenue(db, vehicle.id, "250.00", RecordStatus.APPROVED)

    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    ops = {o["kind"]: o for o in client.get(URL, headers=acc).json()["operations"]}
    fixed = ops["FIXED_ROUTE"]
    assert fixed["activity_label"] == "لفات مكتملة"
    assert int(fixed["activity_value"]) >= 3
    assert fixed["vehicles"] >= 1
    assert Decimal(fixed["collection"]) >= Decimal("250.00")
    assert fixed["progress_pct"] is not None  # against the expected collection (U10)
