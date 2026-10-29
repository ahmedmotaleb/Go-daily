"""Per-request context (client IP, user agent) for audit records."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    ip_address: str | None = None
    user_agent: str | None = None


_EMPTY = RequestContext()
_ctx: contextvars.ContextVar[RequestContext | None] = contextvars.ContextVar(
    "request_context", default=None
)


def set_request_context(ctx: RequestContext) -> contextvars.Token[RequestContext | None]:
    return _ctx.set(ctx)


def reset_request_context(token: contextvars.Token[RequestContext | None]) -> None:
    _ctx.reset(token)


def get_request_context() -> RequestContext:
    return _ctx.get() or _EMPTY
