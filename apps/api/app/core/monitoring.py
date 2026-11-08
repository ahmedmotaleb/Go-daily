"""Error-monitoring integration point (Task 27).

Unhandled errors and failing background rules call `capture_exception`.
By default that only logs (the log line already has the traceback and the
request ID). To send errors to a monitoring service, register a reporter
at startup, e.g. for Sentry:

    import sentry_sdk
    sentry_sdk.init(dsn=..., send_default_pii=False)
    monitoring.register(lambda exc, ctx: sentry_sdk.capture_exception(exc))

Reporters receive only the exception and non-sensitive context (request
ID, path, component); never request bodies, tokens or personal data.

Every captured error is also counted by component (U37) and exposed on
/metrics as `godaily_errors_total{component}`, so alerts work without any
external service: api, exception_rule, notification_generator,
notification_delivery, storage.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

Reporter = Callable[[BaseException, dict[str, Any]], None]
_reporters: list[Reporter] = []
_lock = threading.Lock()
_errors: dict[str, int] = defaultdict(int)


def register(reporter: Reporter) -> None:
    _reporters.append(reporter)


def clear() -> None:
    _reporters.clear()


def capture_exception(exc: BaseException, **context: Any) -> None:
    with _lock:
        _errors[str(context.get("component", "unknown"))] += 1
    for reporter in list(_reporters):
        try:
            reporter(exc, context)
        except Exception:  # a broken reporter must never break the app
            logger.warning("error_reporter_failed", exc_info=True)


def error_counts() -> dict[str, int]:
    with _lock:
        return dict(_errors)


def reset_counts() -> None:
    with _lock:
        _errors.clear()


def render() -> list[str]:
    lines = [
        "# HELP godaily_errors_total Captured errors by component (per worker process).",
        "# TYPE godaily_errors_total counter",
    ]
    for component, n in sorted(error_counts().items()):
        lines.append(f'godaily_errors_total{{component="{component}"}} {n}')
    return lines
