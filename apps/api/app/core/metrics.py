"""Prometheus-format metrics without extra dependencies (Task 27).

HTTP counters and latency are kept in-process per worker (scrape each
worker, or treat them as a sample). Fleet gauges are computed from the
database at scrape time, so they are the same from every worker.
"""

from __future__ import annotations

import threading
from collections import defaultdict

HIST = "godaily_http_request_duration_seconds"
BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class HttpMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self.buckets: dict[str, list[int]] = defaultdict(lambda: [0] * (len(BUCKETS) + 1))
        self.sums: dict[str, float] = defaultdict(float)

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        status_class = f"{status // 100}xx"
        with self._lock:
            self.requests[(method, route, status_class)] += 1
            counts = self.buckets[route]
            for i, bound in enumerate(BUCKETS):
                if seconds <= bound:
                    counts[i] += 1
            counts[-1] += 1  # +Inf
            self.sums[route] += seconds

    def render(self) -> list[str]:
        lines = [
            "# HELP godaily_http_requests_total HTTP requests by route template and status class.",
            "# TYPE godaily_http_requests_total counter",
        ]
        with self._lock:
            for (method, route, status_class), n in sorted(self.requests.items()):
                lines.append(
                    f'godaily_http_requests_total{{method="{method}",route="{route}",'
                    f'status="{status_class}"}} {n}'
                )
            lines += [
                f"# HELP {HIST} Request latency by route template.",
                f"# TYPE {HIST} histogram",
            ]
            for route, counts in sorted(self.buckets.items()):
                for bound, n in zip((*map(str, BUCKETS), "+Inf"), counts, strict=True):
                    lines.append(f'{HIST}_bucket{{route="{route}",le="{bound}"}} {n}')
                lines.append(f'{HIST}_sum{{route="{route}"}} {self.sums[route]:.6f}')
                lines.append(f'{HIST}_count{{route="{route}"}} {counts[-1]}')
        return lines

    def reset(self) -> None:
        with self._lock:
            self.requests.clear()
            self.buckets.clear()
            self.sums.clear()


http_metrics = HttpMetrics()
