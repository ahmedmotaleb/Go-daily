"""Test data helpers. Only used by tests; never seeds real environments."""

from __future__ import annotations

import itertools
import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.security import hash_password
from app.core.text import plate_key
from app.core.time import utcnow
from app.models.assignment import DriverVehicleAssignment
from app.models.driver import Driver, EmploymentStatus
from app.models.fleet import Vehicle, VehicleType
from app.models.operations import OperationType, RouteDefinition, RouteStop
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
