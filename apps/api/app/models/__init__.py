"""ORM models. Import every model module here so Alembic sees all tables."""

from app.models.assignment import AssignmentRole, DriverVehicleAssignment
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.driver import CompensationMethod, Driver, DriverCompensationPlan, EmploymentStatus
from app.models.fleet import OwnershipStatus, Vehicle, VehicleType
from app.models.user import AuthSession, ClientType, User

__all__ = [
    "AssignmentRole",
    "AuditLog",
    "AuthSession",
    "Base",
    "ClientType",
    "CompensationMethod",
    "Driver",
    "DriverCompensationPlan",
    "DriverVehicleAssignment",
    "EmploymentStatus",
    "OwnershipStatus",
    "User",
    "Vehicle",
    "VehicleType",
]
