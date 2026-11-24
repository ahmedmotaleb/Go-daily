"""Document expiry indicators (licenses, insurance)."""

from __future__ import annotations

from datetime import date, timedelta
from enum import StrEnum

from app.core.config import get_settings
from app.core.time import local_today


class ExpiryStatus(StrEnum):
    OK = "OK"
    EXPIRING_SOON = "EXPIRING_SOON"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


def expiry_status(expires_on: date | None, *, today: date | None = None) -> ExpiryStatus:
    if expires_on is None:
        return ExpiryStatus.UNKNOWN
    today = today or local_today()
    if expires_on < today:
        return ExpiryStatus.EXPIRED
    if expires_on <= today + timedelta(days=get_settings().expiry_warning_days):
        return ExpiryStatus.EXPIRING_SOON
    return ExpiryStatus.OK


def warning_cutoff(today: date | None = None) -> date:
    return (today or local_today()) + timedelta(days=get_settings().expiry_warning_days)
