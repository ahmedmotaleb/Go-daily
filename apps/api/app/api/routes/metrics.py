"""Prometheus metrics endpoint (Task 27). Disabled unless METRICS_TOKEN is set."""

from __future__ import annotations

import hmac
from datetime import timedelta

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.api.routes import health
from app.core import monitoring, ratelimit
from app.core.config import get_settings
from app.core.metrics import http_metrics
from app.core.time import utcnow
from app.models.exceptions import ExceptionSeverity, OperationalException
from app.models.finance import Expense, FuelTransaction, RecordStatus, RideHailingStatement
from app.models.maintenance import MaintenanceRecord
from app.models.shift import Shift, ShiftStatus
from app.models.tracking import GpsPoint
from app.services import ops_metrics, tracking
from app.services.exceptions import ACTIVE as ACTIVE_EXCEPTIONS
from app.services.exceptions import last_run

router = APIRouter(tags=["health"])


def _authorised(request: Request) -> bool:
    token = get_settings().metrics_token
    if token is None:
        return False
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    return hmac.compare_digest(supplied.encode(), token.get_secret_value().encode())


def _gauge(name: str, help_text: str, values: dict[str, float] | float) -> list[str]:
    lines = [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
    if isinstance(values, dict):
        for labels, v in values.items():
            lines.append(f"{name}{{{labels}}} {v}")
    else:
        lines.append(f"{name} {values}")
    return lines


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request, db: DbSession) -> Response:
    if not _authorised(request):
        # Indistinguishable from a missing route when disabled or unauthorised.
        return PlainTextResponse("Not Found", status_code=404)
    now = utcnow()
    lines = http_metrics.render() + ratelimit.backend_errors.render() + monitoring.render()
    lines += _gauge(
        "godaily_migrations_current",
        "1 when the database schema matches this build's migrations, else 0.",
        1 if health.migrations_current(db) else 0,
    )

    active = db.scalar(
        select(func.count()).select_from(Shift).where(Shift.status == ShiftStatus.ACTIVE)
    )
    lines += _gauge("godaily_active_shifts", "Shifts in progress.", active or 0)

    states: dict[str, int] = {"ONLINE": 0, "STALE": 0, "OFFLINE": 0}
    for pos in tracking.live_positions(db):
        states[pos.state] = states.get(pos.state, 0) + 1
    lines += _gauge(
        "godaily_tracking_vehicles",
        "Vehicles in an active shift by tracking state.",
        {f'state="{k}"': v for k, v in states.items()},
    )

    recent = db.scalar(
        select(func.count())
        .select_from(GpsPoint)
        .where(GpsPoint.received_at >= now - timedelta(minutes=5))
    )
    lines += _gauge(
        "godaily_gps_points_received_5m", "GPS points received in the last 5 minutes.", recent or 0
    )

    flow = ops_metrics.gps(db, now)
    lines += _gauge(
        "godaily_gps_points_per_minute",
        "GPS points received per minute (last 5 minutes).",
        round((recent or 0) / 5, 2),
    )
    lines += _gauge(
        "godaily_gps_points_rejected_5m",
        "GPS points refused in the last 5 minutes (outside the shift, future time, invalid).",
        flow["rejected_5m"],
    )
    lines += _gauge(
        "godaily_gps_sync_lag_seconds",
        "Delay between a point's phone time and its arrival, last 5 minutes.",
        {
            'stat="avg"': round(flow["sync_lag_avg"], 1),
            'stat="max"': round(flow["sync_lag_max"], 1),
        },
    )
    lines += _gauge(
        "godaily_device_pending_points",
        "Points still queued on phones in running shifts (as last reported).",
        flow["device_pending"],
    )
    lines += _gauge(
        "godaily_loop_detections_1h",
        "Fixed-route loops detected in the last hour.",
        ops_metrics.loops_last_hour(db, now),
    )
    lines += _gauge(
        "godaily_submissions_today",
        "Fuel, expense and revenue records created today (Cairo day).",
        {f'kind="{k}"': v for k, v in ops_metrics.submissions_today(db).items()},
    )

    by_severity = {s.value: 0 for s in ExceptionSeverity}
    for severity, n in db.execute(
        select(OperationalException.severity, func.count())
        .where(OperationalException.status.in_(ACTIVE_EXCEPTIONS))
        .group_by(OperationalException.severity)
    ).all():
        by_severity[severity.value] = n
    lines += _gauge(
        "godaily_open_exceptions",
        "Exception cases still needing review, by severity.",
        {f'severity="{k}"': v for k, v in by_severity.items()},
    )

    run = last_run(db)
    if run is not None and run.finished_at is not None:
        lines += _gauge(
            "godaily_exception_run_age_seconds",
            "Seconds since the last finished exception detection run.",
            round((now - run.finished_at).total_seconds()),
        )
        lines += _gauge(
            "godaily_exception_run_failed_rules",
            "Rules that failed in the last detection run.",
            len(run.errors or {}),
        )

    pending = 0
    for model in (FuelTransaction, Expense, MaintenanceRecord, RideHailingStatement):
        pending += (
            db.scalar(
                select(func.count())
                .select_from(model)
                .where(model.status == RecordStatus.SUBMITTED)
            )
            or 0
        )
    lines += _gauge(
        "godaily_pending_financial_reviews", "Financial records waiting for review.", pending
    )

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
