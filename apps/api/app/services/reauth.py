"""Re-authentication for sensitive actions (U35).

A sensitive action needs the user to have logged in, or re-confirmed their
password (and two-factor code when enabled), within REAUTH_WINDOW_MINUTES.
Sensitive: creating users, changing roles or account status, password and
2FA resets for others, company policy changes, and finalizing settlements
of at least REAUTH_SETTLEMENT_AMOUNT. Every re-confirmation is audited.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import PermissionDenied, field_error
from app.core.security import verify_password
from app.core.time import utcnow
from app.models.user import AuthSession
from app.services import audit, two_factor


class ReauthRequired(PermissionDenied):
    code = "reauth_required"
    default_message = "أكّد كلمة المرور (ورمز التحقق) للمتابعة في هذا الإجراء الحساس"


def last_confirmed(session: AuthSession) -> datetime:
    return max(session.created_at, session.reauthenticated_at or session.created_at)


def is_recent(session: AuthSession, *, now: datetime | None = None) -> bool:
    window = timedelta(minutes=get_settings().reauth_window_minutes)
    return last_confirmed(session) >= (now or utcnow()) - window


def require(session: AuthSession) -> None:
    if not is_recent(session):
        raise ReauthRequired(details={"window_minutes": get_settings().reauth_window_minutes})


def require_for_amount(session: AuthSession, amount: Decimal) -> None:
    if abs(amount) >= get_settings().reauth_settlement_amount:
        require(session)


def confirm(db: Session, *, session: AuthSession, password: str, code: str | None) -> None:
    user = session.user
    if not verify_password(user.password_hash, password):
        audit.record(
            db, action="auth.reauth.failed", actor=user, entity_type="user", entity_id=user.id
        )
        db.commit()
        raise field_error("password", "كلمة المرور غير صحيحة")
    if two_factor.enabled(user) and two_factor.check_code(db, user, code or "") is None:
        audit.record(
            db, action="auth.reauth.failed", actor=user, entity_type="user", entity_id=user.id
        )
        db.commit()
        raise field_error("code", "رمز التحقق غير صحيح")
    session.reauthenticated_at = utcnow()
    audit.record(
        db, action="auth.reauth", actor=user, entity_type="auth_session", entity_id=session.id
    )
    db.commit()


__all__ = [
    "ReauthRequired",
    "confirm",
    "is_recent",
    "last_confirmed",
    "require",
    "require_for_amount",
]
