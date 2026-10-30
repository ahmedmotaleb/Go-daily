"""ORM models. Import every model module here so Alembic sees all tables."""

from app.models.assignment import AssignmentRole, DriverVehicleAssignment
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.driver import CompensationMethod, Driver, DriverCompensationPlan, EmploymentStatus
from app.models.fleet import OwnershipStatus, Vehicle, VehicleType
from app.models.operations import (
    OperationKind,
    OperationType,
    RouteDefinition,
    RouteStop,
    StopKind,
    TripPattern,
)
from app.models.shift import OperationSession, SessionStatus, Shift, ShiftSource, ShiftStatus
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
    "OperationKind",
    "OperationSession",
    "OperationType",
    "OwnershipStatus",
    "RouteDefinition",
    "RouteStop",
    "SessionStatus",
    "Shift",
    "ShiftSource",
    "ShiftStatus",
    "StopKind",
    "TripPattern",
    "User",
    "Vehicle",
    "VehicleType",
]
