"""Liveness and readiness probes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
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
    return JSONResponse(content={"status": "ready", "checks": {"database": "ok"}})
