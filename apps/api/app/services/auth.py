"""Authentication use cases: login, session validation, logout, password change.

Session strategy (see docs/ARCHITECTURE.md -> Authentication):
opaque random bearer tokens; the database stores only their SHA-256.
Sessions expire absolutely (per client type) and, for web sessions, after
an idle period. Revocation is immediate (logout, deactivation, password
change).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.errors import (
    AuthenticationError,
    PermissionDenied,
    TooManyRequests,
    ValidationFailed,
)
from app.core.permissions import STAFF_ROLES, UserRole
from app.core.phone import InvalidPhoneError, mask_phone, normalize_phone
from app.core.request_context import get_request_context
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    password_problems,
    verify_password,
)
from app.core.time import utcnow
from app.models.user import AuthSession, ClientType, User
from app.services import audit

INVALID_CREDENTIALS = "رقم الهاتف أو كلمة المرور غير صحيحة"
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True)
class LoginResult:
    token: str
    session: AuthSession
    user: User


def _client_allowed(role: UserRole, client: ClientType) -> bool:
    # The admin web is for staff; the driver app is for drivers.
    if client is ClientType.WEB:
        return role in STAFF_ROLES
    return role is UserRole.DRIVER


def login(
    db: Session,
    *,
    phone: str,
    password: str,
    client: ClientType,
    device_name: str | None = None,
) -> LoginResult:
    settings = get_settings()
    now = utcnow()

    try:
        normalised = normalize_phone(phone)
    except InvalidPhoneError:
        normalised = None

    user = (
        db.scalar(
            select(User)
            .where(User.phone == normalised)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if normalised
        else None
    )

    if user is not None and user.locked_until is not None and user.locked_until > now:
        retry_after = int((user.locked_until - now).total_seconds()) + 1
        audit.record(
            db, action="auth.login.locked", actor=None, entity_type="user", entity_id=user.id
        )
        db.commit()
        raise TooManyRequests(
            "تم إيقاف تسجيل الدخول مؤقتًا بسبب محاولات خاطئة متكررة",
            code="account_locked",
            details={"retry_after_seconds": retry_after},
        )

    if not verify_password(user.password_hash if user else None, password):
        if user is not None:
            user.failed_login_count += 1
            locked = user.failed_login_count >= settings.login_max_failed_attempts
            if locked:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_count = 0
            audit.record(
                db,
                action="auth.login.failed",
                actor=None,
                entity_type="user",
                entity_id=user.id,
                details={"locked": locked},
            )
        else:
            audit.record(
                db,
                action="auth.login.failed",
                actor=None,
                details={"phone": mask_phone(normalised or phone[:20]), "unknown_account": True},
            )
        db.commit()
        raise AuthenticationError(INVALID_CREDENTIALS, code="invalid_credentials")

    if user is None:  # unreachable: verify_password() is False without a hash
        raise AuthenticationError(INVALID_CREDENTIALS, code="invalid_credentials")

    if not user.is_active:
        audit.record(
            db, action="auth.login.inactive", actor=None, entity_type="user", entity_id=user.id
        )
        db.commit()
        raise PermissionDenied("هذا الحساب غير مفعل، تواصل مع الإدارة", code="account_inactive")

    if not _client_allowed(user.role, client):
        audit.record(
            db,
            action="auth.login.client_not_allowed",
            actor=None,
            entity_type="user",
            entity_id=user.id,
            details={"client": client.value},
        )
        db.commit()
        message = (
            "حسابات السائقين تستخدم تطبيق السائق فقط"
            if client is ClientType.WEB
            else "تطبيق السائق مخصص لحسابات السائقين فقط"
        )
        raise PermissionDenied(message, code="client_not_allowed")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    ttl_hours = (
        settings.session_ttl_hours_admin
        if client is ClientType.WEB
        else settings.session_ttl_hours_driver
    )
    ctx = get_request_context()
    token = generate_session_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        client_type=client,
        device_name=device_name,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    db.add(session)
    db.flush()
    audit.record(
        db,
        action="auth.login.success",
        actor=user,
        entity_type="auth_session",
        entity_id=session.id,
        details={"client": client.value},
    )
    db.commit()
    return LoginResult(token=token, session=session, user=user)


def authenticate(db: Session, token: str) -> AuthSession:
    """Resolve a bearer token to a live session, or raise AuthenticationError."""
    settings = get_settings()
    now = utcnow()
    session = db.scalar(
        select(AuthSession)
        .options(joinedload(AuthSession.user))
        .where(AuthSession.token_hash == hash_token(token))
    )
    if session is None or session.revoked_at is not None:
        raise AuthenticationError(code="invalid_session")
    if session.expires_at <= now:
        raise AuthenticationError("انتهت الجلسة، سجّل الدخول مرة أخرى", code="session_expired")
    idle_limit = timedelta(hours=settings.session_idle_timeout_hours)
    if session.client_type is ClientType.WEB and session.last_used_at + idle_limit <= now:
        session.revoked_at = now
        session.revoke_reason = "idle_timeout"
        db.commit()
        raise AuthenticationError("انتهت الجلسة، سجّل الدخول مرة أخرى", code="session_expired")
    if not session.user.is_active:
        raise AuthenticationError("هذا الحساب غير مفعل", code="account_inactive")

    if now - session.last_used_at >= SESSION_TOUCH_INTERVAL:
        db.execute(update(AuthSession).where(AuthSession.id == session.id).values(last_used_at=now))
        session.last_used_at = now
        db.commit()
    return session


def logout(db: Session, session: AuthSession) -> None:
    if session.revoked_at is None:
        session.revoked_at = utcnow()
        session.revoke_reason = "logout"
    audit.record(
        db,
        action="auth.logout",
        actor=session.user,
        entity_type="auth_session",
        entity_id=session.id,
    )
    db.commit()


def revoke_user_sessions(
    db: Session, user_id: uuid.UUID, *, reason: str, except_session_id: uuid.UUID | None = None
) -> int:
    stmt = (
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow(), revoke_reason=reason)
    )
    if except_session_id is not None:
        stmt = stmt.where(AuthSession.id != except_session_id)
    result = db.execute(stmt)
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def validate_new_password(password: str, *, phone: str | None) -> None:
    problems = password_problems(password, phone=phone)
    if problems:
        raise ValidationFailed(problems[0], code="weak_password", details={"problems": problems})


def change_password(
    db: Session, *, session: AuthSession, current_password: str, new_password: str
) -> None:
    user = session.user
    if not verify_password(user.password_hash, current_password):
        audit.record(
            db,
            action="auth.password_change.failed",
            actor=user,
            entity_type="user",
            entity_id=user.id,
        )
        db.commit()
        raise ValidationFailed("كلمة المرور الحالية غير صحيحة", code="invalid_current_password")
    validate_new_password(new_password, phone=user.phone)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    revoked = revoke_user_sessions(
        db, user.id, reason="password_changed", except_session_id=session.id
    )
    audit.record(
        db,
        action="auth.password_changed",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        details={"other_sessions_revoked": revoked},
    )
    db.commit()
