"""GPS vs odometer reconciliation (U04)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import UserRole
from app.models.audit import AuditLog
from app.models.shift import Shift, ShiftStatus
from app.services import exception_rules as rules
from app.services import tracking
from app.services.odometer_reconciliation import Reconciliation, ReconciliationStatus, reconcile
from tests.factories import login_as, make_completed_shift
from tests.test_exceptions import YESTERDAY, add_points, ctx_around, offset, pair
from tests.test_reports import _report

RS = ReconciliationStatus


def _shift(db: Session, *, odometer_km: int, minutes: int = 60, start: int | None = 1_000) -> Shift:
    driver, vehicle = pair(db)
    return make_completed_shift(
        db,
        driver,
        vehicle,
        day=YESTERDAY,
        minutes=minutes,
        start_odometer_km=start,
        end_odometer_km=(start or 1_000) + odometer_km,
    )


def _drive(db: Session, shift: Shift, km: float, minutes: int = 60) -> None:
    """Points every minute along a straight line covering `km`."""
    assert shift.started_at
    step = km * 1000 / minutes
    add_points(
        db, shift, shift.started_at, minutes=minutes, where=lambda i: offset(east_m=i * step)
    )


def _rec(db: Session, shift: Shift) -> Reconciliation:
    return reconcile(shift, tracking.valid_tracks(db, [shift.id])[shift.id], get_settings())


def test_matching_distances_are_within_tolerance(db: Session) -> None:
    shift = _shift(db, odometer_km=11)
    _drive(db, shift, 10)
    rec = _rec(db, shift)
    assert rec.status is RS.WITHIN_TOLERANCE
    assert rec.gps_km == pytest.approx(10, abs=0.05)
    assert rec.difference_km == pytest.approx(1, abs=0.05)
    assert rec.difference_pct == pytest.approx(9.1, abs=0.5)
    assert rec.allowed_km == 5  # the 5 km floor beats 25% of 11 km
    assert rec.gps_coverage_pct == 100.0
    assert rec.missing == []


def test_a_large_difference_with_good_gps_needs_review(db: Session) -> None:
    shift = _shift(db, odometer_km=30)
    _drive(db, shift, 10)
    rec = _rec(db, shift)
    assert rec.status is RS.REVIEW
    assert rec.abs_difference_km == pytest.approx(20, abs=0.05)
    assert rec.difference_pct == pytest.approx(66.7, abs=0.2)
    assert rec.allowed_km == 7.5  # 25% of the larger distance (30 km)

    found = rules.gps_odometer_mismatch(ctx_around(db, shift)).candidates
    assert [c.shift_id for c in found] == [shift.id]
    assert found[0].evidence["difference_pct"] == rec.difference_pct


def test_missing_gps_is_not_a_difference(db: Session) -> None:
    shift = _shift(db, odometer_km=80, minutes=120)
    _drive(db, shift, 10, minutes=30)  # only the first quarter has GPS
    rec = _rec(db, shift)
    assert rec.status is RS.INSUFFICIENT_GPS
    assert rec.missing == ["GPS"]
    assert rec.gps_coverage_pct is not None and rec.gps_coverage_pct < 80
    # The numbers are still shown, but no review case is raised.
    assert rec.difference_km is not None
    assert rules.gps_odometer_mismatch(ctx_around(db, shift)).candidates == []


def test_missing_odometer_reading_is_reported_as_missing(db: Session) -> None:
    shift = _shift(db, odometer_km=10, start=None)
    rec = _rec(db, shift)
    assert rec.status is RS.MISSING_ODOMETER
    assert rec.missing == ["ODOMETER", "GPS"]
    assert rec.difference_km is None and rec.difference_pct is None


def test_running_shift_is_not_compared(db: Session) -> None:
    shift = _shift(db, odometer_km=10)
    shift.status = ShiftStatus.ACTIVE
    shift.ended_at = None
    shift.end_odometer_km = None
    db.commit()
    assert _rec(db, shift).status is RS.NOT_COMPLETED


def test_corrections_keep_the_first_reading_and_are_audited(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    shift = _shift(db, odometer_km=100)
    url = f"/api/v1/shifts/{shift.id}/odometer-correction"
    first = client.post(url, headers=h, json={"end_odometer_km": 1_050, "reason": "خطأ إدخال"})
    assert first.status_code == 200, first.text
    second = client.post(url, headers=h, json={"end_odometer_km": 1_060, "reason": "مراجعة ثانية"})
    body = second.json()
    assert body["end_odometer_km"] == 1_060
    assert body["original_end_odometer_km"] == 1_100  # still the reading first entered
    assert body["original_start_odometer_km"] is None  # never changed
    assert body["odometer_distance_km"] == 60
    entries = db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "shift.odometer_corrected", AuditLog.entity_id == str(shift.id))
    )
    assert entries == 2

    track = client.get(f"/api/v1/shifts/{shift.id}/track", headers=h).json()
    rec = track["odometer_reconciliation"]
    assert rec["odometer_corrected"] is True and rec["original_end_odometer_km"] == 1_100
    assert rec["status"] == "INSUFFICIENT_GPS"  # no points recorded for this shift


def test_report_shows_status_and_counts(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    ok = _shift(db, odometer_km=10)
    _drive(db, ok, 10)
    _shift(db, odometer_km=10)  # no GPS at all
    report = _report(client, h, "gps_odometer", vehicle_id=str(ok.vehicle_id))
    assert [r["status"] for r in report["rows"]] == ["ضمن الحد المسموح"]
    assert report["rows"][0]["corrected"] == "لا"
    everything = _report(client, h, "gps_odometer")
    statuses = {r["status"] for r in everything["rows"]}
    assert {"ضمن الحد المسموح", "تغطية GPS غير كافية"} <= statuses
    counts = {r["status"]: r["shifts"] for r in everything["summaries"][0]["rows"]}
    assert counts["تغطية GPS غير كافية"] >= 1
