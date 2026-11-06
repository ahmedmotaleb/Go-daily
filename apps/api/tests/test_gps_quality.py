"""Explainable shift GPS quality (U03)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.models.tracking import GpsPoint, PointQuality
from app.services.gps_quality import GpsQuality, QualityGrade, assess

T0 = datetime(2026, 3, 1, 6, 0, tzinfo=UTC)
G = QualityGrade


def _points(
    minutes: int,
    *,
    every_s: int = 30,
    start: datetime = T0,
    accuracy: float = 8,
    delay_s: float = 5,
    quality: PointQuality = PointQuality.VALID,
) -> list[GpsPoint]:
    out = []
    for i in range(minutes * 60 // every_s + 1):
        at = start + timedelta(seconds=i * every_s)
        out.append(
            GpsPoint(
                shift_id=uuid.uuid4(),
                client_point_id=uuid.uuid4(),
                recorded_at=at,
                received_at=at + timedelta(seconds=delay_s),
                latitude=30.0 + i * 0.0001,
                longitude=31.0,
                accuracy_m=accuracy,
                quality=quality,
            )
        )
    return out


def _assess(points: list[GpsPoint], minutes: int = 120, start: datetime = T0) -> GpsQuality:
    return assess(
        points,
        window_start=start,
        window_end=start + timedelta(minutes=minutes),
        settings=get_settings(),
    )


def _by_code(q: GpsQuality) -> dict[str, QualityGrade]:
    return {c.code: c.grade for c in q.checks}


def test_complete_accurate_live_data_is_excellent() -> None:
    q = _assess(_points(120))
    assert q.grade is G.EXCELLENT
    assert set(_by_code(q).values()) == {G.EXCELLENT}
    assert q.metrics.coverage_pct == 100.0
    assert q.metrics.median_accuracy_m == 8
    assert q.metrics.median_sync_delay_s == 5
    assert q.metrics.valid_points == 241


def test_a_twenty_minute_gap_is_good_not_excellent() -> None:
    points = _points(50) + _points(50, start=T0 + timedelta(minutes=70))
    q = _assess(points)
    assert q.grade is G.GOOD
    assert _by_code(q)["COVERAGE"] is G.GOOD
    assert _by_code(q)["LONGEST_GAP"] is G.GOOD
    assert q.metrics.gaps == 1 and q.metrics.longest_gap_minutes == 20.0
    assert q.metrics.coverage_pct == 83.3


def test_the_worst_metric_sets_the_grade_and_is_visible() -> None:
    points = _points(120)
    points[10].quality = PointQuality.MOCK
    q = _assess(points)
    assert q.grade is G.NEEDS_REVIEW
    assert [c.code for c in q.checks if c.grade is G.NEEDS_REVIEW] == ["MOCK_POINTS"]
    # Everything else is still reported with its own result.
    assert _by_code(q)["COVERAGE"] is G.EXCELLENT


def test_inaccurate_points_and_jumps_lower_the_grade() -> None:
    points = _points(120, accuracy=35)
    for p in points[:3]:
        p.quality = PointQuality.IMPLAUSIBLE_SPEED
    q = _assess(points)
    assert _by_code(q)["MEDIAN_ACCURACY"] is G.GOOD
    assert _by_code(q)["IMPOSSIBLE_JUMPS"] is G.NEEDS_REVIEW
    assert q.grade is G.NEEDS_REVIEW


def test_late_points_count_as_stale() -> None:
    on_time = _points(60)
    late = _points(60, start=T0 + timedelta(minutes=60), delay_s=2 * 3600)
    q = _assess(on_time + late)
    stale = next(c for c in q.checks if c.code == "STALE_SHARE")
    assert 49 < stale.value < 51 and stale.grade is G.GOOD
    assert q.metrics.p95_sync_delay_s == 7200
    mostly_late = _assess(_points(30) + _points(90, start=T0 + timedelta(minutes=30), delay_s=7200))
    assert _by_code(mostly_late)["STALE_SHARE"] is G.NEEDS_REVIEW


def test_missing_data_is_insufficient_never_guessed() -> None:
    nothing = _assess([])
    assert nothing.grade is G.INSUFFICIENT and nothing.insufficient_reason == "TOO_FEW_POINTS"
    assert nothing.metrics.coverage_pct == 0.0 and nothing.checks == []

    short = _assess(_points(10), minutes=10)
    assert short.grade is G.INSUFFICIENT and short.insufficient_reason == "TOO_SHORT"
    assert short.metrics.points == 21  # metrics are still shown

    not_started = assess(_points(10), window_start=None, window_end=None, settings=get_settings())
    assert not_started.insufficient_reason == "NOT_STARTED"
