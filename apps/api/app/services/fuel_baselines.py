"""Rolling vehicle fuel baselines (U14).

Each complete week (Saturday-Friday) is compared with:
- the vehicle's own history (median of the previous `FUEL_BASELINE_WEEKS`);
- its recent weeks (median of the previous `FUEL_RECENT_WEEKS`);
- when its own history is too short, other vehicles doing the same main
  operation type over the same weeks (peer baseline).

Metric. A week with one fuel is compared on physical efficiency (km per
litre / per m³ / per kg), so fuel price changes do not look like worse
consumption. A week with several fuels (CNG + gasoline) cannot split its
distance, so it is compared on cost per km, with unit prices shown so a
price rise can be told apart from higher use.

Incomplete data: weeks with a missing odometer reading or less than
`EXCEPTION_FUEL_MIN_WEEK_KM` are never used as a baseline or judged, and
a baseline needs at least `FUEL_BASELINE_MIN_WEEKS` usable weeks (peers:
`FUEL_PEER_MIN_SAMPLES`). Otherwise the result is "insufficient data".
"""

from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import local_day_bounds_utc, to_local_date, week_start
from app.models.operations import OperationKind
from app.models.shift import OperationSession, SessionStatus
from app.services import fuel_efficiency
from app.services.fuel_efficiency import EfficiencyRow

UNUSUAL_LABEL = "استهلاك غير معتاد — مراجعة مطلوبة"


class BaselineStatus(StrEnum):
    NORMAL = "NORMAL"  # ضمن المعتاد
    UNUSUAL = "UNUSUAL"  # استهلاك غير معتاد — مراجعة مطلوبة
    INSUFFICIENT = "INSUFFICIENT"  # بيانات غير كافية


STATUS_AR = {
    BaselineStatus.NORMAL: "ضمن المعتاد",
    BaselineStatus.UNUSUAL: UNUSUAL_LABEL,
    BaselineStatus.INSUFFICIENT: "بيانات غير كافية",
}


@dataclass
class Baseline:
    value: Decimal | None = None
    samples: int = 0


@dataclass
class WeekAssessment:
    vehicle_id: uuid.UUID
    vehicle_code: str
    week: date
    operation_kind: OperationKind | None
    distance_km: int
    metric: str  # "km_per_unit" or "egp_per_km"
    fuel: str | None  # fuel code and unit for km_per_unit
    current: Decimal | None
    historical: Baseline = field(default_factory=Baseline)
    recent: Baseline = field(default_factory=Baseline)
    peer: Baseline = field(default_factory=Baseline)
    basis: str | None = None  # which baseline the verdict used
    ratio: Decimal | None = None  # >1 means worse than the baseline
    status: BaselineStatus = BaselineStatus.INSUFFICIENT
    reason: str | None = None
    excluded_weeks: int = 0
    unit_price: dict[str, str] = field(default_factory=dict)
    fuel_cost: Decimal = Decimal("0")


def _usable(row: EfficiencyRow | None, min_km: int) -> bool:
    return (
        row is not None
        and not row.distance_missing
        and row.distance_km >= min_km
        and row.fuel_cost > 0
    )


