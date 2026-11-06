from __future__ import annotations

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.main import create_app


def test_health_ok(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_ready_checks_database(client: TestClient) -> None:
    res = client.get("/ready")
    assert res.status_code == 200
    assert res.json() == {"status": "ready", "checks": {"database": "ok", "migrations": "ok"}}


def test_ready_reports_unavailable_database() -> None:
    class BrokenSession:
        def execute(self, *_: object, **__: object) -> None:
            raise ConnectionError("db down")

    app = create_app()

    def _broken() -> Iterator[Session]:
        yield BrokenSession()  # type: ignore[misc]

    app.dependency_overrides[get_db] = _broken
    with TestClient(app) as c:
        res = c.get("/ready")
    assert res.status_code == 503
    assert res.json()["checks"]["database"] == "error"


def test_request_id_is_echoed(client: TestClient) -> None:
    res = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert res.headers["X-Request-ID"] == "abc123"
    generated = client.get("/health").headers["X-Request-ID"]
    assert len(generated) == 32


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    res = client.get("/does-not-exist")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"
