"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes import health, metrics
from app.core.config import get_settings
from app.core.crypto import check_configured
from app.core.errors import register_error_handlers
from app.core.logging import RequestContextMiddleware, configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    # Refuse to start (rather than fail on first use) without the encryption key.
    check_configured()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        # Interactive docs are disabled in production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(api_router)
    return app


app = create_app()
