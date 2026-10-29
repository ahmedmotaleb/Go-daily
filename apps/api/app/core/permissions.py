"""Roles and permissions (backend source of truth for authorization).

Endpoints declare the permission they need; roles map to permission sets.
Drivers do not get admin permissions: they only use `/api/v1/driver/*`
endpoints, which are scoped to their own records.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    OPERATIONS = "OPERATIONS"
    ACCOUNTANT = "ACCOUNTANT"
    DRIVER = "DRIVER"


STAFF_ROLES = frozenset(
    {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATIONS, UserRole.ACCOUNTANT}
)


class Permission(StrEnum):
    USERS_READ = "users:read"
    USERS_MANAGE = "users:manage"
    AUDIT_READ = "audit:read"

    VEHICLES_READ = "vehicles:read"
    VEHICLES_WRITE = "vehicles:write"
    DRIVERS_READ = "drivers:read"
    DRIVERS_WRITE = "drivers:write"
    # National ID and other sensitive driver identity fields.
    DRIVERS_READ_SENSITIVE = "drivers:read_sensitive"
    ASSIGNMENTS_READ = "assignments:read"
    ASSIGNMENTS_WRITE = "assignments:write"

    OPERATIONS_READ = "operations:read"
    OPERATIONS_WRITE = "operations:write"
    SHIFTS_READ = "shifts:read"
    SHIFTS_WRITE = "shifts:write"
    TRACKING_READ = "tracking:read"

    FUEL_READ = "fuel:read"
    FUEL_WRITE = "fuel:write"
    EXPENSES_READ = "expenses:read"
    EXPENSES_WRITE = "expenses:write"
    EXPENSES_APPROVE = "expenses:approve"
    REVENUE_READ = "revenue:read"
    REVENUE_WRITE = "revenue:write"
    SETTLEMENTS_READ = "settlements:read"
    SETTLEMENTS_WRITE = "settlements:write"
    SETTLEMENTS_FINALIZE = "settlements:finalize"
    PROFITABILITY_READ = "profitability:read"

    EXCEPTIONS_READ = "exceptions:read"
    EXCEPTIONS_REVIEW = "exceptions:review"
    MAINTENANCE_READ = "maintenance:read"
    MAINTENANCE_WRITE = "maintenance:write"
    REPORTS_READ = "reports:read"
    NOTIFICATIONS_READ = "notifications:read"
    ATTACHMENTS_READ = "attachments:read"
    ATTACHMENTS_WRITE = "attachments:write"
    SETTINGS_MANAGE = "settings:manage"


P = Permission

_OPERATIONS = frozenset(
    {
        P.VEHICLES_READ,
        P.VEHICLES_WRITE,
        P.DRIVERS_READ,
        P.DRIVERS_WRITE,
        P.ASSIGNMENTS_READ,
        P.ASSIGNMENTS_WRITE,
        P.OPERATIONS_READ,
        P.OPERATIONS_WRITE,
        P.SHIFTS_READ,
        P.SHIFTS_WRITE,
        P.TRACKING_READ,
        P.FUEL_READ,
        P.EXPENSES_READ,
        P.EXCEPTIONS_READ,
        P.EXCEPTIONS_REVIEW,
        P.MAINTENANCE_READ,
        P.MAINTENANCE_WRITE,
        P.REPORTS_READ,
        P.NOTIFICATIONS_READ,
        P.ATTACHMENTS_READ,
        P.ATTACHMENTS_WRITE,
    }
)

_ACCOUNTANT = frozenset(
    {
        P.VEHICLES_READ,
        P.DRIVERS_READ,
        P.ASSIGNMENTS_READ,
        P.OPERATIONS_READ,
        P.SHIFTS_READ,
        P.TRACKING_READ,
        P.FUEL_READ,
        P.FUEL_WRITE,
        P.EXPENSES_READ,
        P.EXPENSES_WRITE,
        P.EXPENSES_APPROVE,
        P.REVENUE_READ,
        P.REVENUE_WRITE,
        P.SETTLEMENTS_READ,
        P.SETTLEMENTS_WRITE,
        P.SETTLEMENTS_FINALIZE,
        P.PROFITABILITY_READ,
        P.EXCEPTIONS_READ,
        P.EXCEPTIONS_REVIEW,
        P.MAINTENANCE_READ,
        P.REPORTS_READ,
        P.NOTIFICATIONS_READ,
        P.ATTACHMENTS_READ,
        P.ATTACHMENTS_WRITE,
    }
)

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.SUPER_ADMIN: frozenset(Permission),
    UserRole.ADMIN: frozenset(Permission),
    UserRole.OPERATIONS: _OPERATIONS,
    UserRole.ACCOUNTANT: _ACCOUNTANT,
    UserRole.DRIVER: frozenset(),
}

# Which roles each role may create/modify through user management.
MANAGEABLE_ROLES: dict[UserRole, frozenset[UserRole]] = {
    UserRole.SUPER_ADMIN: frozenset(UserRole),
    UserRole.ADMIN: frozenset({UserRole.OPERATIONS, UserRole.ACCOUNTANT, UserRole.DRIVER}),
}


def permissions_for(role: UserRole) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: UserRole, permission: Permission) -> bool:
    return permission in permissions_for(role)


def can_manage_role(actor_role: UserRole, target_role: UserRole) -> bool:
    return target_role in MANAGEABLE_ROLES.get(actor_role, frozenset())
