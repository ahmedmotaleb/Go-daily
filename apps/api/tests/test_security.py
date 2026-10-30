"""Security hardening (Task 25): every route against every role, headers, throttling."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_driver_user
from app.api.routes.auth import login_limiter
from app.core.permissions import ROLE_PERMISSIONS, Permission, UserRole
from app.main import app
from tests.factories import login_as, make_driver_account, make_user

PUBLIC = {("GET", "/health"), ("GET", "/ready"), ("POST", "/api/v1/auth/login")}

# Routes that need a login but no role permission: the service checks access
# itself (own session, own inbox, owning-record rules for files).
AUTHENTICATED_ONLY = {
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/auth/me"),
    ("POST", "/api/v1/auth/change-password"),
    ("POST", "/api/v1/attachments"),
    ("GET", "/api/v1/attachments"),
    ("GET", "/api/v1/attachments/{attachment_id}/content"),
    ("POST", "/api/v1/attachments/{attachment_id}/delete"),
}


def _calls(dependant: Any) -> Iterator[Callable[..., Any]]:
    for dep in dependant.dependencies:
        if dep.call is not None:
            yield dep.call
        yield from _calls(dep)


def _routes() -> list[tuple[str, str, APIRoute]]:
    out = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in sorted(route.methods or ()):
                out.append((method, route.path, route))
    return out


def _required(route: APIRoute) -> set[Permission] | None:
    found = [c for c in _calls(route.dependant) if hasattr(c, "required_permissions")]
    if not found:
        return None
    return {p for c in found for p in c.required_permissions}


def _driver_only(route: APIRoute) -> bool:
    return any(c is get_current_driver_user for c in _calls(route.dependant))


def _fill(path: str) -> str:
    parts = []
    for part in path.split("/"):
        if part.startswith("{") and part.endswith("}"):
            parts.append("daily_operations" if part == "{code}" else str(uuid.uuid4()))
        else:
            parts.append(part)
    return "/".join(parts)


def test_every_route_is_classified() -> None:
    """A new route must declare its permissions (or be consciously listed above)."""
    unclassified = [
        (m, p)
        for m, p, r in _routes()
        if (m, p) not in PUBLIC
        and (m, p) not in AUTHENTICATED_ONLY
        and _required(r) is None
        and not _driver_only(r)
    ]
    assert unclassified == []


def test_nothing_is_reachable_without_login(client: TestClient) -> None:
    for method, path, _ in _routes():
        if (method, path) in PUBLIC:
            continue
        res = client.request(method, _fill(path))
        assert res.status_code == 401, (method, path, res.status_code)


@pytest.mark.parametrize("role", [r for r in UserRole if r is not UserRole.DRIVER])
def test_staff_permissions_are_enforced_on_every_route(
    client: TestClient, db: Session, role: UserRole
) -> None:
    _, h = login_as(client, db, role)
    granted = ROLE_PERMISSIONS[role]
    for method, path, route in _routes():
        url = _fill(path)
        if _driver_only(route):
            assert client.request(method, url, headers=h).status_code == 403, (method, path)
            continue
        required = _required(route)
        if required is None:
            continue
        status = (
            client.request(method, url, headers=h).status_code
            if (not required <= granted or method == "GET")
            else None
        )
        if not required <= granted:
            assert status == 403, (role, method, path, status)
        elif status is not None:
            assert status != 403, (role, method, path)


def test_drivers_reach_only_the_driver_app(client: TestClient, db: Session) -> None:
    _, _, h, _ = make_driver_account(client, db)
    for method, path, route in _routes():
        if (method, path) in PUBLIC or (method, path) in AUTHENTICATED_ONLY:
            continue
        url = _fill(path)
        if _driver_only(route):
            if method == "GET":
                assert client.request(method, url, headers=h).status_code != 403, path
        else:
            assert client.request(method, url, headers=h).status_code == 403, (method, path)


def test_driver_cannot_read_staff_files(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    res = client.get(
        "/api/v1/attachments",
        params={"owner_type": "vehicle", "owner_id": str(vehicle.id)},
        headers=h,
    )
    assert res.status_code == 403


def test_accountant_has_no_live_location_access(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    assert Permission.TRACKING_READ not in ROLE_PERMISSIONS[UserRole.ACCOUNTANT]
    assert client.get("/api/v1/tracking/live", headers=h).status_code == 403


def test_api_responses_carry_security_headers(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ADMIN)
    res = client.get("/api/v1/auth/me", headers=h)
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["cache-control"] == "no-store"
    assert res.headers["referrer-policy"] == "no-referrer"
    assert "strict-transport-security" not in res.headers  # only in production


def test_login_is_throttled_per_client(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(login_limiter, "limit", 3)
    user = make_user(db, role=UserRole.ADMIN)
    for _ in range(3):
        res = client.post(
            "/api/v1/auth/login",
            json={"phone": user.phone, "password": "wrong-password-1", "client": "web"},
        )
        assert res.status_code == 401
    res = client.post(
        "/api/v1/auth/login",
        json={"phone": user.phone, "password": "wrong-password-1", "client": "web"},
    )
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "rate_limited"
    assert res.json()["error"]["details"]["retry_after_seconds"] >= 1


def test_limiter_window_expires() -> None:
    from app.core.ratelimit import SlidingWindowLimiter

    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    assert limiter.hit("a", now=0) is None
    assert limiter.hit("a", now=1) is None
    assert limiter.hit("a", now=2) == 59
    assert limiter.hit("b", now=2) is None  # other clients are unaffected
    assert limiter.hit("a", now=61) is None  # first attempt left the window


def test_validation_errors_do_not_echo_input(client: TestClient) -> None:
    res = client.post(
        "/api/v1/auth/login",
        json={"phone": "x", "password": "secret-value-123", "client": "bogus"},
    )
    assert res.status_code == 422
    assert "secret-value-123" not in res.text


def test_logs_scrub_sensitive_and_personal_fields() -> None:
    import json
    import logging

    from app.core.logging import JsonFormatter

    record = logging.LogRecord("t", logging.INFO, __file__, 1, "event", (), None)
    record.__dict__.update(
        {
            "password": "p@ss",
            "token": "abc",
            "phone": "01012345678",
            "latitude": 30.1,
            "nested": {"national_id": "29001011234567", "kind": "ok"},
        }
    )
    line = json.loads(JsonFormatter().format(record))
    blob = json.dumps(line, ensure_ascii=False)
    for secret in ("p@ss", "abc", "01012345678", "30.1", "29001011234567"):
        assert secret not in blob
    assert line["nested"]["kind"] == "ok"
