"""Field-level encryption for sensitive personal data (e.g. national IDs).

- Values are encrypted with Fernet (AES-128-CBC + HMAC-SHA256).
- A keyed HMAC "blind index" allows uniqueness checks and exact lookup
  without decrypting.
- Production must set DATA_ENCRYPTION_KEY. Development and test fall back
  to a fixed, clearly-insecure key so the app runs out of the box.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_DEV_KEY = base64.urlsafe_b64encode(hashlib.sha256(b"go-daily-insecure-dev-key").digest())


class EncryptionNotConfigured(RuntimeError):
    pass


@lru_cache
def _key() -> bytes:
    settings = get_settings()
    if settings.data_encryption_key is not None:
        return settings.data_encryption_key.get_secret_value().encode()
    if settings.app_env in ("development", "test"):
        logger.warning("data_encryption_key_missing_using_dev_key")
        return _DEV_KEY
    raise EncryptionNotConfigured("DATA_ENCRYPTION_KEY must be set outside development/test")


def check_configured() -> None:
    """Fail fast at startup when encryption is not configured."""
    Fernet(_key())


def encrypt(value: str) -> str:
    return Fernet(_key()).encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return Fernet(_key()).decrypt(token.encode()).decode()
    except InvalidToken as exc:  # wrong key or tampered value
        raise EncryptionNotConfigured("Unable to decrypt value with the configured key") from exc


def blind_index(value: str, *, purpose: str) -> str:
    """Deterministic keyed hash for lookups/uniqueness (purpose-separated)."""
    return hmac.new(_key(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def generate_key() -> str:
    return Fernet.generate_key().decode()
