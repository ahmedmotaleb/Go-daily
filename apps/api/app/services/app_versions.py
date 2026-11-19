"""Driver app version policy (U43/U44).

The app sends its build number (Android versionCode) in `X-App-Version`.
`DRIVER_APP_MIN_VERSION` and `DRIVER_APP_RECOMMENDED_VERSION` set the policy:

- below the recommended version: the app shows an update notice;
- below the minimum: the app cannot START a new shift until it is updated.
  A shift already running is never interrupted: points, fuel, ending the
  shift and the close-out keep working, so no driver is cut off mid-shift.

An app that sends no version (builds before U44) counts as version 0.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.config import get_settings
from app.core.errors import DomainError


class UpdateStatus(StrEnum):
    OK = "OK"
    UPDATE_RECOMMENDED = "UPDATE_RECOMMENDED"
    UPDATE_REQUIRED = "UPDATE_REQUIRED"


class AppUpdateRequired(DomainError):
    status_code = 426
    code = "app_update_required"
    default_message = "حدّث تطبيق السائق إلى أحدث إصدار قبل بدء وردية جديدة"


def parse(header: str | None) -> int:
    try:
        return max(0, int((header or "").strip()))
    except ValueError:
        return 0


def status_for(version: int) -> UpdateStatus:
    s = get_settings()
    if version < s.driver_app_min_version:
        return UpdateStatus.UPDATE_REQUIRED
    if version < s.driver_app_recommended_version:
        return UpdateStatus.UPDATE_RECOMMENDED
    return UpdateStatus.OK


def require_for_new_shift(version: int) -> None:
    if status_for(version) is UpdateStatus.UPDATE_REQUIRED:
        raise AppUpdateRequired(
            details={"minimum_version": get_settings().driver_app_min_version, "version": version}
        )


__all__ = ["AppUpdateRequired", "UpdateStatus", "parse", "require_for_new_shift", "status_for"]
