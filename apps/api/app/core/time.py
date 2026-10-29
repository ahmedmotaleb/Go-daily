"""Time helpers.

Timestamps are stored in UTC (`timestamptz`). Business-day boundaries
(e.g. "today's shifts") are computed in the configured local timezone
(Africa/Cairo by default).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from app.core.config import get_settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def local_today() -> date:
    return utcnow().astimezone(get_settings().tz).date()


def local_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Return the [start, end) UTC instants of a local calendar day."""
    tz = get_settings().tz
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)
