"""Small in-process sliding-window rate limiter.

A safety net against credential stuffing on login, on top of the per-account
lockout. It is per API process: with several workers or servers, the edge
proxy (see docs/DEPLOYMENT.md) is the primary rate limit. Keys are client
IPs; nothing else is stored, and entries expire with the window.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, *, now: float | None = None) -> int | None:
        """Record an attempt. Returns seconds to wait if over the limit, else None."""
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
