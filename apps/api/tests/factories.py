"""Test data helpers. Only used by tests; never seeds real environments."""

from __future__ import annotations

import itertools

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.security import hash_password
from app.core.text import plate_key
from app.models.driver import Driver, EmploymentStatus
from app.models.fleet import Vehicle, VehicleType
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
    db.flush()
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
    db.flush()
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
    db.flush()
    return driver
