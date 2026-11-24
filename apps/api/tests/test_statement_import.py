"""Ride-hailing statement CSV import (U19)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today
from app.models.audit import AuditLog
from app.services import statement_import as service
from tests.factories import (
    assign,
    login_as,
    make_completed_shift,
    make_driver,
    make_platform,
    make_vehicle,
)

URL = "/api/v1/ride-hailing/imports"


def _day(n: int) -> str:
    return (local_today() - timedelta(days=n)).isoformat()


def _body(platform: Any, content: str, **extra: Any) -> dict[str, Any]:
    return {"platform_id": str(platform.id), "file_name": "uber.csv", "content": content, **extra}


def test_money_and_dates_are_parsed_safely() -> None:
    assert service.parse_money("1,234.50 ج.م") == Decimal("1234.50")
    assert service.parse_money("١٢٣٫٤٥") == Decimal("123.45")
    assert service.parse_money("(20)") == Decimal("-20")
    assert service.parse_money("") is None
    for bad in ("12.345", "abc"):
        try:
            service.parse_money(bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    assert service.parse_date("05/11/2026").isoformat() == "2026-11-05"
    assert service.parse_date("2026-11-05 10:00").isoformat() == "2026-11-05"


def test_preview_import_and_roll_back(client: TestClient, db: Session) -> None:
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    platform = make_platform(db)
    worked, idle = make_driver(db), make_driver(db)
    car = make_vehicle(db)
    assign(db, worked, car)  # no vehicle column: the assignment decides
    make_completed_shift(
        db, worked, car, day=local_today() - timedelta(days=3), operation_code="RIDE_HAILING"
    )
    other_car = make_vehicle(db)
    csv_text = "\n".join(
        [
            "Phone,Date,Trips,Gross,Fees,Cash,Ref",
            f'{worked.phone},{_day(3)},12,"1,200.00",300,150,R-1',
            f"{idle.phone},{_day(3)},4,400,100,0,R-2",  # no assignment and no vehicle
            f"{worked.phone},{_day(3)},12,1200,300,150,R-1",  # same row twice
            f"01099999999,{_day(3)},1,10,1,0,R-3",  # unknown driver
            f"{worked.phone},{_day(2)},5,100,500,0,R-4",  # fees above income
        ]
    )
    mapping = {
        "driver_phone": "Phone",
        "period_start": "Date",
        "trips_count": "Trips",
        "gross_earnings": "Gross",
        "platform_fees": "Fees",
        "cash_collected": "Cash",
        "statement_reference": "Ref",
    }
    res = client.post(
        f"{URL}/preview", headers=acc, json=_body(platform, csv_text, mapping=mapping)
    )
    assert res.status_code == 200, res.text
    preview = res.json()
    statuses = [r["status"] for r in preview["rows"]]
    assert statuses == ["OK", "ERROR", "DUPLICATE", "ERROR", "ERROR"]
    first = preview["rows"][0]
    assert first["vehicle"] == car.internal_code and first["net_earnings"] == "900.00"
    assert first["warnings"] == []  # a ride-hailing shift is recorded that day
    assert preview["counts"] == {"OK": 1, "ERROR": 3, "DUPLICATE": 1, "warnings": 0}
    # Nothing is saved by a preview.
    assert all(b["platform"]["id"] != str(platform.id) for b in client.get(URL, headers=acc).json())

    content = "\n".join(
        [
            "Phone,Date,Trips,Gross,Fees,Cash,Ref,Car",
            f"{worked.phone},{_day(3)},12,1200,300,150,R-1,",
            f"{idle.phone},{_day(1)},4,400,100,0,R-5,{other_car.internal_code}",
            f"{worked.phone},{_day(2)},5,100,500,0,R-4,",
        ]
    )
    with_car = {**mapping, "vehicle": "Car"}
    res = client.post(URL, headers=acc, json=_body(platform, content, mapping=with_car))
    assert res.status_code == 201, res.text
    batch = res.json()
    assert batch["rows_total"] == 3 and batch["rows_imported"] == 2
    assert batch["skipped"][0]["row"] == 3 and batch["pending"] == 2
    statements = client.get(
        "/api/v1/ride-hailing/statements", headers=acc, params={"platform_id": str(platform.id)}
    ).json()["items"]
    assert {s["status"] for s in statements} == {"SUBMITTED"}  # still reviewed as usual
    idle_statement = next(s for s in statements if s["driver"]["id"] == str(idle.id))
    assert "مراجعة مطلوبة" in (idle_statement["notes"] or "")  # no shift recorded
    assert idle_statement["vehicle"]["id"] == str(other_car.id)

    # The mapping is remembered for the platform; the same file cannot be imported twice.
    again = client.post(URL, headers=acc, json=_body(platform, content))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "file_already_imported"

    # Roll back: needs revenue approval; voids everything the file created, approved or not.
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    denied = client.post(f"{URL}/{batch['id']}/void", headers=ops, json={"reason": "ملف خاطئ"})
    assert denied.status_code == 403
    _, approver = login_as(client, db, UserRole.ADMIN)
    approved = client.post(
        f"/api/v1/ride-hailing/statements/{statements[0]['id']}/approve", headers=approver, json={}
    )
    assert approved.status_code == 200, approved.text
    res = client.post(f"{URL}/{batch['id']}/void", headers=approver, json={"reason": "ملف خاطئ"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "VOIDED"
    after = client.get(
        "/api/v1/ride-hailing/statements", headers=acc, params={"platform_id": str(platform.id)}
    ).json()["items"]
    assert {s["status"] for s in after} == {"VOIDED"}
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "ride_hailing_import.voided"))
    # Once rolled back, the corrected file can be imported again.
    assert client.post(URL, headers=acc, json=_body(platform, content)).status_code == 201


def test_mapping_is_guessed_and_checked(client: TestClient, db: Session) -> None:
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    platform = make_platform(db)
    res = client.post(
        f"{URL}/preview", headers=acc, json=_body(platform, "phone;date;gross;fees\n")
    )
    assert res.status_code == 200, res.text  # semicolons and common names are recognised
    assert res.json()["mapping"] == {
        "driver_phone": "phone",
        "period_start": "date",
        "gross_earnings": "gross",
        "platform_fees": "fees",
    }
    missing = client.post(f"{URL}/preview", headers=acc, json=_body(platform, "a,b\n1,2\n"))
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "mapping_incomplete"
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    assert (
        client.post(f"{URL}/preview", headers=ops, json=_body(platform, "a\n")).status_code == 403
    )