def _metric(row: EfficiencyRow) -> tuple[str, str | None, Decimal | None]:
    if len(row.fuels) == 1:
        (code, unit), line = next(iter(row.fuels.items()))
        return "km_per_unit", f"{code}:{unit.value}", line.km_per_unit
    return "egp_per_km", None, row.egp_per_km


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return Decimal(str(statistics.median(values))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _worse_ratio(metric: str, current: Decimal, baseline: Decimal) -> Decimal | None:
    """How many times worse than the baseline (km/unit: lower is worse)."""
    if baseline <= 0 or current <= 0:
        return None
    raw = baseline / current if metric == "km_per_unit" else current / baseline
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _series(
    candidates: list[EfficiencyRow | None], metric: str, fuel: str | None, min_km: int
) -> tuple[list[Decimal], int]:
    """Values of the same metric (and fuel) from usable weeks; also how many
    recorded weeks were left out (incomplete, or a different fuel mix)."""
    values: list[Decimal] = []
    excluded = 0
    for row in candidates:
        if row is None:
            continue
        if not _usable(row, min_km):
            excluded += 1
            continue
        m, f, value = _metric(row)
        if (m, f) != (metric, fuel) or value is None:
            excluded += 1
            continue
        values.append(value)
    return values, excluded


def _dominant_kinds(
    db: Session, first_week: date, last_week: date
) -> dict[tuple[uuid.UUID, date], OperationKind]:
    """Main operation type per vehicle and week, by session minutes."""
    start = local_day_bounds_utc(first_week)[0]
    end = local_day_bounds_utc(last_week + timedelta(days=6))[1]
    minutes: dict[tuple[uuid.UUID, date], dict[OperationKind, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for s in db.scalars(
        select(OperationSession).where(
            OperationSession.status != SessionStatus.CANCELLED,
            OperationSession.started_at >= start,
            OperationSession.started_at < end,
        )
    ).all():
        until = s.ended_at or s.started_at
        key = (s.shift.vehicle_id, week_start(to_local_date(s.started_at)))
        minutes[key][s.operation_type.kind] += max(0.0, (until - s.started_at).total_seconds() / 60)
    return {k: max(v, key=lambda kind: v[kind]) for k, v in minutes.items() if v}


def assess(
    db: Session,
    first_week: date,
    last_week: date,
    *,
    vehicle_id: uuid.UUID | None = None,
) -> list[WeekAssessment]:
    """Assess every vehicle-week from `first_week` to `last_week` (week starts)."""
    s = get_settings()
    first_week, last_week = week_start(first_week), week_start(last_week)
    history_start = first_week - timedelta(days=7 * s.fuel_baseline_weeks)
    rows, _ = fuel_efficiency.compute(
        db, history_start, last_week + timedelta(days=6), period="week"
    )
    weeks: dict[uuid.UUID, dict[date, EfficiencyRow]] = defaultdict(dict)
    codes: dict[uuid.UUID, str] = {}
    for r in rows:
        weeks[r.vehicle_id][r.period_start] = r
        codes[r.vehicle_id] = r.vehicle_code
    kinds = _dominant_kinds(db, history_start, last_week)
    min_km = s.exception_fuel_min_week_km

    out: list[WeekAssessment] = []
    for vid, by_week in weeks.items():
        if vehicle_id and vid != vehicle_id:
            continue
        for week, row in sorted(by_week.items()):
            if not (first_week <= week <= last_week) or row.fuel_cost <= 0:
                continue
            metric, fuel, current = _metric(row)
            a = WeekAssessment(
                vehicle_id=vid,
                vehicle_code=codes[vid],
                week=week,
                operation_kind=kinds.get((vid, week)),
                distance_km=row.distance_km,
                metric=metric,
                fuel=fuel,
                current=current,
                fuel_cost=row.fuel_cost,
                unit_price={
                    f"{c}:{u.value}": str((ln.amount / ln.quantity).quantize(Decimal("0.01")))
                    for (c, u), ln in row.fuels.items()
                    if ln.quantity > 0
                },
            )
            out.append(a)
            if not _usable(row, min_km) or current is None:
                a.reason = "incomplete_week"
                continue

            previous = [week - timedelta(days=7 * k) for k in range(1, s.fuel_baseline_weeks + 1)]
            values, a.excluded_weeks = _series(
                [by_week.get(w) for w in previous], metric, fuel, min_km
            )
            a.historical = Baseline(_median(values), len(values))
            recent, _ = _series(
                [by_week.get(w) for w in previous[: s.fuel_recent_weeks]], metric, fuel, min_km
            )
            a.recent = Baseline(_median(recent), len(recent))
            if a.operation_kind is not None:
                peers = [
                    other_weeks.get(w)
                    for other_vid, other_weeks in weeks.items()
                    if other_vid != vid
                    for w in previous
                    if kinds.get((other_vid, w)) is a.operation_kind
                ]
                peer_values, _ = _series(peers, metric, fuel, min_km)
                a.peer = Baseline(_median(peer_values), len(peer_values))

            if a.historical.samples >= s.fuel_baseline_min_weeks and a.historical.value:
                a.basis, base = "historical", a.historical.value
            elif a.peer.samples >= s.fuel_peer_min_samples and a.peer.value:
                a.basis, base = "peer", a.peer.value
            else:
                a.reason = "not_enough_history"
                continue
            a.ratio = _worse_ratio(metric, current, base)
            if a.ratio is None:
                a.reason = "not_enough_history"
                continue
            threshold = Decimal(str(s.exception_fuel_ratio))
            a.status = BaselineStatus.UNUSUAL if a.ratio >= threshold else BaselineStatus.NORMAL
    return sorted(out, key=lambda a: (a.week, a.vehicle_code))
