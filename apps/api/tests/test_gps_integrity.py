"""GPS integrity evidence (U02): ingestion keeps it, rules turn it into review cases."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.exceptions import ExceptionLabel, OperationalException
from app.models.shift import Shift
from app.models.tracking import (
    GpsPoint,
    GpsUploadBatch,
    PointQuality,
    TrackingEvent,
    TrackingEventType,
)
from app.services import exception_rules as rules
from app.services import exceptions as engine
from tests.factories import make_completed_shift, make_driver_account
from tests.test_exceptions import YESTERDAY, add_points, codes, ctx_around, offset, pair
from tests.test_tracking import BASE, _point, _start, _upload

E = TrackingEventType


def _event(
    db: Session, shift: Shift, kind: TrackingEventType, minute: int, **details: str
) -> TrackingEvent:
    assert shift.started_at
    ev = TrackingEvent(
        shift_id=shift.id,
        driver_id=shift.driver_id,
        client_event_id=uuid.uuid4(),
        event_type=kind,
        occurred_at=shift.started_at + timedelta(minutes=minute),
        details=details or None,
    )
    db.add(ev)
    db.commit()
    return ev


def _batch(
    db: Session, shift: Shift, received_min: int, first_min: int, last_min: int, **kw: Any
) -> GpsUploadBatch:
    assert shift.started_at
    t0 = shift.started_at
    b = GpsUploadBatch(
        driver_id=shift.driver_id,
        shift_id=shift.id,
        client_batch_id=uuid.uuid4(),
        received_at=t0 + timedelta(minutes=received_min),
        point_count=10,
        accepted=10,
        duplicates=0,
        first_recorded_at=t0 + timedelta(minutes=first_min),
        last_recorded_at=t0 + timedelta(minutes=last_min),
        **{"rejected": 0, **kw},
    )
    db.add(b)
    db.commit()
    return b


# --- Ingestion ------------------------------------------------------------------


def test_ingestion_keeps_integrity_evidence_but_no_outside_locations(
    client: TestClient, db: Session
) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle.id)
    now = utcnow()
    before_shift = now - timedelta(hours=3)
    res = client.post(
        "/api/v1/driver/tracking/points",
        headers=h,
        json={
            "batch_id": str(uuid.uuid4()),
            "shift_id": shift["id"],
            "points": [
                _point(before_shift, *BASE),
                _point(now + timedelta(hours=2), *BASE),
                _point(now - timedelta(seconds=20), *BASE),
                _point(now - timedelta(seconds=10), *BASE),
            ],
            "device": {
                "app_version": "1.0",
                "device_time": (now + timedelta(minutes=40)).isoformat(),
            },
        },
    )
    assert res.status_code == 200, res.text
    batch = db.scalars(select(GpsUploadBatch).where(GpsUploadBatch.shift_id == shift["id"])).one()
    assert batch.rejected_outside_shift == 1
    assert batch.outside_shift_first_at == before_shift == batch.outside_shift_last_at
    assert batch.rejected_future == 1
    assert batch.future_max_seconds is not None and 7100 < batch.future_max_seconds <= 7200
    assert batch.first_recorded_at == now - timedelta(seconds=20)
    assert batch.last_recorded_at == now - timedelta(seconds=10)
    assert batch.device_time == now + timedelta(minutes=40)
    # Only the two in-shift points were stored; the outside one left no location.
    stored = db.scalars(select(GpsPoint.recorded_at).where(GpsPoint.shift_id == shift["id"])).all()
    assert sorted(stored) == [now - timedelta(seconds=20), now - timedelta(seconds=10)]


def test_old_clients_without_device_time_still_upload(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle.id)
    res = _upload(client, h, shift["id"], [_point(utcnow(), *BASE)])
    assert res.status_code == 200 and res.json()["accepted"] == 1


# --- Tracking interruptions --------------------------------------------------------


def test_restart_measures_the_time_without_tracking(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=120)
    assert shift.started_at
    add_points(db, shift, shift.started_at, minutes=30)
    _event(db, shift, E.TRACKING_STARTED, 0, boot_count="5")
    restart = _event(db, shift, E.SERVICE_RESTARTED, 50, boot_count="5")
    add_points(db, shift, shift.started_at + timedelta(minutes=50), minutes=70)

    result = rules.tracking_interrupted(ctx_around(db, shift))
    assert codes(result) == ["TRACKING_INTERRUPTED"]
    c = result.candidates[0]
    assert c.evidence["minutes"] == 20
    assert c.evidence["detected_by"] == "last_point"
    assert c.evidence["reboot_detected"] is False
    assert c.evidence["device_time"] == restart.occurred_at.isoformat()
    assert c.evidence["reported_at"] is not None
    assert c.severity.value == "LOW"
    assert c.shift_id == shift.id and c.driver_id == driver.id and c.vehicle_id == vehicle.id
    assert c.occurred_until == restart.occurred_at


def test_reboot_is_recognised_from_the_boot_counter(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=180)
    assert shift.started_at
    add_points(db, shift, shift.started_at, minutes=30)
    _event(db, shift, E.TRACKING_STARTED, 0, boot_count="5")
    _event(db, shift, E.TRACKING_STOPPED, 35, reason="service_stopped")
    _event(db, shift, E.SERVICE_RESTARTED, 110, boot_count="6")

    c = rules.tracking_interrupted(ctx_around(db, shift)).candidates[0]
    assert c.evidence["reboot_detected"] is True
    assert c.evidence["detected_by"] == "stop_event"
    assert c.evidence["minutes"] == 75
    assert c.severity.value == "MEDIUM"
    assert "إعادة تشغيل الهاتف" in c.summary


def test_stop_without_restart_and_normal_ends(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=120)
    assert shift.started_at
    add_points(db, shift, shift.started_at, minutes=90)
    _event(db, shift, E.TRACKING_STARTED, 0)
    _event(db, shift, E.SERVICE_RESTARTED, 40)  # points kept coming: nothing lost
    _event(db, shift, E.TRACKING_STOPPED, 100, reason="service_stopped")
    _event(db, shift, E.TRACKING_STOPPED, 120, reason="shift_ended")

    result = rules.tracking_interrupted(ctx_around(db, shift))
    assert len(result.candidates) == 1
    c = result.candidates[0]
    assert c.evidence["minutes"] == 20
    assert c.evidence["restarted_at"] is None
    assert c.severity.value == "MEDIUM"
    assert len(result.scopes) == 2  # the short restart is in scope, so it can clear


# --- Point-level checks -----------------------------------------------------------


def _raw_point(
    db: Session,
    shift: Shift,
    at: datetime,
    where: tuple[float, float],
    quality: PointQuality = PointQuality.VALID,
    received_at: datetime | None = None,
) -> None:
    db.add(
        GpsPoint(
            shift_id=shift.id,
            driver_id=shift.driver_id,
            vehicle_id=shift.vehicle_id,
            client_point_id=uuid.uuid4(),
            recorded_at=at,
            received_at=received_at or at,
            latitude=where[0],
            longitude=where[1],
            accuracy_m=10,
            quality=quality,
        )
    )


def test_impossible_jumps_report_the_implied_speed(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=60)
    assert shift.started_at
    t0 = shift.started_at
    _raw_point(db, shift, t0, offset())
    _raw_point(
        db, shift, t0 + timedelta(seconds=10), offset(east_m=20_000), PointQuality.IMPLAUSIBLE_SPEED
    )
    _raw_point(db, shift, t0 + timedelta(seconds=20), offset(north_m=100))
    db.commit()

    result = rules.impossible_jumps(ctx_around(db, shift))
    assert codes(result) == ["IMPOSSIBLE_JUMP"]
    ev = result.candidates[0].evidence
    assert ev["points"] == 1
    assert ev["examples"][0]["distance_m"] == pytest.approx(20_000, abs=50)
    assert ev["max_speed_kmh"] == pytest.approx(7200, abs=20)
    assert result.candidates[0].severity.value == "LOW"


def test_late_uploads_are_flagged_with_their_delay(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=60)
    assert shift.started_at
    t0 = shift.started_at
    _raw_point(db, shift, t0, offset(), received_at=t0 + timedelta(hours=1))
    _raw_point(db, shift, t0 + timedelta(minutes=5), offset(), received_at=t0 + timedelta(hours=14))
    db.commit()

    result = rules.late_uploads(ctx_around(db, shift))
    assert codes(result) == ["LATE_GPS_UPLOAD"]
    ev = result.candidates[0].evidence
    assert ev["points"] == 1 and ev["max_delay_hours"] == 13.9
    assert "بلا إنترنت" in result.candidates[0].summary


# --- Batch-level checks -------------------------------------------------------------


def test_out_of_shift_points_and_timestamp_anomalies(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=120)
    assert shift.started_at
    t0 = shift.started_at
    _batch(db, shift, 11, 0, 10, device_time=t0 + timedelta(minutes=11, seconds=5))
    _batch(db, shift, 21, 2, 20)  # goes back 8 minutes
    _batch(db, shift, 31, 20, 30, device_time=t0 + timedelta(minutes=71))  # clock 40 min ahead
    _batch(
        db,
        shift,
        41,
        30,
        40,
        rejected=5,
        rejected_outside_shift=3,
        outside_shift_first_at=t0 - timedelta(minutes=50),
        outside_shift_last_at=t0 - timedelta(minutes=20),
        rejected_future=2,
        future_max_seconds=7200,
    )
    ctx = ctx_around(db, shift)

    out = rules.out_of_shift_points(ctx)
    assert codes(out) == ["OUT_OF_SHIFT_GPS"]
    assert out.candidates[0].evidence["points"] == 3
    assert out.candidates[0].occurred_at == t0 - timedelta(minutes=50)
    assert "lat" not in out.candidates[0].evidence

    ts = rules.timestamp_anomalies(ctx)
    assert codes(ts) == ["TIMESTAMP_ANOMALY"]
    ev = ts.candidates[0].evidence
    assert ev["backwards_batches"] == 1 and ev["max_backwards_minutes"] == 8.0
    assert ev["clock_offset_batches"] == 1 and ev["max_clock_offset_minutes"] == 40.0
    assert ev["future_points"] == 2 and ev["future_max_minutes"] == 120.0
    assert ts.candidates[0].severity.value == "MEDIUM"


def test_ordinary_batches_raise_nothing(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=60)
    assert shift.started_at
    t0 = shift.started_at
    _batch(db, shift, 1, 0, 1, device_time=t0 + timedelta(minutes=1, seconds=-3))
    # Slight overlap within the tolerance (batches cut mid-second, retries).
    _batch(db, shift, 2, 0, 2, device_time=t0 + timedelta(minutes=2, seconds=20))
    ctx = ctx_around(db, shift)
    assert rules.timestamp_anomalies(ctx).candidates == []
    assert rules.out_of_shift_points(ctx).candidates == []


# --- Engine and wording ---------------------------------------------------------------


def test_integrity_cases_are_stored_for_review_with_neutral_wording(db: Session) -> None:
    driver, vehicle = pair(db)
    shift = make_completed_shift(db, driver, vehicle, day=YESTERDAY, minutes=120)
    assert shift.started_at
    add_points(db, shift, shift.started_at, minutes=30)
    _event(db, shift, E.SERVICE_RESTARTED, 60)
    _batch(db, shift, 70, 0, 30, rejected_outside_shift=1, outside_shift_first_at=shift.started_at)

    engine.run_detection(db, actor=None, trigger="test", days=7)
    found = {
        e.rule_code: e
        for e in db.scalars(
            select(OperationalException).where(OperationalException.shift_id == shift.id)
        )
    }
    interrupted = found["TRACKING_INTERRUPTED"]
    assert interrupted.label is ExceptionLabel.REVIEW_REQUIRED
    assert interrupted.status.value == "OPEN"
    assert interrupted.driver_id == driver.id and interrupted.vehicle_id == vehicle.id
    assert interrupted.occurred_until is not None and interrupted.detected_at is not None
    assert found["OUT_OF_SHIFT_GPS"].label is ExceptionLabel.UNUSUAL


def test_no_rule_accuses_anyone() -> None:
    accusing = ("سرقة", "سارق", "احتيال", "تلاعب", "غش", "تزوير")
    for info in rules.RULE_INFO.values():
        text = info.title_ar + info.description_ar
        assert not any(word in text for word in accusing), info.code
        assert info.label in (ExceptionLabel.REVIEW_REQUIRED, ExceptionLabel.UNUSUAL)
