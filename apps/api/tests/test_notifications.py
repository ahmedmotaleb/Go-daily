"""In-app notifications (Task 22): generators, dedupe, clearing, inbox, channels."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cli
from app.core.config import get_settings
from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from app.models.exceptions import (
    ExceptionLabel,
    ExceptionSeverity,
    ExceptionStatus,
    OperationalException,
)
from app.models.finance import FuelTransaction, PaidBy, PaymentMethod, QuantityUnit
from app.models.maintenance import MaintenanceSchedule, MaintenanceType
from app.models.notifications import Notification
from app.models.shift import Shift, ShiftStatus
from app.models.user import User
from app.services import notification_channels
from app.services import notifications as service
from tests.factories import (
    fuel_type_id,
    login_as,
    make_driver,
    make_user,
    make_vehicle,
)


def _for(db: Session, user: User, kind: str | None = None) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if kind:
        stmt = stmt.where(Notification.kind == kind)
    return list(db.scalars(stmt.order_by(Notification.created_at)).all())


@pytest.fixture()
def staff(db: Session) -> dict[str, User]:
    return {
        "admin": make_user(db, role=UserRole.ADMIN),
        "operations": make_user(db, role=UserRole.OPERATIONS),
        "accountant": make_user(db, role=UserRole.ACCOUNTANT),
        "driver": make_user(db, role=UserRole.DRIVER),
        "inactive": make_user(db, role=UserRole.ADMIN, is_active=False),
    }


def test_document_expiry_dedupe_clear_and_escalation(db: Session, staff: dict[str, User]) -> None:
    vehicle = make_vehicle(db, license_expiry=local_today() + timedelta(days=10))
    service.generate(db)
    for role in ("admin", "operations", "accountant"):
        [n] = _for(db, staff[role], "VEHICLE_DOCUMENT")
        assert n.severity.value == "WARNING"
        assert vehicle.internal_code in n.title
        assert n.link == f"/vehicles/{vehicle.id}"
    assert _for(db, staff["driver"]) == []
    assert _for(db, staff["inactive"]) == []

    outcome = service.generate(db)
    assert outcome["results"]["VEHICLE_DOCUMENT"]["new"] == 0
    assert len(_for(db, staff["admin"], "VEHICLE_DOCUMENT")) == 1

    vehicle.license_expiry = local_today() - timedelta(days=1)  # now expired
    db.commit()
    service.generate(db)
    rows = _for(db, staff["admin"], "VEHICLE_DOCUMENT")
    assert [r.severity.value for r in rows] == ["WARNING", "CRITICAL"]
    assert rows[0].cleared_at is not None and rows[1].cleared_at is None

    vehicle.license_expiry = local_today() + timedelta(days=365)  # renewed
    db.commit()
    service.generate(db)
    assert all(r.cleared_at is not None for r in _for(db, staff["admin"], "VEHICLE_DOCUMENT"))


def test_driver_license_expiry(db: Session, staff: dict[str, User]) -> None:
    driver = make_driver(db, license_expiry=local_today() + timedelta(days=5))
    service.generate(db)
    [n] = _for(db, staff["operations"], "DRIVER_LICENSE")
    assert driver.full_name in n.title and n.severity.value == "WARNING"


def test_maintenance_due(db: Session, staff: dict[str, User]) -> None:
    vehicle = make_vehicle(db, current_odometer_km=20_000)
    oil = db.scalars(
        select(MaintenanceType).where(MaintenanceType.code == "ENGINE_OIL_CHANGE")
    ).one()
    db.add(MaintenanceSchedule(vehicle_id=vehicle.id, type_id=oil.id, baseline_km=10_000))
    db.commit()
    service.generate(db)
    [n] = _for(db, staff["accountant"], "MAINTENANCE_DUE")
    assert n.severity.value == "WARNING"
    assert "متأخرة" in n.title and vehicle.internal_code in n.title


def test_tracking_interruption_after_grace(db: Session, staff: dict[str, User]) -> None:
    driver, vehicle = make_driver(db), make_vehicle(db)
    quiet = Shift(
        driver_id=driver.id,
        vehicle_id=vehicle.id,
        status=ShiftStatus.ACTIVE,
        started_at=utcnow() - timedelta(minutes=40),
        start_odometer_km=1000,
    )
    other_vehicle = make_vehicle(db)
    fresh = Shift(
        driver_id=make_driver(db).id,
        vehicle_id=other_vehicle.id,
        status=ShiftStatus.ACTIVE,
        started_at=utcnow() - timedelta(minutes=2),
        start_odometer_km=1000,
    )
    db.add_all([quiet, fresh])
    db.commit()
    service.generate(db)
    rows = _for(db, staff["operations"], "TRACKING_INTERRUPTED")
    assert [r.entity_id for r in rows] == [quiet.id]
    assert "لم تصل أي بيانات" in (rows[0].body or "")

    quiet.status = ShiftStatus.COMPLETED
    quiet.ended_at = utcnow()
    quiet.end_odometer_km = 1010
    db.commit()
    service.generate(db)
    assert _for(db, staff["operations"], "TRACKING_INTERRUPTED")[0].cleared_at is not None


def _exception(db: Session, severity: ExceptionSeverity) -> OperationalException:
    exc = OperationalException(
        rule_code="IMPLAUSIBLE_ODOMETER",
        severity=severity,
        label=ExceptionLabel.REVIEW_REQUIRED,
        summary="اختبار",
        evidence={},
        occurred_at=utcnow() - timedelta(hours=2),
        dedupe_key=f"TEST:{uuid.uuid4()}",
    )
    db.add(exc)
    db.commit()
    return exc


def test_only_important_open_exceptions_notify(db: Session, staff: dict[str, User]) -> None:
    high = _exception(db, ExceptionSeverity.HIGH)
    _exception(db, ExceptionSeverity.LOW)
    service.generate(db)
    [n] = _for(db, staff["accountant"], "EXCEPTION")
    assert n.severity.value == "CRITICAL"
    assert n.title.startswith("مراجعة مطلوبة: ")
    assert n.link == f"/exceptions/{high.id}"

    high.status = ExceptionStatus.DISMISSED
    db.commit()
    service.generate(db)
    assert _for(db, staff["accountant"], "EXCEPTION")[0].cleared_at is not None


def test_pending_review_summary_goes_to_approvers(db: Session, staff: dict[str, User]) -> None:
    vehicle = make_vehicle(db)
    tx = FuelTransaction(
        vehicle_id=vehicle.id,
        fuel_type_id=uuid.UUID(fuel_type_id(db, "CNG")),
        quantity=Decimal("20"),
        unit=QuantityUnit.CUBIC_METER,
        total_amount=Decimal("150"),
        occurred_at=utcnow() - timedelta(days=2),
        payment_method=PaymentMethod.CASH,
        paid_by=PaidBy.COMPANY,
    )
    db.add(tx)
    db.commit()
    tx.created_at = utcnow() - timedelta(days=2)
    db.commit()
    service.generate(db)
    [n] = _for(db, staff["accountant"], "PENDING_REVIEW")
    assert n.title.startswith("1 ") and "وقود: 1" in (n.body or "")
    assert n.link == "/finance/fuel?status=SUBMITTED"
    assert _for(db, staff["operations"], "PENDING_REVIEW") == []  # cannot approve


class Recorder:
    name = "recorder"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def deliver(self, notification: Notification, user: User) -> None:
        self.sent.append((notification.severity.value, str(user.id)))


class Broken:
    name = "broken"

    def deliver(self, notification: Notification, user: User) -> None:
        raise RuntimeError("provider down")


def test_extra_channels_get_new_important_notifications(
    db: Session, staff: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder()
    monkeypatch.setitem(notification_channels.CHANNELS, "recorder", recorder)
    monkeypatch.setitem(notification_channels.CHANNELS, "broken", Broken())
    monkeypatch.setattr(get_settings(), "notification_channels", "broken, recorder, nope")
    monkeypatch.setattr(get_settings(), "notification_channel_min_severity", "CRITICAL")
    make_vehicle(db, license_expiry=local_today() - timedelta(days=3))  # CRITICAL
    make_vehicle(db, license_expiry=local_today() + timedelta(days=3))  # WARNING: not sent
    service.generate(db)
    assert {sev for sev, _ in recorder.sent} == {"CRITICAL"}
    assert len(recorder.sent) == 3  # admin, operations, accountant
    service.generate(db)
    assert len(recorder.sent) == 3  # nothing new, nothing re-sent


def test_a_failing_generator_is_isolated(
    db: Session, staff: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(db: Session) -> list[service.Draft]:
        raise RuntimeError("broken")

    make_vehicle(db, license_expiry=local_today() + timedelta(days=3))
    monkeypatch.setattr(service, "GENERATORS", [("BROKEN", boom), *service.GENERATORS])
    outcome = service.generate(db)
    assert outcome["errors"] == {"BROKEN": "RuntimeError"}
    assert len(_for(db, staff["admin"], "VEHICLE_DOCUMENT")) == 1


def test_inbox_api(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    other, _ = login_as(client, db, UserRole.OPERATIONS)
    make_vehicle(db, license_expiry=local_today() - timedelta(days=1))
    make_vehicle(db, license_expiry=local_today() + timedelta(days=9))
    service.generate(db)

    counts = client.get("/api/v1/notifications/unread-count", headers=h).json()
    assert counts == {"unread": 2, "critical": 1}
    page = client.get("/api/v1/notifications", headers=h).json()
    assert page["total"] == 2
    first = page["items"][0]

    assert client.post(f"/api/v1/notifications/{first['id']}/read", headers=h).json()["read_at"]
    assert client.get("/api/v1/notifications/unread-count", headers=h).json()["unread"] == 1
    assert (
        client.get("/api/v1/notifications", params={"unread_only": True}, headers=h).json()["total"]
        == 1
    )

    others = _for(db, other)
    assert client.post(f"/api/v1/notifications/{others[0].id}/read", headers=h).status_code == 404

    assert client.post("/api/v1/notifications/read-all", headers=h).json() == {"marked": 1}
    assert client.get("/api/v1/notifications/unread-count", headers=h).json()["unread"] == 0
    assert _for(db, other)[0].read_at is None  # only the caller's inbox changed

    assert client.post("/api/v1/notifications/generate", headers=h).status_code == 403
    _, admin_h = login_as(client, db, UserRole.ADMIN)
    res = client.post("/api/v1/notifications/generate", headers=admin_h)
    assert res.status_code == 200 and res.json()["errors"] == {}

    _, driver_h = login_as(client, db, UserRole.DRIVER)
    assert client.get("/api/v1/notifications", headers=driver_h).status_code in (401, 403)


def test_cleared_notifications_are_hidden_unless_requested(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ADMIN)
    vehicle = make_vehicle(db, license_expiry=local_today() + timedelta(days=9))
    service.generate(db)
    vehicle.license_expiry = local_today() + timedelta(days=400)
    db.commit()
    service.generate(db)
    assert client.get("/api/v1/notifications", headers=h).json()["total"] == 0
    all_rows = client.get("/api/v1/notifications", params={"include_cleared": True}, headers=h)
    assert all_rows.json()["items"][0]["cleared_at"] is not None


def test_cli_generate_notifications(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    @contextmanager
    def _session() -> Any:
        yield db

    monkeypatch.setattr(cli, "SessionLocal", _session)
    make_user(db, role=UserRole.ADMIN)
    make_vehicle(db, license_expiry=local_today() + timedelta(days=3))
    assert cli.main(["generate-notifications"]) == 0
    assert "1 new" in capsys.readouterr().out
