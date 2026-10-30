"""Liveness and readiness probes."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import check_database, get_db

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health", summary="Liveness probe")
def health() -> dict[str, str]:
    """Process is up. Does not touch dependencies."""
    return {"status": "ok", "service": get_settings().app_name}


@router.get("/ready", summary="Readiness probe (checks database connectivity)")
def ready(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        check_database(db)
    except Exception:
        logger.warning("readiness_db_unavailable", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "checks": {"database": "error"}},
        )
    if not migrations_current(db):
        # Code is newer than the schema: refuse traffic until migrations run.
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unavailable",
                "checks": {"database": "ok", "migrations": "pending"},
            },
        )
    return JSONResponse(
        content={"status": "ready", "checks": {"database": "ok", "migrations": "ok"}}
    )


@lru_cache
def expected_revision() -> str | None:
    """Head revision of the migration scripts shipped with this build."""
    cfg = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def migrations_current(db: Session) -> bool:
    current = db.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    return current is not None and current == expected_revision()
