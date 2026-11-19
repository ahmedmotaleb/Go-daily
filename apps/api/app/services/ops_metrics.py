"""Operational gauges for /metrics (U37/U38).

Computed from the database at scrape time, so every worker reports the same
values. Labels are only fixed words (kinds, states); never IDs, names,
phone numbers or coordinates.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import local_day_bounds_utc, local_today
from app.models.finance import Expense, FuelTransaction, RevenueEntry
from app.models.route_events import EventStatus, RouteEvent, RouteEventType
from app.models.shift import Shift, ShiftStatus
from app.models.tracking import GpsPoint, GpsUploadBatch

WINDOW = timedelta(minutes=5)


def gps(db: Session, now: datetime) -> dict[str, float]:
    since = now - WINDOW
    rejected = db.scalar(
        select(func.coalesce(func.sum(GpsUploadBatch.rejected), 0)).where(
            GpsUploadBatch.received_at >= since
        )
    )
    lag = func.extract("epoch", GpsPoint.received_at - GpsPoint.recorded_at)
    avg_lag, max_lag = db.execute(
        select(func.avg(lag), func.max(lag)).where(GpsPoint.received_at >= since)
    ).one()
    # Points still on the phones: the latest batch of each running shift says
    # how many it had not sent yet.
    latest = (
        select(
            GpsUploadBatch.pending_points,
            func.row_number()
            .over(partition_by=GpsUploadBatch.shift_id, order_by=GpsUploadBatch.received_at.desc())
            .label("rn"),
        )
        .join(Shift, Shift.id == GpsUploadBatch.shift_id)
        .where(Shift.status == ShiftStatus.ACTIVE)
        .subquery()
    )
    pending = db.scalar(
        select(func.coalesce(func.sum(latest.c.pending_points), 0)).where(latest.c.rn == 1)
    )
    return {
        "rejected_5m": float(rejected or 0),
        "sync_lag_avg": float(avg_lag or 0),
        "sync_lag_max": float(max_lag or 0),
        "device_pending": float(pending or 0),
    }


def loops_last_hour(db: Session, now: datetime) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(RouteEvent)
            .where(
                RouteEvent.event_type == RouteEventType.LOOP_COMPLETED,
                RouteEvent.status == EventStatus.ACTIVE,
                RouteEvent.occurred_at >= now - timedelta(hours=1),
            )
        )
        or 0
    )


def submissions_today(db: Session) -> dict[str, int]:
    start, end = local_day_bounds_utc(local_today())
    out: dict[str, int] = {}
    for kind, model in (("fuel", FuelTransaction), ("expense", Expense), ("revenue", RevenueEntry)):
        out[kind] = int(
            db.scalar(
                select(func.count())
                .select_from(model)
                .where(model.created_at >= start, model.created_at < end)
            )
            or 0
        )
    return out


__all__ = ["gps", "loops_last_hour", "submissions_today"]
