"""Security audit H1 (and runtime M2): review cases follow the reader's data permissions.

Operations is barred from revenue, so it never sees (or closes) the money
rules; accountants have no tracking access, so evidence reaches them without
coordinates. The same rule applies wherever a case is shown: the list, the
case page, related cases, the summary, the timelines, the control centre, the
`exceptions` report and notifications.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from app.models.exceptions import (
    ExceptionLabel,
    ExceptionSeverity,
    OperationalException,
)
from app.models.notifications import Notification
from app.services import notifications
from tests.factories import login_as, make_driver, make_vehicle

E = "/api/v1/exceptions"


def _case(db: Session, rule: str, evidence: dict[str, Any], **ids: Any) -> OperationalException:
    case = OperationalException(
        rule_code=rule,
        severity=ExceptionSeverity.HIGH,
        label=ExceptionLabel.REVIEW_REQUIRED,
        summary=f"حالة {rule}",
        evidence=evidence,
        occurred_at=utcnow() - timedelta(hours=1),
        dedupe_key=f"test:{rule}:{utcnow().timestamp()}",
        **ids,
    )
    db.add(case)
    db.commit()
    return case


def _world(db: Session) -> dict[str, OperationalException]:
    vehicle, driver = make_vehicle(db), make_driver(db)
    ids = {"vehicle_id": vehicle.id, "driver_id": driver.id}
    return {
        "money": _case(
            db,
            "COLLECTION_GAP",
            {"expected": "900.00", "approved": "400.00", "difference": "500.00"},
            **ids,
        ),
        "stop": _case(
            db,
            "LONG_STOP",
            {"minutes": 95, "lat": 31.0409, "lng": 31.3785, "areas": [{"lat": 30.1, "lng": 31.2}]},
            **ids,
        ),
    }


def _codes(res: Any) -> set[str]:
    body = res.json()
    items = body["items"] if isinstance(body, dict) else body
    return {i["rule_code"] for i in items}


def test_operations_never_sees_money_rules(client: TestClient, db: Session) -> None:
    cases = _world(db)
    _, op = login_as(client, db, UserRole.OPERATIONS)
    _, ac = login_as(client, db, UserRole.ACCOUNTANT)
    assert "COLLECTION_GAP" not in _codes(client.get(E, headers=op))
    assert "COLLECTION_GAP" in _codes(client.get(E, headers=ac))
    money = str(cases["money"].id)
    assert client.get(f"{E}/{money}", headers=op).status_code == 404
    assert "COLLECTION_GAP" not in _codes(client.get(f"{E}/{cases['stop'].id}/related", headers=op))
    summary = client.get(f"{E}/summary", headers=op).json()
    assert "COLLECTION_GAP" not in json.dumps(summary)
    # Operations cannot close (dismiss/explain) a financial case either.
    res = client.post(f"{E}/{money}/review", headers=op, json={"status": "DISMISSED"})
    assert res.status_code == 404
    db.refresh(cases["money"])
    assert cases["money"].status.value == "OPEN"


def test_accountants_get_evidence_without_coordinates(client: TestClient, db: Session) -> None:
    cases = _world(db)
    _, ac = login_as(client, db, UserRole.ACCOUNTANT)
    _, op = login_as(client, db, UserRole.OPERATIONS)
    stop = str(cases["stop"].id)
    for url in (E, f"{E}/{stop}", f"{E}/{stop}/related"):
        text = client.get(url, headers=ac).text
        assert "31.3785" not in text and '"lat"' not in text, url
    assert "31.3785" in client.get(f"{E}/{stop}", headers=op).text  # tracking:read keeps them
    assert client.get(f"{E}/{stop}", headers=ac).json()["evidence"]["minutes"] == 95


def test_timelines_and_report_follow_the_same_rule(client: TestClient, db: Session) -> None:
    cases = _world(db)
    vehicle_id = cases["money"].vehicle_id
    driver_id = cases["money"].driver_id
    _, op = login_as(client, db, UserRole.OPERATIONS)
    _, ac = login_as(client, db, UserRole.ACCOUNTANT)
    day = local_today().isoformat()
    money_summary = cases["money"].summary
    for url in (
        f"/api/v1/vehicles/{vehicle_id}/timeline",
        f"/api/v1/drivers/{driver_id}/timeline",
    ):
        assert money_summary not in client.get(url, headers=op, params={"day": day}).text, url
        assert money_summary in client.get(url, headers=ac, params={"day": day}).text, url
    params = {"date_from": day, "date_to": day}
    op_report = client.get("/api/v1/reports/exceptions", headers=op, params=params)
    assert op_report.status_code == 200 and money_summary not in op_report.text
    ac_report = client.get("/api/v1/reports/exceptions", headers=ac, params=params)
    assert "31.3785" not in ac_report.text
    ac_csv = client.get("/api/v1/reports/exceptions/csv", headers=ac, params=params)
    assert "31.3785" not in ac_csv.text


def test_money_case_notifications_go_only_to_revenue_readers(
    client: TestClient, db: Session
) -> None:
    cases = _world(db)
    op_user, _ = login_as(client, db, UserRole.OPERATIONS)
    ac_user, _ = login_as(client, db, UserRole.ACCOUNTANT)
    notifications.generate(db)

    def inbox(user_id: Any) -> set[Any]:
        return set(
            db.scalars(select(Notification.entity_id).where(Notification.user_id == user_id))
        )

    assert cases["money"].id not in inbox(op_user.id)
    assert cases["money"].id in inbox(ac_user.id)
    assert cases["stop"].id in inbox(op_user.id)
