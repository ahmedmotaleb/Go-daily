"""Driver daily workflow: start photo, day-off, close-out, cash collections, account."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from app.models.attachment import Attachment, AttachmentOwner
from app.models.finance import (
    DriverLedgerEntry,
    Expense,
    FuelTransaction,
    LedgerEntryType,
    PaidBy,
    RecordStatus,
    RevenueEntry,
    RevenueKind,
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
    # Operations follows the states; the amounts are revenue (security audit M1).
    assert rows[str(worker.id)]["outstanding"] is None
    assert rows[str(resting.id)]["kind"] == "DAY_OFF"
    assert rows[str(running.id)]["kind"] == "OPEN_SHIFT"
    summary = board.json()
    assert summary["day_offs"] >= 1 and summary["open_shifts"] >= 1
    assert summary["open_balance"] is None
    _, acc_board = login_as(client, db, UserRole.ACCOUNTANT)
    full = client.get(f"{API}/cash/board", headers=acc_board).json()
    full_rows = {r["driver"]["id"]: r for r in full["rows"]}
    assert Decimal(full_rows[str(worker.id)]["outstanding"]) == Decimal("1980")
    assert Decimal(full["open_balance"]) >= Decimal("1980")

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
    tomorrow = (local_today() + timedelta(days=1)).isoformat()  # Cairo, not UTC
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


# --- Security audit (security H4): mixed shifts book revenue per session kind ----------


def _mixed_shift(
    client: TestClient, db: Session, staff: dict[str, str], *, fixed_minutes: int, rh_minutes: int
) -> tuple[Any, str]:
    """An ended shift: a fixed-route session, then a ride-hailing session."""
    from tests.factories import assign, make_driver, make_vehicle

    driver, vehicle = make_driver(db), make_vehicle(db, current_odometer_km=50_000)
    assign(db, driver, vehicle)
    route = make_route(db)
    total = fixed_minutes + rh_minutes
    start = utcnow() - timedelta(minutes=total + 5)
    shift = client.post(
        f"{API}/shifts",
        headers=staff,
        json={
            "driver_id": str(driver.id),
            "vehicle_id": str(vehicle.id),
            "start_now": True,
            "start_odometer_km": 50_000,
            "started_at": start.isoformat(),
        },
    )
    assert shift.status_code == 201, shift.text
    sid = shift.json()["id"]
    if fixed_minutes == 0:  # ride-hailing only
        only = client.post(
            f"{API}/shifts/{sid}/sessions",
            headers=staff,
            json={
                "operation_type_id": operation_type_id(db, "RIDE_HAILING"),
                "started_at": start.isoformat(),
            },
        )
        assert only.status_code == 201, only.text
        return driver, sid
    fixed = client.post(
        f"{API}/shifts/{sid}/sessions",
        headers=staff,
        json={
            "operation_type_id": operation_type_id(db, "FIXED_ROUTE"),
            "route_id": str(route.id),
            "started_at": start.isoformat(),
        },
    )
    assert fixed.status_code == 201, fixed.text
    switch = start + timedelta(minutes=fixed_minutes)
    ended = client.post(
        f"{API}/operation-sessions/{fixed.json()['id']}/end",
        headers=staff,
        json={"ended_at": switch.isoformat()},
    )
    assert ended.status_code == 200, ended.text
    rh = client.post(
        f"{API}/shifts/{sid}/sessions",
        headers=staff,
        json={
            "operation_type_id": operation_type_id(db, "RIDE_HAILING"),
            "started_at": switch.isoformat(),
        },
    )
    assert rh.status_code == 201, rh.text
    return driver, sid


def _revenue_for_shift(db: Session, shift_id: str) -> list[RevenueEntry]:
    return list(
        db.scalars(
            select(RevenueEntry).where(
                RevenueEntry.shift_id == shift_id, RevenueEntry.status != RecordStatus.VOIDED
            )
        ).all()
    )


SIMPLE: dict[str, Any] = {
    "end_odometer_km": 50_050,
    "collection_amount": "1000",
    "toll_amount": "0",
}


def test_mixed_shift_needs_the_ride_hailing_part(client: TestClient, db: Session) -> None:
    _, acc = login_as(client, db, UserRole.ADMIN)
    _, sid = _mixed_shift(client, db, acc, fixed_minutes=60, rh_minutes=180)
    res = client.post(f"{API}/cash/shifts/{sid}/closeout", headers=acc, json=SIMPLE)
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "ride_hailing_split_required"


def test_mixed_shift_books_only_the_non_ride_hailing_cash(client: TestClient, db: Session) -> None:
    _, acc = login_as(client, db, UserRole.ADMIN)
    # Ride-hailing ran longest: the fixed-route cash used to be lost.
    _, sid = _mixed_shift(client, db, acc, fixed_minutes=60, rh_minutes=180)
    body = {**SIMPLE, "ride_hailing_amount": "400"}
    res = client.post(f"{API}/cash/shifts/{sid}/closeout", headers=acc, json=body)
    assert res.status_code == 201, res.text
    assert res.json()["ride_hailing_amount"] == "400.00"
    [entry] = _revenue_for_shift(db, sid)
    assert entry.kind is RevenueKind.FIXED_ROUTE_COLLECTION and entry.amount == Decimal("600")
    # Fixed route ran longest: the ride-hailing cash used to be booked as route revenue.
    _, sid2 = _mixed_shift(client, db, acc, fixed_minutes=180, rh_minutes=60)
    res = client.post(f"{API}/cash/shifts/{sid2}/closeout", headers=acc, json=body)
    assert res.status_code == 201, res.text
    [entry] = _revenue_for_shift(db, sid2)
    assert entry.amount == Decimal("600")


def test_ride_hailing_part_needs_a_ride_hailing_session(client: TestClient, db: Session) -> None:
    _, h, vehicle = make_driver_account(client, db)[1:]
    shift = _start(client, h, vehicle)
    res = client.post(
        f"{DA}/shifts/{shift['id']}/closeout",
        headers=h,
        json={**CLOSE, "ride_hailing_amount": "10"},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "ride_hailing_not_in_shift"


def test_statement_cash_is_not_counted_twice_on_the_cash_board(
    client: TestClient, db: Session
) -> None:
    from tests.factories import make_platform

    _, acc = login_as(client, db, UserRole.ADMIN)
    driver, sid = _mixed_shift(client, db, acc, fixed_minutes=0, rh_minutes=120)
    shift = db.get(Shift, uuid.UUID(sid))
    assert shift is not None
    res = client.post(f"{API}/cash/shifts/{sid}/closeout", headers=acc, json=SIMPLE)
    assert res.status_code == 201, res.text
    before = client.get(f"{API}/drivers/{driver.id}/cash-account", headers=acc).json()
    platform = make_platform(db)
    statement = client.post(
        f"{API}/ride-hailing/statements",
        headers=acc,
        json={
            "platform_id": str(platform.id),
            "driver_id": str(driver.id),
            "vehicle_id": str(shift.vehicle_id),
            "period_start": local_today().isoformat(),
            "period_end": local_today().isoformat(),
            "gross_earnings": "1500",
            "platform_fees": "300",
            "cash_collected": "1000",
            "approve_now": True,
        },
    )
    assert statement.status_code == 201, statement.text
    after = client.get(f"{API}/drivers/{driver.id}/cash-account", headers=acc).json()
    # The close-out already asks for this ride-hailing cash; the statement's cash
    # receipt is the same money and must not be asked for again.
    assert after["outstanding"] == before["outstanding"] == "1000.00"


# --- Security audit M1: Operations follows close-outs without the cash figures ---------


def test_operations_sees_cash_states_but_not_amounts(client: TestClient, db: Session) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle)
    closeout = _close(client, h, shift["id"])
    _, op = login_as(client, db, UserRole.OPERATIONS)
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    day = local_today().isoformat()
    for url, params in (
        (f"{API}/cash/board", {"day": day}),
        (f"{API}/cash/closeouts/{closeout['id']}", {}),
        (f"{API}/drivers/{driver.id}/cash-account", {}),
        (f"/api/v1/vehicles/{vehicle.id}/timeline", {"day": day}),
        (f"/api/v1/drivers/{driver.id}/timeline", {"day": day}),
    ):
        seen = client.get(url, headers=op, params=params)
        assert seen.status_code == 200, (url, seen.text)
        # 450 is the maintenance expense: Operations reads expenses (expenses:read).
        for figure in ("2940", "1980"):
            assert figure not in seen.text, (url, figure)
        assert "2940" in client.get(url, headers=acc, params=params).text, url
    detail = client.get(f"{API}/cash/closeouts/{closeout['id']}", headers=op).json()
    assert detail["status"] == "WAITING" and detail["net_amount"] is None
    assert detail["lines"][0]["quantity"] == "24.000"  # quantities are not money


# --- Security audit M2: the cash board follows the close-out's live revenue entry -------


def test_board_follows_the_revenue_entry_after_office_corrections(
    client: TestClient, db: Session
) -> None:
    driver, _, h, vehicle = make_driver_account(client, db)
    closeout = _close(client, h, _start(client, h, vehicle)["id"])
    entry = db.scalar(select(RevenueEntry).where(RevenueEntry.shift_id == closeout["shift_id"]))
    assert entry is not None
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)

    def net() -> str:
        res = client.get(f"{API}/cash/closeouts/{closeout['id']}", headers=acc).json()
        return str(res["net_amount"])

    assert net() == "1980.00"
    assert (
        client.post(f"/api/v1/revenue/{entry.id}/approve", headers=acc, json={}).status_code == 200
    )
    corrected = client.post(
        f"/api/v1/revenue/{entry.id}/correct",
        headers=acc,
        json={
            "kind": "FIXED_ROUTE_COLLECTION",
            "vehicle_id": str(vehicle.id),
            "driver_id": str(driver.id),
            "shift_id": closeout["shift_id"],
            "occurred_on": closeout["service_date"],
            "amount": "3000",
            "reason": "تصحيح مبلغ التحصيل",
            "approve_now": True,
        },
    )
    assert corrected.status_code in (200, 201), corrected.text
    # The receipt held by the driver moved to the replacement: custody is still 2,940
    # (the extra 60 is revenue not yet received), as in the driver's ledger.
    assert net() == "1980.00"
    replacement = client.get(f"/api/v1/revenue/{corrected.json()['id']}", headers=acc).json()
    for receipt in replacement["receipts"]:
        res = client.post(
            f"/api/v1/revenue/receipts/{receipt['id']}/void",
            headers=acc,
            json={"reason": "لم يتم التحصيل"},
        )
        assert res.status_code == 200, res.text
    assert net() == "-960.00"  # the driver no longer holds that cash
    voided = client.post(
        f"/api/v1/revenue/{corrected.json()['id']}/void",
        headers=acc,
        json={"reason": "لم يتم التحصيل"},
    )
    assert voided.status_code == 200, voided.text
    assert net() == "-960.00"  # no cash held any more; the costs are still owed to the driver
    over = client.post(
        f"{API}/cash/collections",
        headers=acc,
        json={"driver_id": str(driver.id), "closeout_id": closeout["id"], "amount": "1"},
    )
    assert over.json()["error"]["code"] == "over_collection"


# --- Security audit M3: voiding a close-out respects the approval permissions ----------


def test_voiding_a_closeout_with_approved_records_needs_approve_rights(
    client: TestClient, db: Session, monkeypatch: Any
) -> None:
    from app.core import permissions
    from app.core.permissions import Permission

    _, _, h, vehicle = make_driver_account(client, db)
    closeout = _close(client, h, _start(client, h, vehicle)["id"])
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    entry = db.scalar(select(RevenueEntry).where(RevenueEntry.shift_id == closeout["shift_id"]))
    assert entry is not None
    assert (
        client.post(f"/api/v1/revenue/{entry.id}/approve", headers=acc, json={}).status_code == 200
    )
    # A role that may collect cash but not approve revenue (none today; the rule must not
    # depend on that coincidence).
    reduced = permissions.ROLE_PERMISSIONS[UserRole.ACCOUNTANT] - {Permission.REVENUE_APPROVE}
    monkeypatch.setitem(permissions.ROLE_PERMISSIONS, UserRole.ACCOUNTANT, reduced)
    res = client.post(
        f"{API}/cash/closeouts/{closeout['id']}/void", headers=acc, json={"reason": "خطأ"}
    )
    assert res.status_code == 403, res.text
    assert res.json()["error"]["details"]["missing"] == ["revenue:approve"]
    db.refresh(entry)
    assert entry.status is RecordStatus.APPROVED


def test_closeout_in_a_settled_period_cannot_be_voided(client: TestClient, db: Session) -> None:
    from app.models.driver import CompensationMethod
    from tests.factories import make_plan

    driver, _, h, vehicle = make_driver_account(client, db)
    closeout = _close(client, h, _start(client, h, vehicle)["id"])
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    make_plan(
        db,
        driver,
        CompensationMethod.DAILY_WAGE,
        effective_from=local_today() - timedelta(days=30),
        daily_wage_amount="300",
    )
    day = local_today().isoformat()
    sid = client.post(
        "/api/v1/settlements",
        headers=acc,
        json={"driver_id": str(driver.id), "period_start": day, "period_end": day},
    ).json()["id"]
    assert client.post(f"/api/v1/settlements/{sid}/review", headers=acc).status_code == 200
    assert client.post(f"/api/v1/settlements/{sid}/finalize", headers=acc).status_code == 200
    res = client.post(
        f"{API}/cash/closeouts/{closeout['id']}/void", headers=acc, json={"reason": "خطأ"}
    )
    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "period_settled"


# --- Security audit L4: a day-off and a shift start cannot race --------------------------


def test_day_off_takes_the_driver_lock_that_shift_start_takes(
    client: TestClient, db: Session
) -> None:
    """Shift start locks the driver row; registering a day-off must lock it too,
    so the two serialise and the second sees the first (no shift on a day off)."""
    from sqlalchemy import event

    from app.core.db import engine

    _, _, h, _ = make_driver_account(client, db)
    seen: list[str] = []

    def capture(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        res = client.post(f"{DA}/day-off", headers=h, json={})
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert res.status_code == 201, res.text
    assert any("FROM drivers" in s and "FOR UPDATE" in s for s in seen)
