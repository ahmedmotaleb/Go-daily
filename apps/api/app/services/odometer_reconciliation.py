"""GPS vs odometer distance for a shift (U04).

One definition, used by the shift page, the report and the exception rule.
Missing data is kept apart from a real difference: a shift without both
odometer readings, or without enough GPS coverage, is reported as missing
data and never as a suspicious difference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.core.config import Settings
from app.models.shift import Shift, ShiftStatus
from app.services.track_analysis import TrackPoint, find_gaps, recorded_distance_m


class ReconciliationStatus(StrEnum):
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"  # ضمن الحد المسموح
    REVIEW = "REVIEW"  # فرق يحتاج مراجعة
    MISSING_ODOMETER = "MISSING_ODOMETER"  # قراءة العداد ناقصة
    INSUFFICIENT_GPS = "INSUFFICIENT_GPS"  # تغطية GPS غير كافية
    NOT_COMPLETED = "NOT_COMPLETED"  # الوردية لم تنتهِ


@dataclass
class Reconciliation:
    status: ReconciliationStatus
    odometer_km: int | None
    gps_km: float | None
    # Signed: positive when the odometer shows more than GPS.
    difference_km: float | None
    abs_difference_km: float | None
    # Absolute difference as a share of the odometer distance.
    difference_pct: float | None
    allowed_km: float | None
    gps_coverage_pct: float | None
    tolerance_pct: float
    tolerance_km: float
    min_gps_coverage_pct: float
    # Everything that is missing, not only the reason shown first.
    missing: list[str] = field(default_factory=list)
    odometer_corrected: bool = False
    original_start_odometer_km: int | None = None
    original_end_odometer_km: int | None = None


def reconcile(shift: Shift, track: list[TrackPoint], settings: Settings) -> Reconciliation:
    """Compare a shift's odometer distance with its GPS distance (valid points only)."""
    s = settings
    out = Reconciliation(
        status=ReconciliationStatus.NOT_COMPLETED,
        odometer_km=shift.odometer_distance_km,
        gps_km=None,
        difference_km=None,
        abs_difference_km=None,
        difference_pct=None,
        allowed_km=None,
        gps_coverage_pct=None,
        tolerance_pct=s.exception_odometer_tolerance_pct,
        tolerance_km=s.exception_odometer_tolerance_km,
        min_gps_coverage_pct=s.exception_odometer_min_gps_coverage_pct,
        odometer_corrected=(
            shift.original_start_odometer_km is not None
            or shift.original_end_odometer_km is not None
        ),
        original_start_odometer_km=shift.original_start_odometer_km,
        original_end_odometer_km=shift.original_end_odometer_km,
    )
    if shift.status is not ShiftStatus.COMPLETED or not shift.started_at or not shift.ended_at:
        return out
    total = (shift.ended_at - shift.started_at).total_seconds()
    if total > 0:
        gaps = find_gaps(
            track,
            window_start=shift.started_at,
            window_end=shift.ended_at,
            max_gap_seconds=s.gps_gap_seconds,
        )
        out.gps_coverage_pct = round(100 * (1 - sum(g.seconds for g in gaps) / total), 1)
    out.gps_km = round(recorded_distance_m(track, max_gap_seconds=s.gps_gap_seconds) / 1000, 2)

    if out.odometer_km is None:
        out.missing.append("ODOMETER")
    if len(track) < 2 or (out.gps_coverage_pct or 0) < s.exception_odometer_min_gps_coverage_pct:
        out.missing.append("GPS")
    if out.odometer_km is not None:
        diff = out.odometer_km - out.gps_km
        out.difference_km = round(diff, 2)
        out.abs_difference_km = round(abs(diff), 2)
        out.difference_pct = (
            round(100 * abs(diff) / out.odometer_km, 1) if out.odometer_km else None
        )
        out.allowed_km = round(
            max(
                s.exception_odometer_tolerance_km,
                s.exception_odometer_tolerance_pct / 100 * max(out.odometer_km, out.gps_km),
            ),
            2,
        )
    if "ODOMETER" in out.missing:
        out.status = ReconciliationStatus.MISSING_ODOMETER
    elif "GPS" in out.missing:
        # Without enough GPS the comparison would rest on missing data.
        out.status = ReconciliationStatus.INSUFFICIENT_GPS
    elif out.abs_difference_km is not None and out.allowed_km is not None:
        out.status = (
            ReconciliationStatus.REVIEW
            if out.abs_difference_km > out.allowed_km
            else ReconciliationStatus.WITHIN_TOLERANCE
        )
    return out
