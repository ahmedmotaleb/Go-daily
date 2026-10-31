"""Data integrity and concurrency (Task 26).

Concurrent writes are serialised by row locks in the services and, as the
last line of defence, by database constraints. These tests check that the
locks are requested and that the constraints reject what the services
would never write.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from app.models.finance import (
    DriverLedgerEntry,
    FuelTransaction,
    LedgerEntryType,
    LedgerSource,
    PaidBy,
    PaymentMethod,
    QuantityUnit,
    RecordStatus,
    RevenueEntry,
    RevenueKind,
)
from app.models.route_events import EventSource, RouteEvent, RouteEventType
from app.models.shift import Shift, ShiftStatus
from app.services import audit
from tests.factories import (
    fuel_type_id,
    login_as,
    make_completed_shift,
    make_driver,
    make_platform,
    make_route,
    make_vehicle,
)


@contextmanager
def captured_sql(db: Session) -> Iterator[list[str]]:
    statements: list[str] = []
    conn = db.connection()

    def _capture(_c: Any, _cur: Any, statement: str, *_: Any) -> None:
        statements.append(statement)

    event.listen(conn, "before_cursor_execute", _capture)
    try:
        yield statements
    finally:
        event.remove(conn, "before_cursor_execute", _capture)


def _fuel(db: Session, **kw: Any) -> FuelTransaction:
    tx = FuelTransaction(
        vehicle_id=make_vehicle(db).id,
        fuel_type_id=uuid.UUID(fuel_type_id(db, "CNG")),
        quantity=Decimal("20"),
        unit=QuantityUnit.CUBIC_METER,
        total_amount=Decimal("140"),
        occurred_at=utcnow() - timedelta(hours=1),
        payment_method=PaymentMethod.CASH,
        paid_by=PaidBy.COMPANY,
        **kw,
    )
    db.add(tx)
    db.commit()
    return tx


def test_review_actions_lock_the_record(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    tx = _fuel(db)
    with captured_sql(db) as sql:
        res = client.post(f"/api/v1/fuel/{tx.id}/approve", json={}, headers=h)
    assert res.status_code == 200, res.text
    assert any("FOR UPDATE OF fuel_transactions" in s for s in sql)

    # The second reviewer waits for the lock, then sees the first decision.
    again = client.post(f"/api/v1/fuel/{tx.id}/approve", json={}, headers=h)
    assert again.status_code == 409


def test_reads_do_not_lock(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    tx = _fuel(db)
    with captured_sql(db) as sql:
        assert client.get(f"/api/v1/fuel/{tx.id}", headers=h).status_code == 200
    assert not any("FOR UPDATE" in s for s in sql)


def _nested_fails(db: Session, sql_or_obj: Any, params: dict[str, Any] | None = None) -> bool:
    try:
        with db.begin_nested():
            if isinstance(sql_or_obj, str):
                db.execute(text(sql_or_obj), params or {})
            else:
                db.add(sql_or_obj)
                db.flush()
    except (IntegrityError, DBAPIError):
        return True
    return False


def test_one_live_ledger_entry_per_source(db: Session) -> None:
    driver = make_driver(db)
    source = uuid.uuid4()

    def entry() -> DriverLedgerEntry:
        return DriverLedgerEntry(
            driver_id=driver.id,
            entry_type=LedgerEntryType.REIMBURSEMENT,
            amount=Decimal("50"),
            occurred_on=local_today(),
            description="تعويض",
            source_type=LedgerSource.FUEL,
            source_id=source,
        )

    first = entry()
    db.add(first)
    db.commit()
    assert _nested_fails(db, entry())  # a second live posting for the same source
    first.voided_at = utcnow()
    db.commit()
    assert not _nested_fails(db, entry())  # allowed once the first is voided


def test_one_live_revenue_entry_per_statement(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver, platform = make_vehicle(db), make_driver(db), make_platform(db)
    day = local_today() - timedelta(days=1)
    res = client.post(
        "/api/v1/ride-hailing/statements",
        json={
            "platform_id": str(platform.id),
            "driver_id": str(driver.id),
            "vehicle_id": str(vehicle.id),
            "period_start": day.isoformat(),
            "period_end": day.isoformat(),
            "gross_earnings": "500",
            "platform_fees": "100",
            "payout_recipient": "DRIVER",
            "approve_now": True,
        },
        headers=h,
    )
    assert res.status_code == 201, res.text
    duplicate = RevenueEntry(
        kind=RevenueKind.RIDE_HAILING,
        vehicle_id=vehicle.id,
        occurred_on=day,
        amount=Decimal("400"),
        statement_id=uuid.UUID(res.json()["id"]),
        status=RecordStatus.APPROVED,
    )
    assert _nested_fails(db, duplicate)


def test_shift_odometer_and_lifecycle_constraints(db: Session) -> None:
    driver, vehicle = make_driver(db), make_vehicle(db)
    shift = make_completed_shift(db, driver, vehicle, day=local_today() - timedelta(days=1))
    params = {"id": shift.id}
    assert _nested_fails(
        db, "UPDATE shifts SET end_odometer_km = start_odometer_km - 1 WHERE id = :id", params
    )
    # A completed shift must keep its end time and reading.
    assert _nested_fails(db, "UPDATE shifts SET end_odometer_km = NULL WHERE id = :id", params)
    # An active shift needs a start reading.
    assert _nested_fails(
        db,
        Shift(
            driver_id=make_driver(db).id,
            vehicle_id=make_vehicle(db).id,
            status=ShiftStatus.ACTIVE,
            started_at=utcnow(),
        ),
    )


def test_loop_events_are_not_duplicated(db: Session) -> None:
    driver, vehicle = make_driver(db), make_vehicle(db)
    shift = make_completed_shift(db, driver, vehicle, day=local_today() - timedelta(days=1))
    session = shift.sessions[0]
    route = make_route(db)

    def loop() -> RouteEvent:
        return RouteEvent(
            session_id=session.id,
            shift_id=shift.id,
            route_id=route.id,
            vehicle_id=vehicle.id,
            event_type=RouteEventType.LOOP_COMPLETED,
            occurred_at=utcnow() - timedelta(hours=2),
            source=EventSource.AUTO,
            dedupe_key=f"{session.id}:LOOP:1",
        )

    db.add(loop())
    db.flush()
    assert _nested_fails(db, loop())


def test_audit_rows_cannot_be_rewritten(db: Session) -> None:
    audit.record(db, action="test.integrity", actor=None)
    db.flush()
    assert _nested_fails(db, "UPDATE audit_logs SET action = 'x'")
    assert _nested_fails(db, "DELETE FROM audit_logs")


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v1/fuel/{id}/approve", {}),
        ("/api/v1/fuel/{id}/reject", {"reason": "إيصال غير واضح"}),
        ("/api/v1/fuel/{id}/void", {"reason": "إدخال مكرر"}),
    ],
)
def test_finished_reviews_cannot_be_repeated(
    client: TestClient, db: Session, path: str, body: dict[str, str]
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    tx = _fuel(db, status=RecordStatus.VOIDED)
    res = client.post(path.format(id=tx.id), json=body, headers=h)
    assert res.status_code == 409
