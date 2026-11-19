"""Time-based one-time passwords (RFC 6238, SHA-1, 6 digits, 30 s) for 2FA (U31).

Standard authenticator apps (Google Authenticator, Microsoft Authenticator,
Aegis, ...) read the otpauth:// URI. Secrets are never logged; they are
stored encrypted (see app.services.two_factor).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime
from urllib.parse import quote, urlencode

DIGITS = 6
PERIOD = 30
ISSUER = "Go Daily"


def generate_secret() -> str:
    """160 random bits, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded)


def step_at(moment: datetime) -> int:
    return int(moment.timestamp()) // PERIOD


def code_for(secret: str, step: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def verify(
    secret: str, code: str, *, at: datetime, last_step: int | None, window: int = 1
) -> int | None:
    """The matching time step, or None.

    Accepts one step of clock drift either way. A step already used (or an
    older one) is refused, so an observed code cannot be replayed.
    """
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return None
    now = step_at(at)
    for step in range(now - window, now + window + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(code_for(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, account: str) -> str:
    label = quote(f"{ISSUER}:{account}")
    query = urlencode(
        {"secret": secret, "issuer": ISSUER, "digits": DIGITS, "period": PERIOD},
    )
    return f"otpauth://totp/{label}?{query}"


__all__ = ["code_for", "generate_secret", "provisioning_uri", "step_at", "verify"]
