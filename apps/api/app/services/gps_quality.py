"""Explainable GPS quality for one shift (U03).

The grade is never a black box: each metric is checked against two
published thresholds ("excellent" and "good"), the shift gets the worst
of those results, and every metric is returned with its value so a
reviewer can see exactly why. Missing data is reported as "insufficient",
never filled in or guessed.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.core.config import Settings
from app.models.tracking import GpsPoint, PointQuality
from app.services.track_analysis import TrackPoint, find_gaps


class QualityGrade(StrEnum):
    EXCELLENT = "EXCELLENT"  # ممتاز
    GOOD = "GOOD"  # جيد
    NEEDS_REVIEW = "NEEDS_REVIEW"  # يحتاج مراجعة
    INSUFFICIENT = "INSUFFICIENT"  # بيانات غير كافية


_ORDER = [QualityGrade.EXCELLENT, QualityGrade.GOOD, QualityGrade.NEEDS_REVIEW]


@dataclass(frozen=True)
class QualityCheck:
    code: str
    value: float
    unit: str
    excellent: float
    good: float
    higher_is_better: bool
    grade: QualityGrade


@dataclass
class QualityMetrics:
    duration_minutes: int = 0
    points: int = 0
    valid_points: int = 0
    low_accuracy_points: int = 0
    impossible_jumps: int = 0
    mock_points: int = 0
    coverage_pct: float | None = None
    gaps: int = 0
    longest_gap_minutes: float = 0
    median_accuracy_m: float | None = None
    stale_points: int = 0
    median_sync_delay_s: float | None = None
    p95_sync_delay_s: float | None = None


@dataclass
class GpsQuality:
    grade: QualityGrade
    metrics: QualityMetrics
    checks: list[QualityCheck] = field(default_factory=list)
    # Why the grade is "insufficient", if it is.
    insufficient_reason: str | None = None
    # The shift is still running: figures are "so far".
    partial: bool = False


def _grade(value: float, excellent: float, good: float, *, higher_is_better: bool) -> QualityGrade:
    if higher_is_better:
        if value >= excellent:
            return QualityGrade.EXCELLENT
        return QualityGrade.GOOD if value >= good else QualityGrade.NEEDS_REVIEW
    if value <= excellent:
        return QualityGrade.EXCELLENT
    return QualityGrade.GOOD if value <= good else QualityGrade.NEEDS_REVIEW


def _check(
    code: str, value: float, unit: str, excellent: float, good: float, *, higher: bool = False
) -> QualityCheck:
    return QualityCheck(
        code=code,
        value=round(value, 1),
        unit=unit,
        excellent=excellent,
        good=good,
        higher_is_better=higher,
        grade=_grade(value, excellent, good, higher_is_better=higher),
    )


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def assess(
    points: list[GpsPoint],
    *,
    window_start: datetime | None,
    window_end: datetime | None,
    settings: Settings,
    partial: bool = False,
) -> GpsQuality:
    """Grade a shift's GPS data. `points` are all stored points of the shift."""
    s = settings
    m = QualityMetrics(points=len(points))
    for p in points:
        if p.quality is PointQuality.VALID:
            m.valid_points += 1
        elif p.quality is PointQuality.LOW_ACCURACY:
            m.low_accuracy_points += 1
        elif p.quality is PointQuality.IMPLAUSIBLE_SPEED:
            m.impossible_jumps += 1
        elif p.quality is PointQuality.MOCK:
            m.mock_points += 1

    delays = [
        max(0.0, (p.received_at - p.recorded_at).total_seconds())
        for p in points
        if p.received_at is not None
    ]
    if delays:
        m.median_sync_delay_s = round(statistics.median(delays))
        m.p95_sync_delay_s = round(_percentile(delays, 95))
        m.stale_points = sum(1 for d in delays if d > s.gps_quality_stale_minutes * 60)
    accuracies = [p.accuracy_m for p in points if p.accuracy_m is not None]
    if accuracies:
        m.median_accuracy_m = round(statistics.median(accuracies), 1)

    if window_start is None or window_end is None or window_end <= window_start:
        return GpsQuality(
            QualityGrade.INSUFFICIENT, m, insufficient_reason="NOT_STARTED", partial=partial
        )
    total = (window_end - window_start).total_seconds()
    m.duration_minutes = int(total // 60)
    track = [
        TrackPoint(p.recorded_at, p.latitude, p.longitude, p.accuracy_m, p.speed_mps)
        for p in points
        if p.quality is PointQuality.VALID
    ]
    # Same definition as the GPS-vs-odometer rule: time not inside a gap.
    gaps = find_gaps(
        track, window_start=window_start, window_end=window_end, max_gap_seconds=s.gps_gap_seconds
    )
    m.gaps = len(gaps)
    m.longest_gap_minutes = round(max((g.seconds for g in gaps), default=0) / 60, 1)
    m.coverage_pct = round(100 * (1 - sum(g.seconds for g in gaps) / total), 1)

    if m.duration_minutes < s.gps_quality_min_minutes:
        return GpsQuality(
            QualityGrade.INSUFFICIENT, m, insufficient_reason="TOO_SHORT", partial=partial
        )
    if m.valid_points < s.gps_quality_min_points:
        return GpsQuality(
            QualityGrade.INSUFFICIENT, m, insufficient_reason="TOO_FEW_POINTS", partial=partial
        )

    n = max(m.points, 1)
    checks = [
        _check("COVERAGE", m.coverage_pct, "%", 95, 80, higher=True),
        _check("LONGEST_GAP", m.longest_gap_minutes, "min", 10, 30),
        _check(
            "MEDIAN_ACCURACY",
            m.median_accuracy_m if m.median_accuracy_m is not None else s.gps_max_accuracy_m,
            "m",
            20,
            50,
        ),
        _check("LOW_ACCURACY_SHARE", 100 * m.low_accuracy_points / n, "%", 5, 15),
        _check("IMPOSSIBLE_JUMPS", m.impossible_jumps, "points", 0, 2),
        _check("MOCK_POINTS", m.mock_points, "points", 0, 0),
        _check("STALE_SHARE", 100 * m.stale_points / n, "%", 10, 50),
    ]
    grade = max((c.grade for c in checks), key=_ORDER.index)
    return GpsQuality(grade, m, checks, partial=partial)
