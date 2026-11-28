"""Security audit M7: opt-in rule that whoever enters a financial record cannot approve it.

FINANCE_BLOCK_SELF_APPROVAL_ABOVE (unset by default) blocks self-approval,
including approve_now at entry, from that amount up.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import UserRole
from app.core.time import utcnow
from tests.factories import expense_category_id, login_as, make_vehicle


def _expense(
    client: TestClient, h: dict[str, str], db: Session, amount: str, **extra: object
) -> Any:
    return client.post(
        "/api/v1/expenses",
        headers=h,
        json={
            "vehicle_id": str(make_vehicle(db).id),
            "category_id": expense_category_id(db, "TOLL"),
            "amount": amount,
            "occurred_at": utcnow().isoformat(),
            **extra,
        },
    )


def test_self_approval_is_blocked_above_the_limit_when_enabled(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "finance_block_self_approval_above", Decimal("1000"))
    _, entered_by = login_as(client, db, UserRole.ACCOUNTANT)
    _, colleague = login_as(client, db, UserRole.ACCOUNTANT)

    big = _expense(client, entered_by, db, "1500").json()
    own = client.post(f"/api/v1/expenses/{big['id']}/approve", headers=entered_by, json={})
    assert own.status_code == 403
    assert own.json()["error"]["code"] == "self_approval_blocked"
    other = client.post(f"/api/v1/expenses/{big['id']}/approve", headers=colleague, json={})
    assert other.status_code == 200, other.text

    small = _expense(client, entered_by, db, "500").json()
    ok = client.post(f"/api/v1/expenses/{small['id']}/approve", headers=entered_by, json={})
    assert ok.status_code == 200

    at_entry = _expense(client, entered_by, db, "1500", approve_now=True)
    assert at_entry.status_code == 403
    assert at_entry.json()["error"]["code"] == "self_approval_blocked"


def test_self_approval_is_allowed_by_default(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    created = _expense(client, h, db, "50000", approve_now=True)
    assert created.status_code == 201 and created.json()["status"] == "APPROVED"
