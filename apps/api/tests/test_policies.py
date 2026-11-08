"""Versioned company policies (U47)."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import UserRole
from app.core.time import local_today
from app.models.audit import AuditLog
from app.models.cash import ShiftCloseout
from app.models.exceptions import OperationalException
from app.services import policies
from tests.factories import login_as, make_driver_account
from tests.test_driver_cash import _close, _start

URL = "/api/v1/policies"


def test_catalog_matches_the_settings() -> None:
    defaults = get_settings()
    for key in policies.CATALOG:
        value = getattr(defaults, key.key)  # every key is a real setting
        assert key.minimum <= float(value) <= key.maximum, key.key


def test_changes_are_versioned_audited_and_validated(client: TestClient, db: Session) -> None:
    _, admin = login_as(client, db, UserRole.SUPER_ADMIN)
    before = client.get(URL, headers=admin).json()
    start_version = before["version"]

    res = client.post(
        URL,
        headers=admin,
        json={"changes": {"exception_long_stop_minutes": 60}, "reason": "طرق مزدحمة في الصيف"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["version"] == start_version + 1
    long_stop = next(v for v in body["values"] if v["key"] == "exception_long_stop_minutes")
    assert long_stop["value"] == 60 and long_stop["overridden"] is True
    assert long_stop["default"] == get_settings().exception_long_stop_minutes
    latest = body["history"][0]
    assert latest["reason"] == "طرق مزدحمة في الصيف"
    assert latest["changes"]["exception_long_stop_minutes"][1] == 60
    assert latest["created_by"]
    assert db.scalar(select(AuditLog).where(AuditLog.action == "policy.updated")) is not None

    # Back to the default with null: a new version; history keeps both.
    reset = client.post(
        URL,
        headers=admin,
        json={"changes": {"exception_long_stop_minutes": None}, "reason": "عودة"},
    ).json()
    assert reset["version"] == start_version + 2
    assert (
        next(v for v in reset["values"] if v["key"] == "exception_long_stop_minutes")["overridden"]
        is False
    )

    for bad in (
        {"changes": {"exception_long_stop_minutes": 1}, "reason": "خارج الحدود"},
        {"changes": {"exception_long_stop_minutes": 7.5}, "reason": "ليس صحيحًا"},
        {"changes": {"not_a_policy": 1}, "reason": "غير معروف"},
        {"changes": {"exception_long_stop_minutes": None}, "reason": "بلا تغيير"},
    ):
        assert client.post(URL, headers=admin, json=bad).status_code == 422, bad


def test_only_settings_managers_change_policies(client: TestClient, db: Session) -> None:
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    assert client.get(URL, headers=ops).status_code == 200
    change = {"changes": {"cash_handover_days": 3}, "reason": "تجربة"}
    assert client.post(URL, headers=ops, json=change).status_code == 403


def test_review_rules_use_the_current_policy(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    out = _close(client, h, _start(client, h, vehicle)["id"])
    closeout = db.get(ShiftCloseout, out["id"])
    assert closeout is not None
    closeout.service_date = local_today() - timedelta(days=1)
    db.commit()
    _, admin = login_as(client, db, UserRole.SUPER_ADMIN)

    def cash_case() -> OperationalException | None:
        client.post("/api/v1/exceptions/run", json={"days": 3}, headers=admin)
        return db.scalar(
            select(OperationalException).where(
                OperationalException.rule_code == "CASH_NOT_HANDED_OVER",
                OperationalException.driver_id == driver.id,
                OperationalException.cleared_at.is_(None),
            )
        )

    assert cash_case() is None  # default: 2 days allowed
    client.post(
        URL,
        headers=admin,
        json={"changes": {"cash_handover_days": 1}, "reason": "تسليم يومي"},
    )
    case = cash_case()
    assert case is not None and case.evidence["threshold_days"] == 1
