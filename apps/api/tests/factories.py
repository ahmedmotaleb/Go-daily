"""Test data helpers. Only used by tests; never seeds real environments."""

from __future__ import annotations

import itertools
import uuid
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.security import hash_password
from app.core.text import plate_key
from app.core.time import local_day_bounds_utc, utcnow
from app.models.assignment import DriverVehicleAssignment
from app.models.driver import (
    CompensationMethod,
    Driver,
    DriverCompensationPlan,
    EmploymentStatus,
)
from app.models.finance import ExpenseCategory, FuelType, RideHailingPlatform
from app.models.fleet import Vehicle, VehicleType
from app.models.operations import OperationType, RouteDefinition, RouteStop
from app.models.shift import OperationSession, SessionStatus, Shift, ShiftStatus
from app.models.user import User

DEFAULT_PASSWORD = "Str0ng-pass-123"
_phone_seq = itertools.count(10_000_000)


def next_phone() -> str:
    return f"010{next(_phone_seq):08d}"


def make_user(
    db: Session,
    *,
    role: UserRole = UserRole.ADMIN,
    phone: str | None = None,
    password: str = DEFAULT_PASSWORD,
    full_name: str = "مستخدم تجريبي",
    is_active: bool = True,
) -> User:
    user = User(
        full_name=full_name,
        phone=phone or next_phone(),
        role=role,
        password_hash=hash_password(password),
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    return user


def login(
    client: TestClient,
    user: User,
    *,
    password: str = DEFAULT_PASSWORD,
    app_client: str | None = None,
) -> str:
    kind = app_client or ("mobile" if user.role is UserRole.DRIVER else "web")
    res = client.post(
        "/api/v1/auth/login", json={"phone": user.phone, "password": password, "client": kind}
    )
    assert res.status_code == 200, res.text
    token: str = res.json()["access_token"]
    return token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login_as(client: TestClient, db: Session, role: UserRole) -> tuple[User, dict[str, str]]:
    user = make_user(db, role=role)
    return user, auth(login(client, user))


_code_seq = itertools.count(1)


def vehicle_type_id(db: Session, code: str = "MICROBUS") -> str:
    vt = db.scalar(select(VehicleType).where(VehicleType.code == code))
    assert vt is not None
    return str(vt.id)


def make_vehicle(db: Session, **overrides: object) -> Vehicle:
    n = next(_code_seq)
    plate = str(overrides.pop("plate_number", f"ق ط ر {1000 + n}"))
    values: dict[str, object] = {
        "internal_code": f"GD-{n:04d}",
        "plate_number": plate,
        "plate_key": plate_key(plate),
        "vehicle_type_id": db.scalar(select(VehicleType.id).where(VehicleType.code == "MICROBUS")),
        "is_active": True,
        "current_odometer_km": 100_000,
    }
    values.update(overrides)
    vehicle = Vehicle(**values)
    db.add(vehicle)
    db.commit()
    return vehicle


def make_driver(db: Session, **overrides: object) -> Driver:
    values: dict[str, object] = {
        "full_name": "سائق تجريبي",
        "phone": next_phone(),
        "employment_status": EmploymentStatus.ACTIVE,
    }
    values.update(overrides)
    driver = Driver(**values)
    db.add(driver)
    db.commit()
    return driver


def operation_type_id(db: Session, code: str = "FIXED_ROUTE") -> str:
    ot = db.scalar(select(OperationType).where(OperationType.code == code))
    assert ot is not None
    return str(ot.id)


def make_route(
    db: Session, *, code: str = "FIXED_ROUTE", name: str = "موقف ⇄ جامعة"
) -> RouteDefinition:
    route = RouteDefinition(
        name=name,
        operation_type_id=uuid.UUID(operation_type_id(db, code)),
        trip_pattern="ROUND_TRIP",
    )
    db.add(route)
    db.commit()
    db.add_all(
        [
            RouteStop(route_id=route.id, sequence=1, kind="ORIGIN", name="الموقف"),
            RouteStop(route_id=route.id, sequence=2, kind="DESTINATION", name="الجامعة"),
        ]
    )
    db.commit()
    return route


def assign(
    db: Session, driver: Driver, vehicle: Vehicle, role: str = "PRIMARY"
) -> DriverVehicleAssignment:
    a = DriverVehicleAssignment(
        driver_id=driver.id,
        vehicle_id=vehicle.id,
        role=role,
        starts_at=utcnow() - timedelta(days=30),
    )
    db.add(a)
    db.commit()
    return a


def make_driver_account(
    client: TestClient, db: Session, *, vehicle: Vehicle | None = None
) -> tuple[Driver, User, dict[str, str], Vehicle]:
    """A driver with an app account, assigned to a vehicle, logged in on mobile."""
    user = make_user(db, role=UserRole.DRIVER)
    driver = make_driver(db, user_id=user.id, phone=user.phone)
    vehicle = vehicle or make_vehicle(db, current_odometer_km=50_000)
    assign(db, driver, vehicle)
    return driver, user, auth(login(client, user)), vehicle


def local_noon(day: date) -> datetime:
    """08:00 local time on `day`, as a UTC instant (safe inside the business day)."""
    return local_day_bounds_utc(day)[0] + timedelta(hours=8)


def make_completed_shift(
    db: Session,
    driver: Driver,
    vehicle: Vehicle,
    *,
    day: date,
    minutes: int = 480,
    start_odometer_km: int | None = 1_000,
    end_odometer_km: int | None = 1_100,
    operation_code: str | None = "FIXED_ROUTE",
) -> Shift:
    """A finished shift (and one operation session) inserted directly."""
    started = local_noon(day)
    ended = started + timedelta(minutes=minutes)
    shift = Shift(
        driver_id=driver.id,
        vehicle_id=vehicle.id,
        status=ShiftStatus.COMPLETED,
        started_at=started,
        ended_at=ended,
        start_odometer_km=start_odometer_km,
        end_odometer_km=end_odometer_km,
    )
    db.add(shift)
    db.flush()
    if operation_code:
        db.add(
            OperationSession(
                shift_id=shift.id,
                operation_type_id=uuid.UUID(operation_type_id(db, operation_code)),
                status=SessionStatus.COMPLETED,
                started_at=started,
                ended_at=ended,
            )
        )
    db.commit()
    return shift


def make_plan(
    db: Session,
    driver: Driver,
    method: CompensationMethod,
    *,
    effective_from: date,
    effective_to: date | None = None,
    **amounts: object,
) -> DriverCompensationPlan:
    plan = DriverCompensationPlan(
        driver_id=driver.id,
        method=method,
        effective_from=effective_from,
        effective_to=effective_to,
        **amounts,
    )
    db.add(plan)
    db.commit()
    return plan


def make_platform(db: Session, name: str | None = None) -> RideHailingPlatform:
    platform = RideHailingPlatform(name=name or f"منصة {next(_code_seq)}")
    db.add(platform)
    db.commit()
    return platform


def fuel_type_id(db: Session, code: str) -> str:
    return str(db.scalar(select(FuelType.id).where(FuelType.code == code)))


def expense_category_id(db: Session, code: str) -> str:
    return str(db.scalar(select(ExpenseCategory.id).where(ExpenseCategory.code == code)))
