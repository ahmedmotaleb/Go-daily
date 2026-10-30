"""Request dependencies: database session, authentication and authorization."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AuthenticationError, PermissionDenied
from app.core.permissions import STAFF_ROLES, Permission, UserRole, has_permission
from app.models.driver import Driver, EmploymentStatus
from app.models.user import AuthSession, User
from app.services import auth as auth_service

DbSession = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False, description="Session token from /api/v1/auth/login")


def get_current_session(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthSession:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AuthenticationError()
    return auth_service.authenticate(db, credentials.credentials)


CurrentSession = Annotated[AuthSession, Depends(get_current_session)]


def get_current_user(session: CurrentSession) -> User:
    return session.user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permissions(*permissions: Permission) -> Callable[[User], User]:
    """Dependency factory: the current user must be staff and hold every permission."""

    def _dependency(user: CurrentUser) -> User:
        if user.role not in STAFF_ROLES:
            raise PermissionDenied()
        missing = [p for p in permissions if not has_permission(user.role, p)]
        if missing:
            raise PermissionDenied(details={"missing": [p.value for p in missing]})
        return user

    return _dependency


def get_current_driver_user(user: CurrentUser) -> User:
    if user.role is not UserRole.DRIVER:
        raise PermissionDenied("هذه الخدمة مخصصة للسائقين", code="drivers_only")
    return user


CurrentDriverUser = Annotated[User, Depends(get_current_driver_user)]


def get_current_driver(user: CurrentDriverUser, db: DbSession) -> Driver:
    """The Driver profile of the logged-in driver account (must be employed)."""
    driver = db.scalar(select(Driver).where(Driver.user_id == user.id))
    if driver is None:
        raise PermissionDenied("الحساب غير مرتبط بملف سائق", code="no_driver_profile")
    if driver.employment_status is not EmploymentStatus.ACTIVE:
        raise PermissionDenied("ملف السائق غير نشط", code="driver_not_active")
    return driver


CurrentDriver = Annotated[Driver, Depends(get_current_driver)]
