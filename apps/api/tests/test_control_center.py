"""Operations control center (U23): live rows from recorded data, money by permission."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import utcnow
from app.models.exceptions import ExceptionLabel, ExceptionSeverity, OperationalException
from tests.factories import fuel_type_id, login_as, make_driver_account, start_photo

URL = "/api/v1/dashboard/control"


def test_rows_join_shift_tracking_money_and_cases(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = client.post(
        "/api/v1/driver/shifts/start",
        headers=h,
        json={
            "vehicle_id": str(vehicle.id),
            "start_odometer_km": 50_000,
            "start_odometer_photo_id": start_photo(client, h),
        },
    ).json()
    fuel = client.post(
        "/api/v1/driver/fuel",
        headers=h,
        json={"fuel_type_id": fuel_type_id(db, "CNG"), "quantity": "20", "total_amount": "200"},
    )
    assert fuel.status_code == 201, fuel.text
    db.add(
        OperationalException(
            rule_code="GPS_GAP",
            severity=ExceptionSeverity.MEDIUM,
            label=ExceptionLabel.REVIEW_REQUIRED,
            summary="انقطاع تتبع — مراجعة مطلوبة",
            evidence={},
            occurred_at=utcnow(),
            vehicle_id=vehicle.id,
            shift_id=uuid.UUID(shift["id"]),
            dedupe_key=f"test:{uuid.uuid4()}",
        )
    )
    db.commit()

    _, ops = login_as(client, db, UserRole.OPERATIONS)
    body = client.get(URL, headers=ops)
    assert body.status_code == 200, body.text
    row = next(r for r in body.json()["rows"] if r["vehicle_id"] == str(vehicle.id))
    assert row["shift_id"] == shift["id"]
    # No position received yet: none is shown, and the state says so.
    assert row["latitude"] is None and row["tracking_state"] == "OFFLINE"
    assert Decimal(row["fuel_today"]) == Decimal("200")
    assert row["collection_today"] is None  # operations cannot see revenue
    assert row["open_cases"] == 1 and row["case_titles"] == ["انقطاع تتبع — مراجعة مطلوبة"]

    _, admin = login_as(client, db, UserRole.ADMIN)
    full = next(
        r
        for r in client.get(URL, headers=admin).json()["rows"]
        if r["vehicle_id"] == str(vehicle.id)
    )
    assert Decimal(full["collection_today"]) == Decimal("0")

    # Accountants have no access to live positions.
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    assert client.get(URL, headers=acc).status_code == 403
