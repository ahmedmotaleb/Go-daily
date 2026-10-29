"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

engine: Engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_size=_settings.database_pool_size,
    max_overflow=_settings.database_max_overflow,
    echo=_settings.database_echo,
    # Store and compare timestamps in UTC regardless of server configuration.
    connect_args={"options": "-c timezone=UTC"},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session. Services commit explicitly."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database(db: Session) -> None:
    """Raise if the database is not reachable."""
    db.execute(text("SELECT 1"))
