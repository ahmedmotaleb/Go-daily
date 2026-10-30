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
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

Reporter = Callable[[BaseException, dict[str, Any]], None]
_reporters: list[Reporter] = []


def register(reporter: Reporter) -> None:
    _reporters.append(reporter)


def clear() -> None:
    _reporters.clear()


def capture_exception(exc: BaseException, **context: Any) -> None:
    for reporter in list(_reporters):
        try:
            reporter(exc, context)
        except Exception:  # a broken reporter must never break the app
            logger.warning("error_reporter_failed", exc_info=True)
