"""User management use cases (staff and driver accounts)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDenied, ValidationFailed
from app.core.permissions import UserRole, can_manage_role
from app.core.security import hash_password
from app.core.time import utcnow
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.user import UserCreate, UserUpdate
from app.services import audit
from app.services.auth import revoke_user_sessions, validate_new_password

AUDITED_FIELDS = ("full_name", "phone", "email", "role", "is_active")


def list_users(
    db: Session,
    params: PageParams,
    *,
    q: str | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> tuple[list[User], int]:
    stmt = select(User)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.phone.ilike(like)))
    if role is not None:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(User.created_at.desc(), User.id).offset(params.offset).limit(params.page_size)
    ).all()
    return list(rows), total


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("المستخدم غير موجود")
    return user


def _ensure_unique(
    db: Session, *, phone: str | None, email: str | None, exclude: uuid.UUID | None = None
) -> None:
    if phone:
        stmt = select(User.id).where(User.phone == phone)
        if exclude:
            stmt = stmt.where(User.id != exclude)
        if db.scalar(stmt) is not None:
            raise ConflictError("رقم الهاتف مسجل لمستخدم آخر", code="phone_taken")
    if email:
        stmt = select(User.id).where(func.lower(User.email) == email.lower())
        if exclude:
            stmt = stmt.where(User.id != exclude)
        if db.scalar(stmt) is not None:
            raise ConflictError("البريد الإلكتروني مسجل لمستخدم آخر", code="email_taken")


def _ensure_can_manage(actor: User, role: UserRole) -> None:
    if not can_manage_role(actor.role, role):
        raise PermissionDenied("لا يمكنك إدارة حسابات بهذه الصلاحية", code="role_not_manageable")


def _active_super_admin_count(db: Session) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.SUPER_ADMIN, User.is_active.is_(True))
        )
        or 0
    )


def ensure_phone_available(db: Session, phone: str, *, exclude: uuid.UUID | None = None) -> None:
    _ensure_unique(db, phone=phone, email=None, exclude=exclude)


def create_user(
    db: Session,
    *,
    actor: User | None,
    data: UserCreate,
    commit: bool = True,
    enforce_role_policy: bool = True,
) -> User:
    """Create an account.

    `actor=None` is only used by the bootstrap CLI. `enforce_role_policy=False`
    is only used for driver app accounts (always role DRIVER), whose caller
    authorizes with `drivers:write`.
    """
    if actor is not None and enforce_role_policy:
        _ensure_can_manage(actor, data.role)
    _ensure_unique(db, phone=data.phone, email=data.email)
    validate_new_password(data.password, phone=data.phone)
    user = User(
        full_name=data.full_name,
        phone=data.phone,
        email=data.email,
        role=data.role,
        is_active=data.is_active,
        password_hash=hash_password(data.password),
        password_changed_at=utcnow(),
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        action="user.created",
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        changes=audit.diff({}, audit.snapshot(user, AUDITED_FIELDS)),
    )
    if commit:
        db.commit()
    return user


def update_user(db: Session, *, actor: User, user_id: uuid.UUID, data: UserUpdate) -> User:
    user = get_user(db, user_id)
    _ensure_can_manage(actor, user.role)
    fields: dict[str, Any] = data.model_dump(exclude_unset=True)

    # `null` is meaningful only for email (clear it); ignore it elsewhere.
    for key in ("full_name", "phone", "role", "is_active"):
        if key in fields and fields[key] is None:
            fields.pop(key)

    new_role = fields.get("role")
    if new_role is not None and new_role != user.role:
        _ensure_can_manage(actor, new_role)
        if user.id == actor.id:
            raise ValidationFailed("لا يمكنك تغيير صلاحيتك بنفسك", code="cannot_change_own_role")

    if fields.get("is_active") is False and user.id == actor.id:
        raise ValidationFailed("لا يمكنك إيقاف حسابك بنفسك", code="cannot_deactivate_self")

    losing_super_admin = (
        user.role is UserRole.SUPER_ADMIN
        and user.is_active
        and (
            fields.get("is_active") is False
            or (new_role is not None and new_role is not UserRole.SUPER_ADMIN)
        )
    )
    if losing_super_admin and _active_super_admin_count(db) <= 1:
        raise ValidationFailed("يجب أن يبقى مدير عام واحد مفعل على الأقل", code="last_super_admin")

    _ensure_unique(
        db,
        phone=fields.get("phone"),
        email=fields.get("email"),
        exclude=user.id,
    )

    before = audit.snapshot(user, AUDITED_FIELDS)
    for key, value in fields.items():
        setattr(user, key, value)
    after = audit.snapshot(user, AUDITED_FIELDS)
    changes = audit.diff(before, after)

    if not changes:
        return user

    revoked = 0
    if before["is_active"] and not user.is_active:
        revoked = revoke_user_sessions(db, user.id, reason="deactivated")
    elif "role" in changes:
        # Permissions changed: force re-login.
        revoked = revoke_user_sessions(db, user.id, reason="role_changed")

    action = "user.updated"
    if set(changes) == {"is_active"}:
        action = "user.activated" if user.is_active else "user.deactivated"
    audit.record(
        db,
        action=action,
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        changes=changes,
        details={"sessions_revoked": revoked} if revoked else None,
    )
    db.commit()
    return user


def reset_password(db: Session, *, actor: User, user_id: uuid.UUID, new_password: str) -> User:
    user = get_user(db, user_id)
    _ensure_can_manage(actor, user.role)
    if user.id == actor.id:
        raise ValidationFailed("استخدم تغيير كلمة المرور من حسابك", code="use_change_password")
    validate_new_password(new_password, phone=user.phone)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    user.failed_login_count = 0
    user.locked_until = None
    revoked = revoke_user_sessions(db, user.id, reason="password_reset")
    audit.record(
        db,
        action="user.password_reset",
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        details={"sessions_revoked": revoked},
    )
    db.commit()
    return user


def bootstrap_super_admin(db: Session, *, full_name: str, phone: str, password: str) -> User:
    if db.scalar(select(User.id).where(User.role == UserRole.SUPER_ADMIN)) is not None:
        raise ConflictError("يوجد مدير عام بالفعل", code="super_admin_exists")
    return create_user(
        db,
        actor=None,
        data=UserCreate(
            full_name=full_name, phone=phone, role=UserRole.SUPER_ADMIN, password=password
        ),
    )
