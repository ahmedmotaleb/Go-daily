"""Two-factor login for staff (U31).

- Setup stores a new TOTP secret encrypted; it only counts once the user
  proves it with a code (enable). Enabling issues 10 one-time recovery
  codes, shown once and stored as SHA-256.
- Turning it off, or issuing new recovery codes, needs the password and a
  current code (re-authentication). An administrator with users:manage can
  reset it for someone who lost their phone; that ends their sessions.
- Every change and every failed or recovery-code login is audited. Secrets
  and codes are never logged or audited.
"""

from __future__ import annotations

import hashlib
import secrets

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import crypto, totp
from app.core.config import get_settings
from app.core.errors import ConflictError, ValidationFailed, field_error
from app.core.permissions import UserRole
from app.core.security import verify_password
from app.core.time import utcnow
from app.models.user import RecoveryCode, User
from app.services import audit

RECOVERY_CODES = 10
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i


def required_for(role: UserRole) -> bool:
    roles = {r.strip() for r in get_settings().twofa_required_roles.split(",") if r.strip()}
    return role.value in roles


def enabled(user: User) -> bool:
    return user.totp_enabled_at is not None and user.totp_secret_enc is not None


def setup_needed(user: User) -> bool:
    """Enforcement is on and this user must turn 2FA on before working."""
    return get_settings().twofa_enforce and required_for(user.role) and not enabled(user)


def _hash(code: str) -> str:
    normalised = code.strip().lower().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalised.encode()).hexdigest()


def _new_codes(db: Session, user: User) -> list[str]:
    db.execute(
        update(RecoveryCode)
        .where(RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None))
        .values(used_at=utcnow())
    )
    codes = []
    for _ in range(RECOVERY_CODES):
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
        db.add(RecoveryCode(user_id=user.id, code_hash=_hash(raw)))
    return codes


def check_code(db: Session, user: User, code: str) -> str | None:
    """'totp' or 'recovery' when the code is valid (and consumed), else None."""
    if not enabled(user) or user.totp_secret_enc is None:
        return None
    secret = crypto.decrypt(user.totp_secret_enc)
    step = totp.verify(secret, code, at=utcnow(), last_step=user.totp_last_step)
    if step is not None:
        user.totp_last_step = step
        return "totp"
    recovery = db.scalar(
        select(RecoveryCode)
        .where(
            RecoveryCode.user_id == user.id,
            RecoveryCode.code_hash == _hash(code),
            RecoveryCode.used_at.is_(None),
        )
        .with_for_update()
    )
    if recovery is not None:
        recovery.used_at = utcnow()
        return "recovery"
    return None


def recovery_left(db: Session, user: User) -> int:
    return len(
        db.scalars(
            select(RecoveryCode.id).where(
                RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)
            )
        ).all()
    )


def setup(db: Session, *, user: User) -> tuple[str, str]:
    """A new secret for enrollment: (secret, otpauth URI). Not active until enabled."""
    if enabled(user):
        raise ConflictError("التحقق بخطوتين مفعل بالفعل", code="twofa_already_enabled")
    secret = totp.generate_secret()
    user.totp_secret_enc = crypto.encrypt(secret)
    user.totp_last_step = None
    audit.record(
        db, action="auth.2fa.setup_started", actor=user, entity_type="user", entity_id=user.id
    )
    db.commit()
    return secret, totp.provisioning_uri(secret, user.phone)


def enable(db: Session, *, user: User, code: str) -> list[str]:
    if enabled(user):
        raise ConflictError("التحقق بخطوتين مفعل بالفعل", code="twofa_already_enabled")
    if user.totp_secret_enc is None:
        raise ConflictError("ابدأ الإعداد أولًا", code="twofa_setup_missing")
    secret = crypto.decrypt(user.totp_secret_enc)
    step = totp.verify(secret, code, at=utcnow(), last_step=None)
    if step is None:
        raise field_error("code", "الرمز غير صحيح، تأكد من وقت الهاتف وحاول مرة أخرى")
    user.totp_last_step = step
    user.totp_enabled_at = utcnow()
    codes = _new_codes(db, user)
    audit.record(db, action="auth.2fa.enabled", actor=user, entity_type="user", entity_id=user.id)
    db.commit()
    return codes


def _reauthenticate(db: Session, user: User, password: str, code: str) -> None:
    if not verify_password(user.password_hash, password):
        raise field_error("password", "كلمة المرور غير صحيحة")
    if check_code(db, user, code) is None:
        raise field_error("code", "الرمز غير صحيح")


def disable(db: Session, *, user: User, password: str, code: str) -> None:
    if not enabled(user):
        raise ConflictError("التحقق بخطوتين غير مفعل", code="twofa_not_enabled")
    if setup_needed_after_off(user):
        raise ValidationFailed(
            "التحقق بخطوتين إلزامي لصلاحيتك ولا يمكن إيقافه", code="twofa_required"
        )
    _reauthenticate(db, user, password, code)
    _clear(db, user)
    audit.record(db, action="auth.2fa.disabled", actor=user, entity_type="user", entity_id=user.id)
    db.commit()


def setup_needed_after_off(user: User) -> bool:
    return get_settings().twofa_enforce and required_for(user.role)


def regenerate_codes(db: Session, *, user: User, password: str, code: str) -> list[str]:
    if not enabled(user):
        raise ConflictError("التحقق بخطوتين غير مفعل", code="twofa_not_enabled")
    _reauthenticate(db, user, password, code)
    codes = _new_codes(db, user)
    audit.record(
        db,
        action="auth.2fa.recovery_codes_renewed",
        actor=user,
        entity_type="user",
        entity_id=user.id,
    )
    db.commit()
    return codes


def _clear(db: Session, user: User) -> None:
    user.totp_secret_enc = None
    user.totp_enabled_at = None
    user.totp_last_step = None
    db.execute(
        update(RecoveryCode)
        .where(RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None))
        .values(used_at=utcnow())
    )


def admin_reset(db: Session, *, actor: User, user: User, reason: str) -> None:
    """For a user who lost their phone and codes; they set it up again at next login."""
    if actor.id == user.id:
        raise ValidationFailed("لا يمكنك إعادة ضبط التحقق بخطوتين لحسابك", code="self_reset")
    if not enabled(user) and user.totp_secret_enc is None:
        raise ConflictError("التحقق بخطوتين غير مفعل لهذا المستخدم", code="twofa_not_enabled")
    _clear(db, user)
    audit.record(
        db,
        action="auth.2fa.reset",
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        reason=reason,
    )


__all__ = [
    "admin_reset",
    "check_code",
    "disable",
    "enable",
    "enabled",
    "recovery_left",
    "regenerate_codes",
    "required_for",
    "setup",
    "setup_needed",
]
