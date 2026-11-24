"""TOTP (RFC 6238) known answers and replay protection."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from app.core import totp

# RFC 6238 appendix B, SHA-1 seed "12345678901234567890" (8-digit values,
# compared on their last 6 digits).
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


def test_rfc_6238_vectors() -> None:
    for ts, expected in ((59, "94287082"), (1111111109, "07081804"), (2000000000, "69279037")):
        assert totp.code_for(RFC_SECRET, ts // 30) == expected[-6:]


def test_verify_drift_and_replay() -> None:
    secret = totp.generate_secret()
    at = datetime(2026, 11, 8, 9, 0, 0, tzinfo=UTC)
    step = totp.step_at(at)
    assert totp.verify(secret, totp.code_for(secret, step), at=at, last_step=None) == step
    # One step early or late is accepted (phone clock drift) ...
    assert totp.verify(secret, totp.code_for(secret, step - 1), at=at, last_step=None) == step - 1
    # ... two steps is not.
    assert totp.verify(secret, totp.code_for(secret, step - 2), at=at, last_step=None) is None
    # A step already used cannot be used again.
    assert totp.verify(secret, totp.code_for(secret, step), at=at, last_step=step) is None
    assert totp.verify(secret, "12 34", at=at, last_step=None) is None
    uri = totp.provisioning_uri(secret, "01000000000")
    assert uri.startswith("otpauth://totp/Go%20Daily%3A01000000000?") and secret in uri
