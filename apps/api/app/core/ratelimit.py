"""Rate limits for login, 2FA and sensitive account actions (U32).

Two backends behind one `hit(key)` call:

- `RedisWindowLimiter`: shared by every API worker and server (any
  Redis-compatible store: Redis, Valkey, KeyDB, managed services). Fixed
  windows counted with an atomic INCR + EXPIRE, so attempts cannot be
  spread across workers to get around the limit.
- `SlidingWindowLimiter`: in-process, used when `REDIS_URL` is not set
  (development, a single worker) and as the fallback below.

If Redis cannot be reached, `ResilientLimiter` falls back to the in-process
limiter for that request: limits keep working per worker instead of being
switched off, the per-account lockout in the database still applies, and
the event is logged and counted (`godaily_ratelimit_backend_errors_total`)
so it is noticed. Keys (client IPs, user ids) are hashed before they reach
Redis, and nothing else is stored; entries expire with the window.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import threading
import time
from collections import deque
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class RateLimiter(Protocol):
    def hit(self, key: str) -> int | None:
        """Record an attempt. Seconds to wait when over the limit, else None."""
        ...

    def reset(self) -> None: ...


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, *, now: float | None = None) -> int | None:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1, int(hits[0] + self.window - now) + 1)
            hits.append(now)
            if len(self._hits) > 10_000:
                self._prune(now)
            return None

    def _prune(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:32]


class RedisWindowLimiter:
    """Fixed-window counter shared through Redis."""

    def __init__(self, client: Any, name: str, limit: int, window_seconds: int) -> None:
        self.client = client
        self.name = name
        self.limit = limit
        self.window = window_seconds

    def hit(self, key: str, *, now: float | None = None) -> int | None:
        now = time.time() if now is None else now
        bucket = int(now // self.window)
        redis_key = f"godaily:rl:{self.name}:{_digest(key)}:{bucket}"
        pipe = self.client.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, self.window + 1)
        count = int(pipe.execute()[0])
        if count > self.limit:
            return max(1, int((bucket + 1) * self.window - now) + 1)
        return None

    def reset(self) -> None:
        for k in self.client.scan_iter(match=f"godaily:rl:{self.name}:*"):
            self.client.delete(k)


class BackendErrors:
    """Count of Redis failures, exposed on /metrics."""

    def __init__(self) -> None:
        self.count = 0
        self._lock = threading.Lock()

    def add(self) -> None:
        with self._lock:
            self.count += 1

    def render(self) -> list[str]:
        return [
            "# HELP godaily_ratelimit_backend_errors_total Rate-limit store errors "
            "(the in-process fallback was used).",
            "# TYPE godaily_ratelimit_backend_errors_total counter",
            f"godaily_ratelimit_backend_errors_total {self.count}",
        ]


backend_errors = BackendErrors()


class ResilientLimiter:
    """Shared limiter with an in-process fallback when the store fails."""

    def __init__(self, primary: RedisWindowLimiter, fallback: SlidingWindowLimiter) -> None:
        self.primary = primary
        self.fallback = fallback

    def hit(self, key: str) -> int | None:
        try:
            return self.primary.hit(key)
        except Exception:  # any store/network error: degrade, never disable
            backend_errors.add()
            logger.warning("ratelimit_backend_unavailable", extra={"limiter": self.primary.name})
            return self.fallback.hit(key)

    def reset(self) -> None:
        self.fallback.reset()
        with contextlib.suppress(Exception):  # best effort in tests/maintenance
            self.primary.reset()


def build(name: str, limit: int, window_seconds: int, redis_url: str | None) -> RateLimiter:
    local = SlidingWindowLimiter(limit, window_seconds)
    if not redis_url:
        return local
    import redis  # noqa: PLC0415 - only needed when configured

    client = redis.Redis.from_url(redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
    return ResilientLimiter(RedisWindowLimiter(client, name, limit, window_seconds), local)


__all__ = [
    "RateLimiter",
    "RedisWindowLimiter",
    "ResilientLimiter",
    "SlidingWindowLimiter",
    "backend_errors",
    "build",
]
