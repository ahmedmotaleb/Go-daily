"""Password hashing and session token primitives.

- Passwords: Argon2id (argon2-cffi defaults, RFC 9106 profile).
- Session tokens: 256-bit random, prefixed `gd_` so leaked tokens are
  recognisable by secret scanners. Only a SHA-256 digest is stored.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

TOKEN_PREFIX = "gd_"  # noqa: S105 - a public prefix, not a secret

# Used to equalise timing when the account does not exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-ish time verification; also burns time when no hash exists."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def generate_session_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def password_problems(password: str, *, phone: str | None = None) -> list[str]:
    """Return Arabic descriptions of policy violations (empty when acceptable)."""
    problems: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"كلمة المرور يجب ألا تقل عن {PASSWORD_MIN_LENGTH} أحرف")
    if len(password) > PASSWORD_MAX_LENGTH:
        problems.append(f"كلمة المرور يجب ألا تزيد عن {PASSWORD_MAX_LENGTH} حرفًا")
    if password.strip() != password:
        problems.append("كلمة المرور لا يجب أن تبدأ أو تنتهي بمسافة")
    if phone and phone in password:
        problems.append("كلمة المرور لا يجب أن تحتوي على رقم الهاتف")
    if len(set(password)) < 4:
        problems.append("كلمة المرور ضعيفة جدًا")
    return problems
