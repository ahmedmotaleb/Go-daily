"""Observability (Task 27): readiness, metrics, error reporting."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.api.routes import health
from app.core import monitoring
from app.core.config import get_settings
from app.core.metrics import http_metrics
from app.core.permissions import UserRole
from app.services import exception_rules
from app.services import exceptions as exception_service
from tests.factories import login_as


@pytest.fixture()
def reported() -> Iterator[list[tuple[BaseException, dict[str, Any]]]]:
    seen: list[tuple[BaseException, dict[str, Any]]] = []
    monitoring.register(lambda exc, ctx: seen.append((exc, ctx)))
    try:
        yield seen
    finally:
        monitoring.clear()


def test_ready_checks_database_and_migrations(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    res = client.get("/ready")
    assert res.status_code == 200
    assert res.json()["checks"] == {"database": "ok", "migrations": "ok"}

    monkeypatch.setattr(health, "expected_revision", lambda: "9999_newer_than_db")
    res = client.get("/ready")
    assert res.status_code == 503
    assert res.json()["checks"]["migrations"] == "pending"


def test_metrics_disabled_without_token(client: TestClient) -> None:
    assert get_settings().metrics_token is None
    assert client.get("/metrics").status_code == 404


def test_metrics_with_token(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "metrics_token", SecretStr("scrape-secret"))
    http_metrics.reset()
    _, h = login_as(client, db, UserRole.ADMIN)
    missing = uuid.uuid4()
    assert client.get(f"/api/v1/fuel/{missing}", headers=h).status_code == 404

    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 404
    res = client.get("/metrics", headers={"Authorization": "Bearer scrape-secret"})
    assert res.status_code == 200
    body = res.text
    # Route templates, never raw ids, so label values stay bounded.
    assert 'route="/api/v1/fuel/{tx_id}",status="4xx"' in body
    assert str(missing) not in body
    for gauge in (
        "godaily_active_shifts",
        'godaily_tracking_vehicles{state="OFFLINE"}',
        "godaily_gps_points_received_5m",
        'godaily_open_exceptions{severity="HIGH"}',
        "godaily_pending_financial_reviews",
    ):
        assert gauge in body
    assert "godaily_http_request_duration_seconds_bucket" in body


def test_unhandled_errors_reach_the_reporter_without_leaking(
    client: TestClient, db: Session, reported: list[tuple[BaseException, dict[str, Any]]]
) -> None:
    app = client.app

    def boom() -> None:
        raise RuntimeError("internal detail")

    app.add_api_route("/api/v1/_boom", boom, methods=["GET"])  # type: ignore[attr-defined]
    with TestClient(app, raise_server_exceptions=False) as c:
        res = c.get("/api/v1/_boom", headers={"X-Request-ID": "trace-123"})
    assert res.status_code == 500
    assert "internal detail" not in res.text
    assert res.headers["x-request-id"] == "trace-123"
    [(exc, ctx)] = reported
    assert isinstance(exc, RuntimeError)
    assert ctx == {"component": "api", "path": "/api/v1/_boom", "request_id": "trace-123"}


def test_failing_reporter_never_breaks_the_app(client: TestClient) -> None:
    def broken(exc: BaseException, ctx: dict[str, Any]) -> None:
        raise ValueError("reporter down")

    monitoring.register(broken)
    try:
        monitoring.capture_exception(RuntimeError("x"), component="test")
    finally:
        monitoring.clear()


def test_failing_rule_is_reported(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    reported: list[tuple[BaseException, dict[str, Any]]],
) -> None:
    def broken_rule(ctx: exception_rules.Context) -> exception_rules.RuleResult:
        raise RuntimeError("rule bug")

    info = exception_rules.RuleInfo("BROKEN", "قاعدة معطلة", "", exception_rules.R)
    monkeypatch.setattr(exception_service, "RULES", [(info, broken_rule)])
    exception_service.run_detection(db, actor=None, trigger="cli", days=1)
    [(exc, ctx)] = reported
    assert str(exc) == "rule bug"
    assert ctx == {"component": "exception_rule", "name": "BROKEN"}


def test_log_filter_keeps_an_explicit_request_id() -> None:
    import logging

    from app.core.logging import RequestIdFilter

    record = logging.LogRecord("t", logging.ERROR, __file__, 1, "x", (), None)
    record.request_id = "trace-9"
    RequestIdFilter().filter(record)
    assert getattr(record, "request_id", None) == "trace-9"
    plain = logging.LogRecord("t", logging.INFO, __file__, 1, "x", (), None)
    RequestIdFilter().filter(plain)
    assert getattr(plain, "request_id", None) == "-"


def test_production_refuses_to_start_without_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import crypto
    from app.main import create_app

    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(get_settings(), "data_encryption_key", None)
    crypto._key.cache_clear()
    try:
        with pytest.raises(crypto.EncryptionNotConfigured):
            create_app()
    finally:
        crypto._key.cache_clear()


def test_empty_environment_values_mean_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "")
    monkeypatch.setenv("METRICS_TOKEN", "")
    s = Settings()
    assert s.data_encryption_key is None
    assert s.metrics_token is None
