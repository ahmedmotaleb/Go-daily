"""Expected revenue per loop/leg vs recorded collection (U10)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today
from app.models.audit import AuditLog
from app.models.exceptions import ExceptionLabel
from app.models.finance import (
    ExpectedRevenueModel,
    RecordStatus,
    RevenueEntry,
    RevenueKind,
    RouteRevenueRate,
)
from app.models.operations import RouteDefinition
from app.models.route_events import EventSource, EventStatus, RouteEvent, RouteEventType
from app.models.shift import Shift
from app.services import exception_rules as rules
from app.services import expected_revenue as service
from app.services.expected_revenue import CollectionStatus
from tests.factories import login_as, make_completed_shift, operation_type_id
from tests.test_exceptions import ctx_around, pair
from tests.test_reports import _report

YESTERDAY = local_today() - timedelta(days=1)
CS = CollectionStatus


def _route(db: Session, pattern: str = "ROUND_TRIP", code: str = "FIXED_ROUTE") -> RouteDefinition:
    route = RouteDefinition(
        name=f"موقف ⇄ جامعة {uuid.uuid4().hex[:4]}",
        operation_type_id=uuid.UUID(operation_type_id(db, code)),
        trip_pattern=pattern,
    )
    db.add(route)
    db.commit()
    return route


def _rate(db: Session, route: RouteDefinition, **kw: object) -> RouteRevenueRate:
    rate = RouteRevenueRate(
        route_id=route.id,
        model=kw.pop("model", ExpectedRevenueModel.PER_LOOP),
        effective_from=kw.pop("effective_from", YESTERDAY - timedelta(days=30)),
        **kw,
    )
    db.add(rate)
    db.commit()
    return rate


def _run(db: Session, route: RouteDefinition, *, loops: int, legs: int | None = None) -> Shift:
    """A finished shift on the route with the given detected loops and legs."""
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=240)
    session = shift.sessions[0]
    session.route = route
    db.flush()
    assert shift.started_at
    events = [(RouteEventType.LOOP_COMPLETED, i) for i in range(loops)]
    events += [
        (RouteEventType.LEG_COMPLETED, i) for i in range(legs if legs is not None else 2 * loops)
    ]
    for kind, i in events:
        db.add(
            RouteEvent(
                shift_id=shift.id,
                session_id=session.id,
                route_id=route.id,
                vehicle_id=shift.vehicle_id,
                event_type=kind,
                occurred_at=shift.started_at + timedelta(minutes=10 + i),
                source=EventSource.AUTO,
                status=EventStatus.ACTIVE,
                dedupe_key=f"t:{uuid.uuid4()}",
            )
        )
    db.commit()
    return shift


def _collect(
    db: Session, shift: Shift, amount: str, status: RecordStatus = RecordStatus.APPROVED
) -> None:
    db.add(
        RevenueEntry(
            kind=RevenueKind.FIXED_ROUTE_COLLECTION,
            vehicle_id=shift.vehicle_id,
            driver_id=shift.driver_id,
            occurred_on=YESTERDAY,
            amount=Decimal(amount),
            status=status,
        )
    )
    db.commit()


def _row(db: Session, shift: Shift) -> service.DayCollection:
    [row] = [
        r for r in service.compare(db, YESTERDAY, YESTERDAY) if r.vehicle_id == shift.vehicle_id
    ]
    return row


def test_expected_from_loops_matches_collection(db: Session) -> None:
    route = _route(db)
    _rate(db, route, amount_per_loop=Decimal("120.00"))
    shift = _run(db, route, loops=5)
    _collect(db, shift, "560.00", RecordStatus.APPROVED)
    _collect(db, shift, "40.00", RecordStatus.SUBMITTED)
    row = _row(db, shift)
    assert row.expected == Decimal("600.00")
    assert (row.approved, row.pending) == (Decimal("560.00"), Decimal("40.00"))
    assert row.difference == Decimal("0.00") and row.status is CS.WITHIN_TOLERANCE


def test_a_shortfall_beyond_tolerance_needs_review_with_neutral_wording(db: Session) -> None:
    route = _route(db)
    _rate(db, route, amount_per_loop=Decimal("120.00"))
    shift = _run(db, route, loops=5)
    _collect(db, shift, "400.00")
    row = _row(db, shift)
    assert row.status is CS.SHORTFALL
    assert row.difference == Decimal("-200.00")
    assert row.difference_pct == Decimal("-33.3")
    assert row.allowed == Decimal("60.00")  # 10% of 600 beats the 50 EGP floor

    [case] = [
        c
        for c in rules.collection_gap(ctx_around(db, shift)).candidates
        if c.vehicle_id == shift.vehicle_id
    ]
    assert case.summary.startswith("فرق تحصيل — مراجعة مطلوبة")
    assert case.evidence["expected"] == Decimal("600.00")
    assert rules.RULE_INFO["COLLECTION_GAP"].label is ExceptionLabel.REVIEW_REQUIRED
    for word in ("سرقة", "اختلاس", "احتيال"):
        assert word not in case.summary


def test_per_leg_and_passenger_fare_models(db: Session) -> None:
    per_leg = _route(db, pattern="ONE_WAY")
    _rate(db, per_leg, model=ExpectedRevenueModel.PER_LEG, amount_per_leg=Decimal("55.50"))
    a = _run(db, per_leg, loops=0, legs=4)
    assert _row(db, a).expected == Decimal("222.00")

    fare = _route(db)
    _rate(
        db,
        fare,
        model=ExpectedRevenueModel.PASSENGERS_X_FARE,
        fare=Decimal("7.50"),
        passengers_per_leg=12,
    )
    b = _run(db, fare, loops=2)  # 4 legs
    assert _row(db, b).expected == Decimal("360.00")  # 4 x 12 x 7.50


def test_missing_rate_and_collection_without_loops_are_told_apart(db: Session) -> None:
    no_rate = _run(db, _route(db), loops=3)
    _collect(db, no_rate, "300.00")
    row = _row(db, no_rate)
    assert row.status is CS.NO_RATE and row.expected is None and row.difference is None

    route = _route(db)
    _rate(db, route, amount_per_loop=Decimal("100.00"))
    idle = _run(db, route, loops=0, legs=0)
    _collect(db, idle, "250.00")
    assert _row(db, idle).status is CS.NO_LOOPS


def test_rates_are_versioned_and_audited(client: TestClient, db: Session) -> None:
    route = _route(db)
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    url = f"/api/v1/routes/{route.id}/revenue-rates"
    first = client.post(
        url,
        headers=acc,
        json={
            "model": "PER_LOOP",
            "amount_per_loop": "100.00",
            "effective_from": (YESTERDAY - timedelta(days=10)).isoformat(),
        },
    )
    assert first.status_code == 201, first.text
    second = client.post(
        url,
        headers=acc,
        json={
            "model": "PER_LOOP",
            "amount_per_loop": "120.00",
            "effective_from": YESTERDAY.isoformat(),
        },
    )
    assert second.status_code == 201
    rates = client.get(url, headers=acc).json()
    assert [r["amount_per_loop"] for r in rates] == ["120.00", "100.00"]
    assert rates[1]["effective_to"] == (YESTERDAY - timedelta(days=1)).isoformat()
    # Past days keep the rate that applied then.
    shift = _run(db, route, loops=2)
    assert _row(db, shift).expected == Decimal("240.00")
    actions = set(
        db.scalars(
            select(AuditLog.action).where(AuditLog.entity_type == "route_revenue_rate")
        ).all()
    )
    assert {"route_revenue_rate.created", "route_revenue_rate.closed"} <= actions

    # Validation: the model's amount is required; per-loop needs a round-trip route.
    missing = client.post(
        url, headers=acc, json={"model": "PER_LEG", "effective_from": local_today().isoformat()}
    )
    assert missing.status_code == 422
    one_way = _route(db, pattern="ONE_WAY")
    bad = client.post(
        f"/api/v1/routes/{one_way.id}/revenue-rates",
        headers=acc,
        json={
            "model": "PER_LOOP",
            "amount_per_loop": "50",
            "effective_from": local_today().isoformat(),
        },
    )
    assert bad.status_code == 422
    # Operations staff cannot set revenue figures.
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    denied = client.post(
        url,
        headers=ops,
        json={
            "model": "PER_LOOP",
            "amount_per_loop": "1",
            "effective_from": local_today().isoformat(),
        },
    )
    assert denied.status_code == 403


def test_report_lists_days_with_status(client: TestClient, db: Session) -> None:
    route = _route(db)
    _rate(db, route, amount_per_loop=Decimal("120.00"))
    shift = _run(db, route, loops=5)
    _collect(db, shift, "400.00")
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    report = _report(client, acc, "expected_collection", vehicle_id=str(shift.vehicle_id))
    [row] = report["rows"]
    assert row["status"] == "فرق تحصيل — مراجعة مطلوبة"
    assert row["expected"] == "600.00" and row["difference"] == "-200.00"
    assert report["totals"]["expected"] == "600.00"
