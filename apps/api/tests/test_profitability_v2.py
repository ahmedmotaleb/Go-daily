"""Vehicle profitability V2 (U22): per route, per loop, per km and over time."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today
from app.models.finance import RecordStatus, RevenueEntry, RevenueKind
from app.models.route_events import EventSource, EventStatus, RouteEvent, RouteEventType
from app.models.shift import OperationSession
from app.services import profitability
from tests.factories import (
    login_as,
    make_completed_shift,
    make_driver,
    make_route,
    make_vehicle,
)

URL = "/api/v1/profitability/vehicles"


def test_buckets_follow_the_calendar() -> None:
    days = profitability.buckets(date(2026, 11, 1), date(2026, 11, 3), "day")
    assert len(days) == 3
    # 2026-11-07 is a Saturday: weeks run Saturday to Friday.
    weeks = profitability.buckets(date(2026, 11, 5), date(2026, 11, 20), "week")
    assert weeks[0] == (date(2026, 11, 5), date(2026, 11, 6))
    assert weeks[1] == (date(2026, 11, 7), date(2026, 11, 13))
    months = profitability.buckets(date(2026, 10, 15), date(2026, 12, 2), "month")
    assert months == [
        (date(2026, 10, 15), date(2026, 10, 31)),
        (date(2026, 11, 1), date(2026, 11, 30)),
        (date(2026, 12, 1), date(2026, 12, 2)),
    ]


def test_route_loop_and_km_figures(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver, vehicle = make_driver(db), make_vehicle(db)
    route = make_route(db, name="موقف ⇄ جامعة U22")
    day = local_today() - timedelta(days=2)
    shift = make_completed_shift(
        db, driver, vehicle, day=day, start_odometer_km=10_000, end_odometer_km=10_100
    )
    session = db.scalar(select(OperationSession).where(OperationSession.shift_id == shift.id))
    assert session is not None and shift.started_at is not None
    session.route_id = route.id
    db.add(
        RevenueEntry(
            kind=RevenueKind.FIXED_ROUTE_COLLECTION,
            vehicle_id=vehicle.id,
            driver_id=driver.id,
            shift_id=shift.id,
            session_id=session.id,
            operation_type_id=session.operation_type_id,
            occurred_on=day,
            amount=Decimal("1000"),
            status=RecordStatus.APPROVED,
        )
    )
    for n in range(4):
        db.add(
            RouteEvent(
                shift_id=shift.id,
                session_id=session.id,
                route_id=route.id,
                vehicle_id=vehicle.id,
                event_type=RouteEventType.LOOP_COMPLETED,
                occurred_at=shift.started_at + timedelta(hours=n + 1),
                source=EventSource.AUTO,
                status=EventStatus.ACTIVE if n < 3 else EventStatus.VOIDED,
                dedupe_key=f"u22-{shift.id}-{n}",
            )
        )
    db.commit()

    res = client.get(
        URL,
        headers=h,
        params={
            "date_from": day.isoformat(),
            "date_to": day.isoformat(),
            "vehicle_id": str(vehicle.id),
        },
    )
    assert res.status_code == 200, res.text
    [row] = res.json()["vehicles"]
    assert row["loops_count"] == 3  # voided loops do not count
    assert row["odometer_km"] == 100
    assert row["profit_per_loop"] == str(
        (Decimal(row["net_operating_profit"]) / 3).quantize(Decimal("0.01"))
    )
    assert row["profit_per_km"] == str(
        (Decimal(row["net_operating_profit"]) / 100).quantize(Decimal("0.01"))
    )
    [on_route] = [r for r in row["by_route"] if r["route"]]
    assert on_route["route"]["name"] == "موقف ⇄ جامعة U22"
    assert on_route["revenue"] == "1000.00" and on_route["session_minutes"] == 480

    series = client.get(
        f"{URL}/{vehicle.id}/series",
        headers=h,
        params={
            "date_from": (day - timedelta(days=1)).isoformat(),
            "date_to": day.isoformat(),
            "grain": "day",
        },
    )
    assert series.status_code == 200, series.text
    first, second = series.json()
    assert first["gross_revenue"] == "0.00" or Decimal(first["gross_revenue"]) == 0
    assert second["gross_revenue"] == "1000.00" and second["loops_count"] == 3
    too_many = client.get(
        f"{URL}/{vehicle.id}/series",
        headers=h,
        params={"date_from": "2025-01-01", "date_to": "2026-01-01", "grain": "day"},
    )
    assert too_many.status_code == 422
