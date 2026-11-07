"""Device vs server time (U45/U46).

Phones queue entries offline, so an entry can reach the server long after it
was recorded. The phone's time is kept exactly as submitted; it is used as
the record's business time only when it is plausible (not in the future and
inside the shift it belongs to). Otherwise the server's receive time is used
and the difference stays visible for review. Nothing is adjusted silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

FUTURE_TOLERANCE = timedelta(minutes=5)
WINDOW_TOLERANCE = timedelta(minutes=10)
# A difference this large between phone and server for a live request means
# the phone's clock is wrong (not just a slow network).
MAJOR_SKEW = timedelta(minutes=10)


@dataclass(frozen=True)
class EntryTime:
    at: datetime
    """Business time used for the record."""
    device_time_used: bool


def entry_time(
    recorded_at: datetime | None,
    *,
    received_at: datetime,
    window_start: datetime | None,
    window_end: datetime | None,
) -> EntryTime:
    if recorded_at is None:
        return EntryTime(received_at, False)
    if recorded_at > received_at + FUTURE_TOLERANCE:
        return EntryTime(received_at, False)
    if window_start is not None and recorded_at < window_start - WINDOW_TOLERANCE:
        return EntryTime(received_at, False)
    end = window_end or received_at
    if recorded_at > end + WINDOW_TOLERANCE:
        return EntryTime(received_at, False)
    return EntryTime(recorded_at, True)


__all__ = ["MAJOR_SKEW", "EntryTime", "entry_time"]
