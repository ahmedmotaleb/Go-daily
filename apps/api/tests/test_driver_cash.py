"""Driver daily workflow: start photo, day-off, close-out, cash collections, account."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import utcnow
from app.models.attachment import Attachment, AttachmentOwner
from app.models.finance import (
    DriverLedgerEntry,
    Expense,
    FuelTransaction,
    LedgerEntryType,
    PaidBy,
    RecordStatus,
    RevenueEntry,
)
from app.models.shift import Shift, ShiftStatus
from tests.factories import (
    login_as,
    make_driver_account,
    make_route,
    operation_type_id,
    start_photo,
)

DA = "/api/v1/driver"
API = "/api/v1"

# The design's example: 2,940 collected; gas 240, gasoline 150, toll 120, brakes 450.
CLOSE: dict[str, Any] = {
    "end_odometer_km": 50_088,
    "collection_amount": "2940",
    "gas_quantity": "24",
    "gas_amount": "240",
    "gasoline_quantity": "8",
    "gasoline_amount": "150",
    "toll_amount": "120",
    "maintenance_kind": "MAINTENANCE",
    "maintenance_amount": "450",
    "maintenance_note": "تغيير تيل فرامل أمامي",
}


def _start(
    client: TestClient, h: dict[str, str], vehicle: Any, odo: int = 50_000, **extra: Any
) -> dict[str, Any]:
    res = client.post(
        f"{DA}/shifts/start",
        headers=h,
        json={
            "vehicle_id": str(vehicle.id),
            "start_odometer_km": odo,
            "start_odometer_photo_id": start_photo(client, h),
            **extra,
        },
    )
    assert res.status_code == 201, res.text
    body: dict[str, Any] = res.json()
    return body


def _close(client: TestClient, h: dict[str, str], shift_id: str, **changes: Any) -> dict[str, Any]:
    res = client.post(f"{DA}/shifts/{shift_id}/closeout", headers=h, json={**CLOSE, **changes})
    assert res.status_code == 201, res.text
    body: dict[str, Any] = res.json()
    return body


def test_start_needs_a_fresh_photo_of_this_driver(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    _, _, other_h, _ = make_driver_account(client, db)
    base = {"vehicle_id": str(vehicle.id), "start_odometer_km": 50_000}

    missing = client.post(f"{DA}/shifts/start", headers=h, json=base)
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "start_photo_required"

    foreign = client.post(
        f"{DA}/shifts/start",
        headers=h,
        json={**base, "start_odometer_photo_id": start_photo(client, other_h)},
    )
    assert foreign.json()["error"]["code"] == "start_photo_invalid"

    stale_id = start_photo(client, h)
    stale = db.get(Attachment, stale_id)
    assert stale is not None
    stale.created_at = utcnow() - timedelta(hours=3)
    db.commit()
    old = client.post(
        f"{DA}/shifts/start", headers=h, json={**base, "start_odometer_photo_id": stale_id}
    )
    assert old.json()["error"]["code"] == "start_photo_invalid"

    photo = start_photo(client, h)
    shift = client.post(
        f"{DA}/shifts/start", headers=h, json={**base, "start_odometer_photo_id": photo}
    )
    assert shift.status_code == 201, shift.text
    assert shift.json()["start_odometer_photo_id"] == photo
    attachment = db.get(Attachment, photo)
    assert attachment is not None and attachment.owner_type is AttachmentOwner.SHIFT
    assert str(attachment.owner_id) == shift.json()["id"]

    # Operations can see it with the shift; the same photo cannot start another shift.
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    assert client.get(f"{API}/attachments/{photo}/content", headers=ops).status_code == 200
    _close(client, h, shift.json()["id"])
    reuse = client.post(
        f"{DA}/shifts/start",
        headers=h,
        json={**base, "start_odometer_km": 50_100, "start_odometer_photo_id": photo},
    )
    assert reuse.json()["error"]["code"] == "start_photo_invalid"


def test_day_off_blocks_the_shift_until_cancelled(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    first = client.post(f"{DA}/day-off", headers=h, json={"note": "السيارة في الصيانة"})
    assert first.status_code == 201, first.text
    again = client.post(f"{DA}/day-off", headers=h, json={})
    assert again.json()["id"] == first.json()["id"]
    assert client.get(f"{DA}/day-off", headers=h).json()["note"] == "السيارة في الصيانة"

    blocked = client.post(
        f"{DA}/shifts/start",
        headers=h,
        json={
            "vehicle_id": str(vehicle.id),
            "start_odometer_km": 50_000,
            "start_odometer_photo_id": start_photo(client, h),
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "day_off"

    _, ops = login_as(client, db, UserRole.OPERATIONS)
    listed = client.get(f"{API}/day-offs", headers=ops).json()
    assert any(o["driver"]["id"] == str(driver.id) for o in listed)

    assert client.post(f"{DA}/day-off/cancel", headers=h).status_code == 200
    assert client.get(f"{DA}/day-off", headers=h).json() is None
    shift = _start(client, h, vehicle)
    busy = client.post(f"{DA}/day-off", headers=h, json={})
    assert busy.json()["error"]["code"] == "active_shift"
    _close(client, h, shift["id"])
    worked = client.post(f"{DA}/day-off", headers=h, json={})
    assert worked.json()["error"]["code"] == "shift_that_day"


def test_closeout_ends_the_shift_and_books_each_line(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    route = make_route(db)
    shift = _start(
        client, h, vehicle, operation_type_id=operation_type_id(db), route_id=str(route.id)
    )
    key = {**h, "Idempotency-Key": "close-1"}
    res = client.post(f"{DA}/shifts/{shift['id']}/closeout", headers=key, json=CLOSE)
    assert res.status_code == 201, res.text
    out = res.json()
    assert Decimal(out["deductions"]) == Decimal("960")
    assert Decimal(out["net_amount"]) == Decimal("1980")
    assert Decimal(out["total_due"]) == Decimal("1980")
    assert out["status"] == "WAITING" and out["collection_booked"] is True
    assert [ln["key"] for ln in out["lines"]] == ["gas", "gasoline", "toll", "maintenance"]
    assert all(ln["deducted"] and ln["record_status"] == "SUBMITTED" for ln in out["lines"])
    assert out["start_odometer_km"] == 50_000 and out["end_odometer_km"] == 50_088

    retry = client.post(f"{DA}/shifts/{shift['id']}/closeout", headers=key, json=CLOSE)
    assert retry.json()["id"] == out["id"]
    dup = client.post(f"{DA}/shifts/{shift['id']}/closeout", headers=h, json=CLOSE)
    assert dup.json()["error"]["code"] == "already_closed_out"

    ended = db.get(Shift, shift["id"])
    assert ended is not None and ended.status is ShiftStatus.COMPLETED
    assert ended.end_odometer_km == 50_088
    entry = db.scalar(select(RevenueEntry).where(RevenueEntry.shift_id == ended.id))
    assert entry is not None and entry.amount == Decimal("2940.00")
    assert entry.receipts[0].received_by.value == "DRIVER"
    fuels = db.scalars(select(FuelTransaction).where(FuelTransaction.shift_id == ended.id)).all()
    assert sorted(f.fuel_type.code for f in fuels) == ["CNG", "GASOLINE"]
    assert all(f.paid_by is PaidBy.DRIVER and f.status is RecordStatus.SUBMITTED for f in fuels)
    costs = db.scalars(select(Expense).where(Expense.shift_id == ended.id)).all()
    assert sorted(c.category.code for c in costs) == ["REPAIR", "TOLL"]
    assert any(c.notes == "تغيير تيل فرامل أمامي" for c in costs)
    held = db.scalar(
        select(DriverLedgerEntry).where(
            DriverLedgerEntry.driver_id == driver.id,
            DriverLedgerEntry.entry_type == LedgerEntryType.CASH_COLLECTED,
        )
    )
    assert held is not None and held.amount == Decimal("-2940.00")


def test_closeout_input_is_checked_before_anything_changes(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle)
    cases: list[tuple[dict[str, Any], str]] = [
        ({"gas_quantity": None}, "gas_quantity"),
        ({"maintenance_note": "  "}, "maintenance_note"),
        ({"maintenance_kind": "NONE"}, "maintenance_kind"),
    ]
    for change, field in cases:
        res = client.post(
            f"{DA}/shifts/{shift['id']}/closeout", headers=h, json={**CLOSE, **change}
        )
        assert res.status_code == 422, res.text
        assert field in res.text
    still = db.get(Shift, shift["id"])
    assert still is not None and still.status is ShiftStatus.ACTIVE
    oil = _close(
        client, h, shift["id"], maintenance_kind="OIL_CHANGE", maintenance_note="زيت وفلتر"
    )
    assert oil["lines"][3]["label"] == "تغيير زيت"


def test_rejected_expense_is_due_from_the_driver(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    out = _close(client, h, _start(client, h, vehicle)["id"])
    toll = db.scalar(
        select(Expense).where(Expense.shift_id == out["shift_id"], Expense.amount == Decimal("120"))
    )
    assert toll is not None
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    rejected = client.post(
        f"{API}/expenses/{toll.id}/reject", headers=acc, json={"reason": "لا يوجد إيصال"}
    )
    assert rejected.status_code == 200, rejected.text
    again = client.get(f"{API}/cash/closeouts/{out['id']}", headers=acc).json()
    assert Decimal(again["net_amount"]) == Decimal("2100")
    line = next(ln for ln in again["lines"] if ln["key"] == "toll")
    assert line["deducted"] is False and line["record_status"] == "REJECTED"


def test_partial_collection_carries_over(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    first = _close(client, h, _start(client, h, vehicle)["id"])
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)

    too_much = client.post(
        f"{API}/cash/collections",
        headers=acc,
        json={"driver_id": str(driver.id), "closeout_id": first["id"], "amount": "2000"},
    )
    assert too_much.json()["error"]["code"] == "over_collection"
    paid = client.post(
        f"{API}/cash/collections",
        headers=acc,
        json={
            "driver_id": str(driver.id),
            "closeout_id": first["id"],
            "amount": "1700",
            "note": "الباقي مع تقفيل الخميس",
        },
    )
    assert paid.status_code == 201, paid.text
    now = client.get(f"{API}/cash/closeouts/{first['id']}", headers=acc).json()
    assert now["status"] == "PARTIAL" and Decimal(now["remaining"]) == Decimal("280")

    # A later shift the same day starts from the 280 still due.
    second = _close(
        client,
        h,
        _start(client, h, vehicle, odo=50_088)["id"],
        end_odometer_km=50_150,
        collection_amount="1000",
        gas_amount="0",
        gas_quantity=None,
        gasoline_amount="0",
        gasoline_quantity=None,
        toll_amount="0",
        maintenance_kind="NONE",
        maintenance_amount="0",
        maintenance_note=None,
    )
    assert Decimal(second["carried_before"]) == Decimal("280")
    assert Decimal(second["total_due"]) == Decimal("1280")
    settle = client.post(
        f"{API}/cash/collections",
        headers=acc,
        json={"driver_id": str(driver.id), "closeout_id": second["id"], "amount": "1280"},
    )
    assert settle.status_code == 201
    account = client.get(f"{DA}/account", headers=h).json()
    assert Decimal(account["outstanding"]) == 0
    assert account["today_closeout"]["status"] == "COLLECTED"
    handovers = db.scalars(
        select(DriverLedgerEntry.amount).where(
            DriverLedgerEntry.driver_id == driver.id,
            DriverLedgerEntry.entry_type == LedgerEntryType.CASH_HANDOVER,
            DriverLedgerEntry.voided_at.is_(None),
        )
    ).all()
    assert sorted(handovers) == [Decimal("1280.00"), Decimal("1700.00")]

    undone = client.post(
        f"{API}/cash/collections/{settle.json()['id']}/void",
        headers=acc,
        json={"reason": "سُجل بالخطأ"},
    )
    assert undone.status_code == 200
    assert Decimal(client.get(f"{DA}/account", headers=h).json()["outstanding"]) == 1280


def test_void_closeout_needs_its_collections_voided_first(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    out = _close(client, h, _start(client, h, vehicle)["id"])
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    paid = client.post(
        f"{API}/cash/collections",
        headers=acc,
        json={"driver_id": str(driver.id), "closeout_id": out["id"], "amount": "100"},
    ).json()
    blocked = client.post(
        f"{API}/cash/closeouts/{out['id']}/void", headers=acc, json={"reason": "أرقام خاطئة"}
    )
    assert blocked.json()["error"]["code"] == "closeout_has_collections"
    client.post(f"{API}/cash/collections/{paid['id']}/void", headers=acc, json={"reason": "خطأ"})
    voided = client.post(
        f"{API}/cash/closeouts/{out['id']}/void", headers=acc, json={"reason": "أرقام خاطئة"}
    )
    assert voided.status_code == 200, voided.text
    assert voided.json()["voided_at"] is not None
    statuses = {
        r.status
        for model in cast(tuple[Any, ...], (RevenueEntry, FuelTransaction, Expense))
        for r in db.scalars(select(model).where(model.shift_id == out["shift_id"])).all()
    }
    assert statuses == {RecordStatus.VOIDED}
    # The custody entry from the driver's receipt is reversed too.
    live_held = db.scalars(
        select(DriverLedgerEntry).where(
            DriverLedgerEntry.driver_id == driver.id,
            DriverLedgerEntry.entry_type == LedgerEntryType.CASH_COLLECTED,
            DriverLedgerEntry.voided_at.is_(None),
        )
    ).all()
    assert live_held == []
    # The office can enter it again for the ended shift (same end reading).
    again = client.post(
        f"{API}/cash/shifts/{out['shift_id']}/closeout",
        headers=acc,
        json={**CLOSE, "collection_amount": "2900"},
    )
    assert again.status_code == 201, again.text
    assert again.json()["source"] == "ADMIN"
    mismatch = client.post(
        f"{API}/cash/closeouts/{again.json()['id']}/void", headers=acc, json={"reason": "مرة أخرى"}
    )
    assert mismatch.status_code == 200
    wrong = client.post(
        f"{API}/cash/shifts/{out['shift_id']}/closeout",
        headers=acc,
        json={**CLOSE, "end_odometer_km": 50_500},
    )
    assert wrong.json()["error"]["code"] == "end_odometer_mismatch"


def test_board_rows_permissions_and_ride_hailing(client: TestClient, db: Session) -> None:
    worker, _, h1, v1 = make_driver_account(client, db)
    resting, _, h2, _ = make_driver_account(client, db)
    running, _, h3, v3 = make_driver_account(client, db)
    out = _close(
        client,
        h1,
        _start(client, h1, v1, operation_type_id=operation_type_id(db, "RIDE_HAILING"))["id"],
    )
    # Ride-hailing revenue comes from platform statements: the cash is tracked, not booked.
    assert out["collection_booked"] is False
    assert db.scalar(select(RevenueEntry).where(RevenueEntry.shift_id == out["shift_id"])) is None
    client.post(f"{DA}/day-off", headers=h2, json={"note": "ظرف عائلي"})
    _start(client, h3, v3)

    _, ops = login_as(client, db, UserRole.OPERATIONS)
    board = client.get(f"{API}/cash/board", headers=ops)
    assert board.status_code == 200, board.text
    rows = {r["driver"]["id"]: r for r in board.json()["rows"]}
    assert rows[str(worker.id)]["kind"] == "CLOSEOUT"
    assert Decimal(rows[str(worker.id)]["outstanding"]) == Decimal("1980")
    assert rows[str(resting.id)]["kind"] == "DAY_OFF"
    assert rows[str(running.id)]["kind"] == "OPEN_SHIFT"
    summary = board.json()
    assert summary["day_offs"] >= 1 and summary["open_shifts"] >= 1
    assert Decimal(summary["open_balance"]) >= Decimal("1980")

    denied = client.post(
        f"{API}/cash/collections",
        headers=ops,
        json={"driver_id": str(worker.id), "amount": "10"},
    )
    assert denied.status_code == 403
    assert client.get(f"{API}/cash/board", headers=h1).status_code == 403

    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    staff_view = client.get(f"{API}/drivers/{resting.id}/cash-account", headers=acc).json()
    assert staff_view["today_day_off"]["note"] == "ظرف عائلي"
    assert staff_view["day_off_days"] == 1


def test_receipt_photo_and_staff_day_offs(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    _, _, other_h, _ = make_driver_account(client, db)
    out = _close(client, h, _start(client, h, vehicle)["id"])
    png = {"file": ("receipt.png", b"\x89PNG\r\n\x1a\n" + b"r" * 80, "image/png")}
    stranger = client.post(f"{DA}/closeouts/{out['id']}/receipt", headers=other_h, files=png)
    assert stranger.status_code == 404
    mine = client.post(f"{DA}/closeouts/{out['id']}/receipt", headers=h, files=png)
    assert mine.status_code == 201, mine.text
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    detail = client.get(f"{API}/cash/closeouts/{out['id']}", headers=acc).json()
    assert detail["receipt_attachment_ids"] == [mine.json()["attachment_id"]]

    _, ops = login_as(client, db, UserRole.OPERATIONS)
    tomorrow = (utcnow() + timedelta(days=1)).date().isoformat()
    off = client.post(
        f"{API}/day-offs",
        headers=ops,
        json={"driver_id": str(driver.id), "day": tomorrow, "note": "إجازة مخططة"},
    )
    assert off.status_code == 201, off.text
    assert off.json()["source"] == "ADMIN"
    assert (
        client.get(f"{API}/day-offs?day={tomorrow}", headers=ops).json()[0]["id"]
        == off.json()["id"]
    )
    cancelled = client.post(
        f"{API}/day-offs/{off.json()['id']}/cancel", headers=ops, json={"reason": "تغيير الجدول"}
    )
    assert cancelled.status_code == 200
    assert client.get(f"{API}/day-offs?day={tomorrow}", headers=ops).json() == []
