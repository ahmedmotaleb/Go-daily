"""Reports (Task 23): permissions, totals traced to records, CSV export."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_day_bounds_utc, local_today
from app.models.finance import (
    Expense,
    FuelTransaction,
    LedgerEntryType,
    PaidBy,
    PaymentMethod,
    QuantityUnit,
    RecordStatus,
)
from app.services import driver_ledger
from app.services import reports as service
from tests.factories import (
    expense_category_id,
    fuel_type_id,
    login_as,
    make_completed_shift,
    make_driver,
    make_vehicle,
)

YESTERDAY = local_today() - timedelta(days=1)
RANGE = {
    "date_from": (YESTERDAY - timedelta(days=6)).isoformat(),
    "date_to": local_today().isoformat(),
}


def _report(client: TestClient, h: dict[str, str], code: str, **params: Any) -> Any:
    res = client.get(f"/api/v1/reports/{code}", params={**RANGE, **params}, headers=h)
    assert res.status_code == 200, res.text
    return res.json()


def _noon() -> Any:
    return local_day_bounds_utc(YESTERDAY)[0] + timedelta(hours=12)


def _expense(
    db: Session, vehicle_id: uuid.UUID, amount: str, status: RecordStatus, **kw: Any
) -> None:
    db.add(
        Expense(
            vehicle_id=vehicle_id,
            category_id=uuid.UUID(expense_category_id(db, kw.pop("category", "TOLL"))),
            amount=Decimal(amount),
            occurred_at=_noon(),
            payment_method=PaymentMethod.CASH,
            paid_by=PaidBy.COMPANY,
            status=status,
            **kw,
        )
    )
    db.commit()


def test_catalog_and_access_follow_data_permissions(client: TestClient, db: Session) -> None:
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    codes = {r["code"] for r in client.get("/api/v1/reports", headers=ops).json()}
    assert {
        "daily_operations",
        "route_loops",
        "school_runs",
        "gps_odometer",
        "maintenance",
    } <= codes
    assert not codes & {"revenue", "ride_hailing", "vehicle_profitability", "driver_statements"}
    # Hiding is not enough: the API refuses the report itself.
    assert client.get("/api/v1/reports/revenue", headers=ops).status_code == 403
    assert client.get("/api/v1/reports/revenue/csv", headers=ops).status_code == 403

    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    acc_codes = {r["code"] for r in client.get("/api/v1/reports", headers=acc).json()}
    assert {
        "revenue",
        "expenses",
        "fuel",
        "driver_statements",
        "vehicle_profitability",
    } <= acc_codes

    _, drv = login_as(client, db, UserRole.DRIVER)
    assert client.get("/api/v1/reports", headers=drv).status_code in (401, 403)


def test_validation(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ADMIN)
    assert client.get("/api/v1/reports/nope", headers=h).status_code == 404
    bad = client.get(
        "/api/v1/reports/expenses",
        params={"date_from": "2026-05-02", "date_to": "2026-05-01"},
        headers=h,
    )
    assert bad.status_code == 422
    too_long = client.get(
        "/api/v1/reports/expenses",
        params={"date_from": "2024-01-01", "date_to": "2025-06-01"},
        headers=h,
    )
    assert too_long.status_code == 422


def test_every_report_runs_on_empty_data(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.SUPER_ADMIN)
    for r in service.REPORTS:
        body = _report(client, h, r.code)
        assert body["title"] == r.title
        assert body["columns"] and isinstance(body["rows"], list)
        csv_res = client.get(f"/api/v1/reports/{r.code}/csv", params=RANGE, headers=h)
        assert csv_res.status_code == 200, (r.code, csv_res.text)


def test_daily_operations_totals_are_sums_of_rows(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    driver, vehicle = make_driver(db), make_vehicle(db)
    make_completed_shift(
        db,
        driver,
        vehicle,
        day=YESTERDAY,
        minutes=120,
        start_odometer_km=1000,
        end_odometer_km=1100,
    )
    make_completed_shift(
        db,
        driver,
        vehicle,
        day=YESTERDAY - timedelta(days=1),
        minutes=60,
        start_odometer_km=900,
        end_odometer_km=950,
    )
    body = _report(client, h, "daily_operations", vehicle_id=str(vehicle.id))
    assert len(body["rows"]) == 2
    assert body["totals"]["odometer_km"] == 150
    assert body["totals"]["minutes"] == 180
    assert {r["operations"] for r in body["rows"]} == {"خط ثابت"}


def test_expenses_count_approved_only(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    _expense(db, vehicle.id, "15.50", RecordStatus.APPROVED)
    _expense(db, vehicle.id, "40", RecordStatus.APPROVED, category="PARKING")
    _expense(db, vehicle.id, "99", RecordStatus.SUBMITTED)
    _expense(db, vehicle.id, "77", RecordStatus.VOIDED)
    body = _report(client, h, "expenses", vehicle_id=str(vehicle.id))
    assert [r["amount"] for r in body["rows"]] == ["15.50", "40.00"]
    assert body["totals"]["amount"] == "55.50"
    [summary] = body["summaries"]
    assert summary["totals"] == {"count": 2, "amount": "55.50"}
    assert any("المعتمدة فقط" in n for n in body["notes"])


def test_fuel_report_keeps_types_apart(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    for code, qty, unit, amount in (
        ("CNG", "30", QuantityUnit.CUBIC_METER, "210"),
        ("GASOLINE", "20", QuantityUnit.LITER, "300"),
        ("ENGINE_OIL", "4", QuantityUnit.LITER, "800"),
    ):
        db.add(
            FuelTransaction(
                vehicle_id=vehicle.id,
                fuel_type_id=uuid.UUID(fuel_type_id(db, code)),
                quantity=Decimal(qty),
                unit=unit,
                total_amount=Decimal(amount),
                occurred_at=_noon(),
                payment_method=PaymentMethod.CASH,
                paid_by=PaidBy.COMPANY,
                status=RecordStatus.APPROVED,
            )
        )
    db.commit()
    body = _report(client, h, "fuel", vehicle_id=str(vehicle.id))
    assert body["totals"]["total"] == "1310.00"
    by_type = {r["fuel_type"]: r for r in body["summaries"][0]["rows"]}
    assert len(by_type) == 3
    assert {r["unit"] for r in by_type.values()} == {"م³", "لتر"}

    only_cng = _report(
        client, h, "fuel", vehicle_id=str(vehicle.id), fuel_type_id=fuel_type_id(db, "CNG")
    )
    assert only_cng["totals"]["total"] == "210.00"


def test_revenue_shows_received_and_outstanding(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle, driver = make_vehicle(db), make_driver(db)
    res = client.post(
        "/api/v1/revenue",
        json={
            "kind": "PRIVATE_TRIP",
            "vehicle_id": str(vehicle.id),
            "driver_id": str(driver.id),
            "occurred_on": YESTERDAY.isoformat(),
            "amount": "1000",
            "approve_now": True,
            "receipt": {
                "amount": "600",
                "received_at": _noon().isoformat(),
                "method": "CASH",
                "received_by": "COMPANY",
            },
        },
        headers=h,
    )
    assert res.status_code == 201, res.text
    body = _report(client, h, "revenue", vehicle_id=str(vehicle.id))
    [row] = body["rows"]
    assert (row["amount"], row["received"], row["outstanding"]) == ("1000.00", "600.00", "400.00")
    assert row["kind"] == "رحلة خاصة"


def test_driver_statements_balance(client: TestClient, db: Session) -> None:
    admin, h = login_as(client, db, UserRole.ACCOUNTANT)
    driver = make_driver(db)
    driver_ledger.post(
        db,
        driver_id=driver.id,
        entry_type=LedgerEntryType.ADVANCE,
        amount=Decimal("200"),
        occurred_on=YESTERDAY - timedelta(days=30),
        description="سلفة",
        actor=admin,
    )
    driver_ledger.post(
        db,
        driver_id=driver.id,
        entry_type=LedgerEntryType.BONUS,
        amount=Decimal("150"),
        occurred_on=YESTERDAY,
        description="مكافأة",
        actor=admin,
    )
    db.commit()
    body = _report(client, h, "driver_statements", driver_id=str(driver.id))
    [row] = body["rows"]
    assert row["opening"] == "-200.00"
    assert row["earnings"] == "150.00"
    assert row["closing"] == "-50.00"


def test_csv_export_is_excel_friendly_and_safe(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    _expense(db, vehicle.id, "12.30", RecordStatus.APPROVED, vendor='=HYPERLINK("http://x")')
    _expense(db, vehicle.id, "7.70", RecordStatus.APPROVED, vendor="-محطة")
    res = client.get(
        "/api/v1/reports/expenses/csv", params={**RANGE, "vehicle_id": str(vehicle.id)}, headers=h
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert 'attachment; filename="expenses_' in res.headers["content-disposition"]
    text = res.content.decode("utf-8")
    assert text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows[0][0] == "الوقت" and "المبلغ" in rows[0]
    amount = rows[0].index("المبلغ")
    vendor = rows[0].index("المورد")
    assert [r[amount] for r in rows[1:3]] == ["12.30", "7.70"]
    assert rows[1][vendor] == '\'=HYPERLINK("http://x")'
    assert rows[2][vendor] == "'-محطة"
    assert rows[-1][0] == "الإجمالي" and rows[-1][amount] == "20.00"


def test_profitability_report_matches_service_totals(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    vehicle = make_vehicle(db)
    _expense(db, vehicle.id, "100", RecordStatus.APPROVED)
    body = _report(client, h, "vehicle_profitability", vehicle_id=str(vehicle.id))
    [row] = body["rows"]
    assert row["other_expenses"] == "100.00"
    assert row["net_operating_profit"] == "-100.00"
    assert body["totals"]["net_operating_profit"] == "-100.00"
