"""Passenger counts (U11): recorded with source and confidence, never inferred."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today
from app.models.audit import AuditLog
from app.models.shift import OperationSession
from tests.factories import login_as, make_completed_shift, make_driver, make_route, make_vehicle


def test_counts_are_recorded_listed_and_voided(client: TestClient, db: Session) -> None:
    shift = make_completed_shift(
        db, make_driver(db), make_vehicle(db), day=local_today() - timedelta(days=1)
    )
    assert shift.started_at is not None
    session = db.scalar(select(OperationSession).where(OperationSession.shift_id == shift.id))
    assert session is not None
    session.route_id = make_route(db).id
    db.commit()
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    url = f"/api/v1/shifts/{shift.id}/passenger-counts"
    at = (shift.started_at + timedelta(hours=1)).isoformat()

    res = client.post(
        url,
        headers=ops,
        json={
            "passengers": 14,
            "source": "SUPERVISOR",
            "confidence": "COUNTED",
            "counted_at": at,
            "session_id": str(session.id),
            "direction": "OUTBOUND",
        },
    )
    assert res.status_code == 201, res.text
    count = res.json()
    assert count["route_id"] == str(session.route_id) and count["source"] == "SUPERVISOR"

    # Integration sources cannot be typed in by hand; times outside the shift are refused.
    for bad in (
        {"source": "HARDWARE", "counted_at": at},
        {"source": "TICKETING", "counted_at": at},
        {"source": "DRIVER", "counted_at": (shift.started_at - timedelta(hours=3)).isoformat()},
    ):
        body = {"passengers": 3, "confidence": "ESTIMATED", **bad}
        assert client.post(url, headers=ops, json=body).status_code == 422, bad
    too_many = {"passengers": 500, "source": "DRIVER", "confidence": "ESTIMATED", "counted_at": at}
    assert client.post(url, headers=ops, json=too_many).status_code == 422

    voided = client.post(
        f"/api/v1/passenger-counts/{count['id']}/void", headers=ops, json={"reason": "عد مكرر"}
    )
    assert voided.status_code == 200 and voided.json()["void_reason"] == "عد مكرر"
    assert (
        client.post(
            f"/api/v1/passenger-counts/{count['id']}/void", headers=ops, json={"reason": "مرة أخرى"}
        ).status_code
        == 409
    )
    listed = client.get(url, headers=ops).json()
    assert len(listed) == 1 and listed[0]["voided_at"]  # kept, marked voided
    actions = set(db.scalars(select(AuditLog.action).where(AuditLog.entity_id == count["id"])))
    assert actions == {"passenger_count.recorded", "passenger_count.voided"}

    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    denied = client.post(
        url, headers=acc, json={"passengers": 1, "source": "DRIVER", "confidence": "COUNTED"}
    )
    assert denied.status_code == 403
