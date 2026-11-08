"""Distributed rate limits (U32): shared across workers, safe when the store fails."""

from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.orm import Session

from app.api.routes import auth as auth_routes
from app.core import ratelimit
from app.core.permissions import UserRole
from tests.factories import login_as


def test_workers_share_one_count() -> None:
    server = fakeredis.FakeServer()
    worker_a = ratelimit.RedisWindowLimiter(fakeredis.FakeRedis(server=server), "login", 3, 60)
    worker_b = ratelimit.RedisWindowLimiter(fakeredis.FakeRedis(server=server), "login", 3, 60)
    assert worker_a.hit("10.0.0.1", now=1000) is None
    assert worker_b.hit("10.0.0.1", now=1001) is None
    assert worker_a.hit("10.0.0.1", now=1002) is None
    # The fourth attempt is refused whichever worker receives it.
    wait = worker_b.hit("10.0.0.1", now=1003)
    assert wait is not None and 1 <= wait <= 60
    # Another client is not affected, and a new window starts fresh.
    assert worker_a.hit("10.0.0.2", now=1003) is None
    assert worker_a.hit("10.0.0.1", now=1080) is None
    # Keys are hashed: the IP itself is never stored.
    keys = [k.decode() for k in fakeredis.FakeRedis(server=server).keys("*")]
    assert keys and all("10.0.0" not in k for k in keys)


class _Down:
    def pipeline(self) -> _Down:
        raise RedisConnectionError("store down")


def test_store_failure_falls_back_to_local_limits() -> None:
    before = ratelimit.backend_errors.count
    limiter = ratelimit.ResilientLimiter(
        ratelimit.RedisWindowLimiter(_Down(), "login", 2, 60),
        ratelimit.SlidingWindowLimiter(2, 60),
    )
    assert limiter.hit("1.2.3.4") is None
    assert limiter.hit("1.2.3.4") is None
    # Still limited (per process), never switched off.
    assert limiter.hit("1.2.3.4") is not None
    assert ratelimit.backend_errors.count == before + 3


def test_sensitive_actions_are_limited_per_user(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_routes.sensitive_limiter, "limit", 2)
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    body = {"current_password": "wrong-password", "new_password": "Another-pass-2026"}
    codes = [
        client.post("/api/v1/auth/change-password", headers=h, json=body).status_code
        for _ in range(3)
    ]
    assert codes[:2] != [429, 429] and codes[2] == 429
    # Another user is not affected.
    _, other = login_as(client, db, UserRole.ACCOUNTANT)
    assert client.post("/api/v1/auth/change-password", headers=other, json=body).status_code != 429


def test_build_without_redis_is_local() -> None:
    assert isinstance(ratelimit.build("x", 1, 1, None), ratelimit.SlidingWindowLimiter)
    shared = ratelimit.build("x", 1, 1, "redis://localhost:1/0")
    assert isinstance(shared, ratelimit.ResilientLimiter)
