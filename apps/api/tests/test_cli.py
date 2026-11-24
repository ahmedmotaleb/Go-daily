from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cli
from app.core.config import get_settings
from app.core.permissions import UserRole
from app.models.user import User


@pytest.fixture()
def cli_db(db: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    @contextmanager
    def _session() -> Iterator[Session]:
        yield db

    monkeypatch.setattr(cli, "SessionLocal", _session)
    return db


def _set_bootstrap_env(monkeypatch: pytest.MonkeyPatch, phone: str, password: str) -> None:
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PHONE", phone)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", password)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_settings() -> Iterator[None]:
    yield
    get_settings.cache_clear()


def test_bootstrap_admin_requires_env(cli_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PHONE", raising=False)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    get_settings.cache_clear()
    assert cli.main(["bootstrap-admin"]) == 2


def test_bootstrap_admin_creates_once(cli_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_bootstrap_env(monkeypatch, "+201000000001", "Very-secure-boot-1")
    assert cli.main(["bootstrap-admin"]) == 0
    admin = cli_db.scalar(select(User).where(User.phone == "01000000001"))
    assert admin is not None and admin.role is UserRole.SUPER_ADMIN
    assert admin.password_hash.startswith("$argon2id$")

    # A second run is refused.
    _set_bootstrap_env(monkeypatch, "01000000002", "Very-secure-boot-2")
    assert cli.main(["bootstrap-admin"]) == 1


def test_bootstrap_admin_rejects_weak_password(
    cli_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_bootstrap_env(monkeypatch, "01000000003", "123")
    assert cli.main(["bootstrap-admin"]) == 1


def test_seed_runs(cli_db: Session) -> None:
    assert cli.main(["seed"]) == 0
