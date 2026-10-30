"""Application settings loaded from environment variables.

All configuration comes from the environment (or a local `.env` file in
development). Never hardcode credentials here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Go Daily API"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_timezone: str = "Africa/Cairo"
    app_currency: str = "EGP"

    database_url: str = Field(
        default="postgresql+psycopg://godaily:godaily@localhost:5432/godaily",
        description="SQLAlchemy URL. Use the psycopg (v3) driver.",
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_echo: bool = False

    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:3000"

    log_level: str = "INFO"
    log_json: bool = True

    # Opaque session tokens (see docs/ARCHITECTURE.md -> Authentication).
    session_ttl_hours_admin: int = 12
    session_ttl_hours_driver: int = 24 * 30
    session_idle_timeout_hours: int = 72
    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15

    # Fernet key (urlsafe base64, 32 bytes) for encrypting sensitive personal
    # data such as national IDs. Required in staging/production.
    data_encryption_key: SecretStr | None = None

    # Show "expiring soon" warnings this many days before a document expires.
    expiry_warning_days: int = 30

    # GPS tracking (see docs/ARCHITECTURE.md -> Tracking).
    gps_max_accuracy_m: float = 100.0
    gps_max_speed_kmh: float = 200.0
    gps_gap_seconds: int = 300
    gps_stop_min_seconds: int = 180
    gps_stop_radius_m: float = 60.0
    tracking_online_seconds: int = 120
    tracking_stale_seconds: int = 600
    gps_retention_days: int = 180
    gps_max_batch_points: int = 500

    # Optional bootstrap admin (used only by `python -m app.cli bootstrap-admin`).
    bootstrap_admin_phone: str | None = None
    bootstrap_admin_password: SecretStr | None = None
    bootstrap_admin_name: str = "مدير النظام"

    @field_validator("database_url")
    @classmethod
    def _normalise_db_url(cls, value: str) -> str:
        # Accept plain postgres URLs (e.g. from hosting providers) and pin the driver.
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
