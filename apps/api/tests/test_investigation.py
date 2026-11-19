"""Investigation workspace (U28): related cases around a case."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import utcnow
from app.models.exceptions import ExceptionLabel, ExceptionSeverity, OperationalException
from tests.factories import login_as
from tests.test_exceptions import pair


def _case(db: Session, **kw: object) -> OperationalException:
    e = OperationalException(
        rule_code="GPS_GAP",
        severity=ExceptionSeverity.MEDIUM,
        label=ExceptionLabel.REVIEW_REQUIRED,
        summary="انقطاع تتبع — مراجعة مطلوبة",
        evidence={},
        dedupe_key=f"test:{uuid.uuid4()}",
        **kw,
    )
    db.add(e)
    db.flush()
    return e


def test_related_cases_share_vehicle_or_driver_within_a_day(
    client: TestClient, db: Session
) -> None:
    driver, vehicle = pair(db)
    other_driver, other_vehicle = pair(db)
    now = utcnow()
    case = _case(db, occurred_at=now, vehicle_id=vehicle.id, driver_id=driver.id)
    same_vehicle = _case(db, occurred_at=now - timedelta(hours=5), vehicle_id=vehicle.id)
    same_driver = _case(
        db, occurred_at=now + timedelta(hours=2), driver_id=driver.id, vehicle_id=other_vehicle.id
    )
    _case(db, occurred_at=now - timedelta(days=3), vehicle_id=vehicle.id)  # too old
    _case(db, occurred_at=now, vehicle_id=other_vehicle.id, driver_id=other_driver.id)
    db.commit()

    _, ops = login_as(client, db, UserRole.OPERATIONS)
    res = client.get(f"/api/v1/exceptions/{case.id}/related", headers=ops)
    assert res.status_code == 200, res.text
    assert [r["id"] for r in res.json()] == [str(same_vehicle.id), str(same_driver.id)]

    assert client.get(f"/api/v1/exceptions/{case.id}/related").status_code == 401
    assert client.get(f"/api/v1/exceptions/{uuid.uuid4()}/related", headers=ops).status_code == 404
