"""Test fixtures.

Tests run against a real PostgreSQL database (the schema relies on
PostgreSQL features). The schema is built by running the Alembic
migrations, so every test run also verifies the migration chain.

Each test runs inside a transaction that is rolled back afterwards;
service-level commits become savepoint releases.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

API_ROOT = Path(__file__).resolve().parents[1]
_dotenv = {**dotenv_values(API_ROOT.parents[1] / ".env"), **dotenv_values(API_ROOT / ".env")}

# Must be set before the application modules are imported.
TEST_DATABASE_URL = (
    os.environ.get("TEST_DATABASE_URL")
    or _dotenv.get("TEST_DATABASE_URL")
    or "postgresql+psycopg://godaily:godaily@localhost:5432/godaily_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["APP_ENV"] = "test"
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.routes.auth import login_limiter  # noqa: E402
from app.core.db import engine, get_db  # noqa: E402
from app.core.storage import LocalStorage  # noqa: E402
from app.main import create_app  # noqa: E402


def _alembic_config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> Iterator[None]:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(_alembic_config(), "head")
    yield


@pytest.fixture()
def connection() -> Iterator[Connection]:
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


@pytest.fixture()
def db(connection: Connection) -> Iterator[Session]:
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    app = create_app()

    def _get_db() -> Iterator[Session]:
        # Production closes the session after each request, discarding anything
        # a failed request flushed but never committed. Mirror that here.
        try:
            yield db
        finally:
            db.rollback()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalStorage:
    """Attachments go to a per-test temporary directory, never ./var."""
    storage = LocalStorage(tmp_path / "attachments")
    monkeypatch.setattr("app.services.attachments.get_storage", lambda: storage)
    return storage


@pytest.fixture(autouse=True)
def _fresh_login_limiter() -> None:
    """The per-IP login limiter is process-wide; each test starts with a clean slate."""
    login_limiter.reset()
