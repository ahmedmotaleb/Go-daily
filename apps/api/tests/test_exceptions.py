"""Operational exception engine (Task 20): rules, dedupe, review workflow."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cli
from app.core.config import get_settings
from app.core.permissions import UserRole
from app.core.time import local_day_bounds_utc, local_today, utcnow
from app.models.attachment import Attachment, AttachmentKind, AttachmentOwner
from app.models.audit import AuditLog
from app.models.driver import Driver
from app.models.exceptions import ExceptionStatus, OperationalException
from app.models.finance import (
    Expense,
    FuelTransaction,
    PaidBy,
    PaymentMethod,
    QuantityUnit,
    RecordStatus,
)
from app.models.fleet import Vehicle
from app.models.operations import RouteDefinition, RouteStop
from app.models.shift import Shift
from app.models.tracking import GpsPoint, PointQuality, TrackingEvent, TrackingEventType
from app.services import exception_rules as rules
from app.services import exceptions as engine
from app.services.exception_rules import Candidate, Context, RuleResult, _week_start
from tests.factories import (
    expense_category_id,
    fuel_type_id,
    login_as,
    make_completed_shift,
    make_driver,
    make_platform,
    make_vehicle,
    operation_type_id,
)

LAT, LNG = 30.0444, 31.2357  # central Cairo
YESTERDAY = local_today() - timedelta(days=1)


def offset(north_m: float = 0, east_m: float = 0) -> tuple[float, float]:
    return (
        LAT + north_m / 111_320,
        LNG + east_m / (111_320 * math.cos(math.radians(LAT))),
    )


def add_points(
    db: Session,
    shift: Shift,
    start: datetime,
    *,
    minutes: int,
    every_s: int = 60,
    where: Any = lambda i: offset(),
    mock: bool = False,
) -> None:
    for i in range(minutes * 60 // every_s + 1):
        lat, lng = where(i)
        db.add(
            GpsPoint(
                shift_id=shift.id,
                driver_id=shift.driver_id,
                vehicle_id=shift.vehicle_id,
                client_point_id=uuid.uuid4(),
                recorded_at=start + timedelta(seconds=i * every_s),
                latitude=lat,
                longitude=lng,
                accuracy_m=10,
                is_mock=mock,
                quality=PointQuality.MOCK if mock else PointQuality.VALID,
            )
        )
    db.commit()


def ctx_around(db: Session, shift: Shift | None = None) -> Context:
    if shift is not None and shift.started_at and shift.ended_at:
        return Context(
            db,
            get_settings(),
            shift.started_at - timedelta(hours=1),
            shift.ended_at + timedelta(hours=1),
        )
    return Context(db, get_settings(), utcnow() - timedelta(days=3), utcnow())


def pair(db: Session) -> tuple[Driver, Vehicle]:
    return make_driver(db), make_vehicle(db)


def fuel(
    db: Session,
    vehicle: Vehicle,
    *,
    at: datetime,
    amount: str = "300",
    driver: Driver | None = None,
    paid_by: PaidBy = PaidBy.COMPANY,
    status: RecordStatus = RecordStatus.APPROVED,
    code: str = "CNG",
    **extra: Any,
) -> FuelTransaction:
    tx = FuelTransaction(
        vehicle_id=vehicle.id,
        driver_id=driver.id if driver else None,
        fuel_type_id=uuid.UUID(fuel_type_id(db, code)),
        quantity=Decimal("40"),
        unit=QuantityUnit.CUBIC_METER,
        total_amount=Decimal(amount),
        occurred_at=at,
        payment_method=PaymentMethod.CASH,
        paid_by=paid_by,
        status=status,
        **extra,
    )
    db.add(tx)
    db.commit()
    return tx


def codes(result: RuleResult) -> list[str]:
    return [c.rule_code for c in result.candidates]


# --- Tracking rules -----------------------------------------------------------


def test_gps_disabled_reports_duration_and_ignores_blips(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY)
    assert shift.started_at
    t0 = shift.started_at

    def event(kind: TrackingEventType, minute: int) -> None:
        db.add(
            TrackingEvent(
                shift_id=shift.id,
                driver_id=driver.id,
                client_event_id=uuid.uuid4(),
                event_type=kind,
                occurred_at=t0 + timedelta(minutes=minute),
            )
        )

    event(TrackingEventType.LOCATION_DISABLED, 60)
    event(TrackingEventType.LOCATION_ENABLED, 90)
    event(TrackingEventType.PERMISSION_DENIED, 200)
    event(TrackingEventType.PERMISSION_GRANTED, 202)  # 2 minutes: below the threshold
    db.commit()

    result = rules.gps_disabled(ctx_around(db, shift))
    assert len(result.candidates) == 1
    c = result.candidates[0]
    assert c.evidence["minutes"] == 30
    assert c.severity.value == "MEDIUM"
    assert c.shift_id == shift.id and c.driver_id == driver.id
    assert "30 دقيقة" in c.summary


def test_gps_gap_inside_a_shift_notes_movement(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=120)
    assert shift.started_at
    add_points(db, shift, shift.started_at, minutes=60)
    add_points(
        db,
        shift,
        shift.started_at + timedelta(minutes=100),
        minutes=20,
        where=lambda i: offset(east_m=3000),
    )
    result = rules.gps_gaps(ctx_around(db, shift))
    assert codes(result) == ["GPS_GAP"]
    c = result.candidates[0]
    assert c.evidence["total_minutes"] == 40
    assert c.evidence["gaps"][0]["moved_m"] == pytest.approx(3000, abs=20)
    assert c.severity.value == "MEDIUM"


def test_mock_locations_are_flagged(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=60)
    assert shift.started_at
    add_points(db, shift, shift.started_at, minutes=2, mock=True)
    result = rules.mock_location(ctx_around(db, shift))
    assert codes(result) == ["MOCK_LOCATION"]
    assert result.candidates[0].evidence["points"] == 3


def _route(db: Session, stops: list[tuple[float, float]]) -> RouteDefinition:
    route = RouteDefinition(
        name="خط تجريبي",
        operation_type_id=uuid.UUID(operation_type_id(db, "FIXED_ROUTE")),
        trip_pattern="ROUND_TRIP",
    )
    db.add(route)
    db.flush()
    for i, (lat, lng) in enumerate(stops):
        db.add(
            RouteStop(
                route_id=route.id,
                sequence=i + 1,
                kind="ORIGIN"
                if i == 0
                else "DESTINATION"
                if i == len(stops) - 1
                else "INTERMEDIATE",
                name=f"نقطة {i + 1}",
                latitude=Decimal(str(round(lat, 6))),
                longitude=Decimal(str(round(lng, 6))),
                radius_m=200,
            )
        )
    db.commit()
    return route


def test_long_stop_is_flagged_unless_at_a_route_stop(db: Session) -> None:
    driver, vehicle = pair(db)
    away = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=120)
    assert away.started_at
    add_points(db, away, away.started_at, minutes=60, where=lambda i: offset(north_m=5000))
    result = rules.long_stops(ctx_around(db, away))
    assert codes(result) == ["LONG_STOP"]
    assert result.candidates[0].evidence["stops"][0]["minutes"] == 60

    other_vehicle = make_vehicle(db)
    at_terminal = make_completed_shift(
        db, driver, other_vehicle, day=YESTERDAY - timedelta(days=1), minutes=120
    )
    assert at_terminal.started_at
    at_terminal.sessions[0].route = _route(db, [offset(), offset(east_m=8000)])
    db.commit()
    add_points(db, at_terminal, at_terminal.started_at, minutes=60)
    ctx = ctx_around(db, at_terminal)
    assert [c for c in rules.long_stops(ctx).candidates if c.shift_id == at_terminal.id] == []


def test_route_deviation_beyond_the_corridor(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=60)
    assert shift.started_at
    shift.sessions[0].route = _route(db, [offset(), offset(east_m=10_000)])
    db.commit()
    add_points(db, shift, shift.started_at, minutes=20, where=lambda i: offset(east_m=i * 200))
    add_points(
        db,
        shift,
        shift.started_at + timedelta(minutes=21),
        minutes=15,
        where=lambda i: offset(north_m=4500, east_m=5000),
    )
    add_points(
        db,
        shift,
        shift.started_at + timedelta(minutes=37),
        minutes=20,
        where=lambda i: offset(east_m=6000 + i * 100),
    )
    result = rules.route_deviation(ctx_around(db, shift))
    assert codes(result) == ["ROUTE_DEVIATION"]
    c = result.candidates[0]
    assert c.evidence["segments"][0]["minutes"] == 15
    assert c.evidence["segments"][0]["max_distance_m"] == pytest.approx(4500, abs=30)
    assert c.severity.value == "MEDIUM"


def test_outside_area_needs_configuration(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=60)
    assert shift.started_at
    add_points(db, shift, shift.started_at, minutes=30, where=lambda i: offset(north_m=20_000))
    assert not rules.is_enabled("OUTSIDE_AREA", get_settings())
    assert rules.outside_area(ctx_around(db, shift)).candidates == []

    monkeypatch.setattr(get_settings(), "exception_operating_areas", f"{LAT},{LNG},10; bad")
    assert rules.is_enabled("OUTSIDE_AREA", get_settings())
    result = rules.outside_area(ctx_around(db, shift))
    assert codes(result) == ["OUTSIDE_AREA"]
    assert result.candidates[0].evidence["segments"][0]["max_beyond_m"] == pytest.approx(
        10_000, abs=50
    )


def test_gps_and_odometer_disagree_only_with_enough_coverage(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(
        db,
        driver,
        vehicle,
        day=YESTERDAY,
        minutes=120,
        start_odometer_km=1000,
        end_odometer_km=1100,
    )
    assert shift.started_at
    add_points(
        db, shift, shift.started_at, minutes=120, every_s=30, where=lambda i: offset(east_m=i * 100)
    )
    result = rules.gps_odometer_mismatch(ctx_around(db, shift))
    assert codes(result) == ["GPS_ODOMETER_MISMATCH"]
    ev = result.candidates[0].evidence
    assert ev["gps_km"] == pytest.approx(24, abs=0.5)
    assert ev["gps_coverage_pct"] == 100.0

    sparse_vehicle = make_vehicle(db)
    sparse = make_completed_shift(
        db,
        driver,
        sparse_vehicle,
        day=YESTERDAY - timedelta(days=1),
        minutes=120,
        start_odometer_km=1000,
        end_odometer_km=1100,
    )
    assert sparse.started_at
    add_points(
        db,
        sparse,
        sparse.started_at,
        minutes=60,
        every_s=30,
        where=lambda i: offset(east_m=i * 100),
    )
    assert rules.gps_odometer_mismatch(ctx_around(db, sparse)).candidates == []


# --- Odometer rules -----------------------------------------------------------


def test_vehicle_moved_between_shifts_and_backwards_odometer(db: Session) -> None:
    driver, vehicle = pair(db)
    make_completed_shift(
        db,
        driver,
        vehicle,
        day=YESTERDAY - timedelta(days=1),
        start_odometer_km=1000,
        end_odometer_km=1100,
    )
    nxt = make_completed_shift(
        db, driver, vehicle, day=YESTERDAY, start_odometer_km=1160, end_odometer_km=1200
    )
    result = rules.moved_between_shifts(ctx_around(db))
    assert codes(result) == ["MOVED_BETWEEN_SHIFTS"]
    c = result.candidates[0]
    assert c.evidence["difference_km"] == 60
    assert c.severity.value == "HIGH" and c.shift_id == nxt.id

    other = make_vehicle(db)
    make_completed_shift(
        db,
        driver,
        other,
        day=YESTERDAY - timedelta(days=1),
        start_odometer_km=1000,
        end_odometer_km=1100,
    )
    make_completed_shift(
        db, driver, other, day=YESTERDAY, start_odometer_km=1090, end_odometer_km=1150
    )
    backwards = [
        c for c in rules.implausible_odometer(ctx_around(db)).candidates if c.vehicle_id == other.id
    ]
    assert len(backwards) == 1
    assert backwards[0].evidence["difference_km"] == -10


def test_impossible_distance_for_shift_length(db: Session) -> None:
    driver, vehicle = pair(db)
    make_completed_shift(
        db, driver, vehicle, day=YESTERDAY, minutes=30, start_odometer_km=1000, end_odometer_km=1500
    )
    found = [
        c
        for c in rules.implausible_odometer(ctx_around(db)).candidates
        if c.vehicle_id == vehicle.id
    ]
    assert len(found) == 1
    assert found[0].evidence["max_plausible_km"] == 60


# --- Fuel rules ---------------------------------------------------------------


def test_fuel_cost_per_km_far_above_the_vehicles_own_history(db: Session) -> None:
    driver, vehicle = pair(db)
    target = _week_start(local_today()) - timedelta(days=7)
    for back in range(0, 5):
        week = target - timedelta(days=7 * back)
        day = week + timedelta(days=1)
        make_completed_shift(
            db,
            driver,
            vehicle,
            day=day,
            start_odometer_km=10_000 + back * 1000,
            end_odometer_km=10_300 + back * 1000,
        )
        fuel(
            db,
            vehicle,
            at=local_day_bounds_utc(day)[0] + timedelta(hours=12),
            amount="700" if back == 0 else "300",
        )
    result = rules.fuel_consumption(ctx_around(db))
    found = [c for c in result.candidates if c.vehicle_id == vehicle.id]
    assert len(found) == 1
    ev = found[0].evidence
    assert ev["week_start"] == target.isoformat()
    assert ev["cost_per_km"] == "2.33" and ev["baseline_cost_per_km"] == "1.00"
    assert found[0].severity.value == "MEDIUM"


def test_fuel_far_from_vehicle_when_both_locations_exist(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=60)
    assert shift.started_at
    add_points(db, shift, shift.started_at, minutes=30)
    at = shift.started_at + timedelta(minutes=15)
    far_lat, far_lng = offset(north_m=5000)
    tx = fuel(db, vehicle, at=at, driver=driver, latitude=far_lat, longitude=far_lng)
    fuel(db, vehicle, at=at, amount="99", driver=driver)  # no location: nothing to compare
    result = rules.fuel_far_from_vehicle(ctx_around(db, shift))
    assert [c.subject_id for c in result.candidates] == [tx.id]
    assert result.candidates[0].evidence["distance_m"] == pytest.approx(5000, abs=30)


def test_driver_fuel_outside_any_shift(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=60)
    assert shift.started_at
    night = shift.started_at + timedelta(hours=10)
    outside = fuel(db, vehicle, at=night, driver=driver, paid_by=PaidBy.DRIVER)
    fuel(db, vehicle, at=night, amount="250")  # company purchase: normal
    fuel(db, vehicle, at=shift.started_at + timedelta(minutes=20), amount="120", driver=driver)
    result = rules.fuel_outside_shift(ctx_around(db))
    assert [c.subject_id for c in result.candidates if c.vehicle_id == vehicle.id] == [outside.id]


# --- Duplicates & revenue -----------------------------------------------------


def test_duplicate_transactions_ignore_voided_records(db: Session) -> None:
    _, vehicle = pair(db)
    at = utcnow() - timedelta(hours=5)
    first = fuel(db, vehicle, at=at)
    second = fuel(db, vehicle, at=at + timedelta(minutes=20), status=RecordStatus.SUBMITTED)
    fuel(db, vehicle, at=at + timedelta(minutes=25), amount="55")
    fuel(db, vehicle, at=at + timedelta(minutes=30), amount="55", status=RecordStatus.VOIDED)
    cat = uuid.UUID(expense_category_id(db, "TOLL"))
    for minute in (0, 10):
        db.add(
            Expense(
                vehicle_id=vehicle.id,
                category_id=cat,
                amount=Decimal("15"),
                occurred_at=at + timedelta(minutes=minute),
                payment_method=PaymentMethod.CASH,
                paid_by=PaidBy.COMPANY,
                status=RecordStatus.APPROVED,
            )
        )
    db.commit()
    result = rules.duplicate_transactions(ctx_around(db))
    mine = [c for c in result.candidates if c.vehicle_id == vehicle.id]
    assert sorted(c.evidence["kind"] for c in mine) == ["expense", "fuel"]
    fuel_case = next(c for c in mine if c.evidence["kind"] == "fuel")
    assert {r["id"] for r in fuel_case.evidence["records"]} == {str(first.id), str(second.id)}


def test_same_file_on_different_records(db: Session) -> None:
    sha = "ab" * 32
    owners = [uuid.uuid4(), uuid.uuid4()]
    for owner in [*owners, owners[0]]:
        db.add(
            Attachment(
                owner_type=AttachmentOwner.EXPENSE,
                owner_id=owner,
                kind=AttachmentKind.EXPENSE_RECEIPT,
                storage_backend="local",
                storage_key=f"test/{uuid.uuid4()}",
                original_filename="r.jpg",
                content_type="image/jpeg",
                size_bytes=10,
                sha256=sha,
            )
        )
    db.add(
        Attachment(
            owner_type=AttachmentOwner.EXPENSE,
            owner_id=uuid.uuid4(),
            kind=AttachmentKind.EXPENSE_RECEIPT,
            storage_backend="local",
            storage_key=f"test/{uuid.uuid4()}",
            original_filename="other.jpg",
            content_type="image/jpeg",
            size_bytes=10,
            sha256="cd" * 32,
        )
    )
    db.commit()
    result = rules.duplicate_files(ctx_around(db))
    assert [c.dedupe_key for c in result.candidates] == [f"DUPLICATE_FILE:{sha}"]
    assert len(result.candidates[0].evidence["files"]) == 3


def test_platform_statement_without_recorded_ride_hailing(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver, vehicle = pair(db)
    platform = make_platform(db)
    res = client.post(
        "/api/v1/ride-hailing/statements",
        json={
            "platform_id": str(platform.id),
            "driver_id": str(driver.id),
            "vehicle_id": str(vehicle.id),
            "period_start": (YESTERDAY - timedelta(days=6)).isoformat(),
            "period_end": YESTERDAY.isoformat(),
            "trips_count": 30,
            "gross_earnings": "2000",
            "platform_fees": "500",
            "payout_recipient": "DRIVER",
        },
        headers=h,
    )
    assert res.status_code == 201, res.text
    result = rules.revenue_inconsistent(ctx_around(db))
    mine = [c for c in result.candidates if c.vehicle_id == vehicle.id]
    assert len(mine) == 1
    assert mine[0].subject_type == "ride_hailing_statement"
    assert "بدون ورديات" in mine[0].summary


# --- Engine -------------------------------------------------------------------


def _duplicate_pair(db: Session) -> tuple[Vehicle, FuelTransaction, FuelTransaction]:
    _, vehicle = pair(db)
    at = utcnow() - timedelta(hours=3)
    return vehicle, fuel(db, vehicle, at=at), fuel(db, vehicle, at=at + timedelta(minutes=5))


def _mine(db: Session, vehicle: Vehicle) -> list[OperationalException]:
    return list(
        db.scalars(
            select(OperationalException).where(OperationalException.vehicle_id == vehicle.id)
        ).all()
    )


def test_runs_are_idempotent_and_closed_cases_stay_closed(client: TestClient, db: Session) -> None:
    user, h = login_as(client, db, UserRole.OPERATIONS)
    vehicle, _, second = _duplicate_pair(db)

    first_run = client.post("/api/v1/exceptions/run", json={"days": 2}, headers=h)
    assert first_run.status_code == 200, first_run.text
    assert first_run.json()["results"]["DUPLICATE_TRANSACTION"]["new"] >= 1
    assert first_run.json()["results"]["OUTSIDE_AREA"] == {"skipped": "disabled"}
    again = client.post("/api/v1/exceptions/run", json={"days": 2}, headers=h).json()
    assert again["results"]["DUPLICATE_TRANSACTION"]["new"] == 0
    [case] = _mine(db, vehicle)

    res = client.post(
        f"/api/v1/exceptions/{case.id}/review",
        json={"status": "DISMISSED", "resolution": "إيصالان لتعبئتين فعليتين"},
        headers=h,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "DISMISSED"
    assert res.json()["reviewer"]["id"] == str(user.id)
    summary_before = case.summary

    second.total_amount = Decimal("301")  # no longer identical
    db.commit()
    client.post("/api/v1/exceptions/run", json={"days": 2}, headers=h)
    db.refresh(case)
    assert case.status is ExceptionStatus.DISMISSED
    assert case.summary == summary_before
    assert case.cleared_at is None  # closed cases are not touched


def test_cases_that_disappear_are_marked_no_longer_detected(db: Session) -> None:
    vehicle, _, second = _duplicate_pair(db)
    engine.run_detection(db, actor=None, trigger="cli", days=2)
    [case] = _mine(db, vehicle)
    assert case.cleared_at is None

    second.status = RecordStatus.VOIDED
    db.commit()
    engine.run_detection(db, actor=None, trigger="cli", days=2)
    db.refresh(case)
    assert case.status is ExceptionStatus.OPEN
    assert case.cleared_at is not None


def test_a_failing_rule_does_not_stop_the_others(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    vehicle, _, _ = _duplicate_pair(db)

    def boom(ctx: Context) -> RuleResult:
        raise RuntimeError("broken rule")

    info = rules.RuleInfo("BROKEN", "قاعدة معطلة", "", rules.R)
    monkeypatch.setattr(engine, "RULES", [(info, boom), *rules.RULES])
    run = engine.run_detection(db, actor=None, trigger="cli", days=2)
    assert run.errors == {"BROKEN": "RuntimeError"}
    assert run.finished_at is not None
    assert len(_mine(db, vehicle)) == 1


def test_candidate_storage_keeps_links_and_label(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY)
    info = rules.RULE_INFO["GPS_DISABLED"]
    outcome = RuleResult(
        candidates=[
            Candidate(
                rule_code="GPS_DISABLED",
                severity=rules.MEDIUM,
                summary="اختبار",
                evidence={"at": utcnow(), "amount": Decimal("1.50")},
                occurred_at=utcnow() - timedelta(hours=1),
                dedupe_key=f"TEST:{shift.id}",
                vehicle_id=vehicle.id,
                driver_id=driver.id,
                shift_id=shift.id,
            )
        ]
    )
    assert engine._store(db, info, outcome) == 1
    assert engine._store(db, info, outcome) == 0
    row = db.scalars(
        select(OperationalException).where(OperationalException.dedupe_key == f"TEST:{shift.id}")
    ).one()
    assert row.label.value == "REVIEW_REQUIRED"
    assert row.evidence["amount"] == "1.50"


# --- Review workflow & API ----------------------------------------------------


def _case(db: Session) -> OperationalException:
    vehicle, _, _ = _duplicate_pair(db)
    engine.run_detection(db, actor=None, trigger="cli", days=2)
    return _mine(db, vehicle)[0]


def test_review_workflow_rules_and_audit(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    case = _case(db)
    url = f"/api/v1/exceptions/{case.id}/review"

    res = client.post(url, json={"status": "UNDER_REVIEW"}, headers=h)
    assert res.status_code == 200 and res.json()["status"] == "UNDER_REVIEW"
    assert "OPEN" in res.json()["allowed_transitions"]

    res = client.post(url, json={"status": "ESCALATED"}, headers=h)
    assert res.status_code == 422  # escalation needs a note
    res = client.post(url, json={"status": "ESCALATED", "notes": "يحتاج رأي المدير"}, headers=h)
    assert res.status_code == 200

    res = client.post(url, json={"status": "EXPLAINED"}, headers=h)
    assert res.status_code == 422  # closing needs a resolution
    res = client.post(
        url, json={"status": "EXPLAINED", "resolution": "تعبئتان فعليتان بإيصالين"}, headers=h
    )
    assert res.status_code == 200 and res.json()["resolution"] == "تعبئتان فعليتان بإيصالين"

    assert (
        client.post(url, json={"status": "DISMISSED", "resolution": "x"}, headers=h).status_code
        == 409
    )
    assert client.post(url, json={"status": "OPEN"}, headers=h).status_code == 422
    res = client.post(url, json={"status": "OPEN", "notes": "ظهر إيصال ثالث"}, headers=h)
    assert res.status_code == 200 and res.json()["resolution"] is None

    audits = db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.entity_type == "operational_exception",
            AuditLog.entity_id == str(case.id),
            AuditLog.action == "operational_exception.reviewed",
        )
    )
    assert audits == 4


def test_list_filters_summary_rules_and_permissions(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    case = _case(db)
    res = client.get(
        "/api/v1/exceptions",
        params={"status": "ACTIVE", "vehicle_id": str(case.vehicle_id)},
        headers=h,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["rule_title"] == "سجل مكرر محتمل"
    assert item["label"] == "REVIEW_REQUIRED"
    assert item["vehicle"]["id"] == str(case.vehicle_id)

    closed = client.get(
        "/api/v1/exceptions",
        params={"status": "DISMISSED", "vehicle_id": str(case.vehicle_id)},
        headers=h,
    )
    assert closed.json()["total"] == 0
    assert client.get("/api/v1/exceptions", params={"status": "NOPE"}, headers=h).status_code == 422

    summary = client.get("/api/v1/exceptions/summary", headers=h).json()
    assert summary["active"] >= 1 and summary["by_rule"]["DUPLICATE_TRANSACTION"] >= 1

    meta = client.get("/api/v1/exceptions/rules", headers=h).json()
    assert {r["code"] for r in meta["rules"]} >= {"GPS_DISABLED", "FUEL_CONSUMPTION"}
    assert meta["thresholds"]["gps_gap_minutes"] == 15
    assert meta["last_run"]["trigger"] == "cli"

    assert client.get(f"/api/v1/exceptions/{case.id}", headers=h).status_code == 200
    assert client.get(f"/api/v1/exceptions/{uuid.uuid4()}", headers=h).status_code == 404

    _, driver_h = login_as(client, db, UserRole.DRIVER)
    assert client.get("/api/v1/exceptions", headers=driver_h).status_code in (401, 403)


def test_cli_detect_exceptions(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from contextlib import contextmanager

    @contextmanager
    def _session() -> Any:
        yield db

    monkeypatch.setattr(cli, "SessionLocal", _session)
    _duplicate_pair(db)
    assert cli.main(["detect-exceptions", "--days", "2"]) == 0
    assert "new" in capsys.readouterr().out


def test_old_closed_cases_lose_their_coordinates(db: Session) -> None:
    def case(status: ExceptionStatus, days_ago: int) -> OperationalException:
        exc = OperationalException(
            rule_code="LONG_STOP",
            severity=rules.LOW,
            label=rules.U,
            summary="توقف طويل",
            evidence={
                "stops": [{"start": "x", "minutes": 60, "lat": 30.0444, "lng": 31.2357}],
                "threshold_minutes": 45,
            },
            occurred_at=utcnow() - timedelta(days=days_ago),
            dedupe_key=f"TEST:{uuid.uuid4()}",
            status=status,
        )
        db.add(exc)
        db.commit()
        return exc

    old_closed = case(ExceptionStatus.DISMISSED, 200)
    old_open = case(ExceptionStatus.OPEN, 200)
    recent_closed = case(ExceptionStatus.EXPLAINED, 10)

    assert engine.redact_old_evidence(db, older_than_days=180) == 1
    db.refresh(old_closed)
    assert old_closed.evidence["stops"] == [{"start": "x", "minutes": 60}]
    assert old_closed.evidence["threshold_minutes"] == 45
    assert old_closed.evidence["coordinates_removed"] is True
    db.refresh(old_open)
    db.refresh(recent_closed)
    assert "lat" in old_open.evidence["stops"][0]  # still under review
    assert "lat" in recent_closed.evidence["stops"][0]  # within retention
    assert engine.redact_old_evidence(db, older_than_days=180) == 0  # idempotent
