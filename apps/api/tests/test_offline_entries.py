"""Offline financial entries (U45) and device time (U46)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.cash import ShiftCloseout
from app.models.finance import FuelTransaction
from app.services import clock
from tests.factories import fuel_type_id, make_driver_account
from tests.test_driver_cash import CLOSE, _close, _start

DA = "/api/v1/driver"


def _fuel(db: Session, **extra: Any) -> dict[str, Any]:
    return {
        "fuel_type_id": fuel_type_id(db, "CNG"),
        "quantity": "20",
        "total_amount": "200",
        **extra,
    }


def _count(db: Session, client_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(FuelTransaction)
            .where(FuelTransaction.client_entry_id == client_id)
        )
        or 0
    )


def test_a_resent_fuel_entry_is_recorded_once(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle)
    cid = str(uuid.uuid4())
    body = _fuel(db, client_entry_id=cid, shift_id=shift["id"])
    first = client.post(f"{DA}/fuel", headers=h, json=body)
    assert first.status_code == 201, first.text
    # No Idempotency-Key, or a new one (e.g. after the 7-day key retention):
    # the client entry id alone recognises the entry.
    again = client.post(f"{DA}/fuel", headers={**h, "Idempotency-Key": "other-key-1"}, json=body)
    assert again.status_code == 201
    assert again.json()["id"] == first.json()["id"]
    assert _count(db, cid) == 1


def test_a_queued_entry_is_accepted_after_the_shift_ended(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle)
    recorded = utcnow()
    _close(client, h, shift["id"])
    cid = str(uuid.uuid4())
    res = client.post(
        f"{DA}/fuel",
        headers=h,
        json=_fuel(db, client_entry_id=cid, shift_id=shift["id"], recorded_at=recorded.isoformat()),
    )
    assert res.status_code == 201, res.text
    tx = db.scalar(select(FuelTransaction).where(FuelTransaction.client_entry_id == cid))
    assert tx is not None and str(tx.shift_id) == shift["id"]
    # Inside the shift: the phone's time is the entry's time, kept as sent.
    assert tx.device_recorded_at == recorded and tx.occurred_at == recorded

    # Without a shift id the entry still needs a running shift.
    live = client.post(f"{DA}/fuel", headers=h, json=_fuel(db))
    assert live.status_code == 409


def test_an_implausible_phone_time_is_kept_but_not_used(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle)
    future = utcnow() + timedelta(hours=3)
    cid = str(uuid.uuid4())
    res = client.post(
        f"{DA}/fuel",
        headers=h,
        json=_fuel(db, client_entry_id=cid, shift_id=shift["id"], recorded_at=future.isoformat()),
    )
    assert res.status_code == 201, res.text
    tx = db.scalar(select(FuelTransaction).where(FuelTransaction.client_entry_id == cid))
    assert tx is not None
    assert tx.device_recorded_at == future
    assert tx.occurred_at < future - timedelta(hours=2)  # server receive time


def test_entries_only_for_the_drivers_own_shift(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    _, _, other_h, other_vehicle = make_driver_account(client, db)
    other_shift = _start(client, other_h, other_vehicle)
    _start(client, h, vehicle)
    res = client.post(f"{DA}/fuel", headers=h, json=_fuel(db, shift_id=other_shift["id"]))
    assert res.status_code == 404
    bad = client.post(f"{DA}/fuel", headers=h, json=_fuel(db, client_entry_id="x y"))
    assert bad.status_code == 422


def test_a_resent_closeout_returns_the_same_record(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle)
    cid = str(uuid.uuid4())
    recorded = utcnow()
    first = _close(client, h, shift["id"], client_entry_id=cid, recorded_at=recorded.isoformat())
    again = client.post(
        f"{DA}/shifts/{shift['id']}/closeout",
        headers=h,
        json={**CLOSE, "client_entry_id": cid, "recorded_at": recorded.isoformat()},
    )
    assert again.status_code == 201, again.text
    assert again.json()["id"] == first["id"]
    row = db.get(ShiftCloseout, uuid.UUID(first["id"]))
    assert row is not None and row.device_recorded_at == recorded
    # A different entry for the same shift is still refused.
    other = client.post(
        f"{DA}/shifts/{shift['id']}/closeout",
        headers=h,
        json={**CLOSE, "client_entry_id": str(uuid.uuid4())},
    )
    assert other.status_code == 409


def test_entry_time_rules() -> None:
    now = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
    start, end = now - timedelta(hours=8), now - timedelta(hours=1)

    def at(t: datetime | None) -> clock.EntryTime:
        return clock.entry_time(t, received_at=now, window_start=start, window_end=end)

    assert at(None) == clock.EntryTime(now, False)
    assert at(now - timedelta(hours=2)) == clock.EntryTime(now - timedelta(hours=2), True)
    assert at(now + timedelta(hours=1)).device_time_used is False  # future
    assert at(start - timedelta(hours=1)).device_time_used is False  # before the shift
    assert at(end + timedelta(minutes=30)).device_time_used is False  # after the shift
    assert at(end + timedelta(minutes=5)).device_time_used is True  # within tolerance


def test_unused_phone_times_are_flagged_for_review(client: TestClient, db: Session) -> None:
    from app.services import exception_rules as rules
    from tests.test_exceptions import codes, ctx_around

    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle)
    good, bad = str(uuid.uuid4()), str(uuid.uuid4())
    for cid, at in ((good, utcnow()), (bad, utcnow() + timedelta(hours=3))):
        res = client.post(
            f"{DA}/fuel",
            headers=h,
            json=_fuel(db, client_entry_id=cid, shift_id=shift["id"], recorded_at=at.isoformat()),
        )
        assert res.status_code == 201, res.text
    found = rules.entry_device_time(ctx_around(db))
    assert codes(found) == ["ENTRY_DEVICE_TIME"]
    case = found.candidates[0]
    assert case.evidence["difference_minutes"] > 170
    bad_tx = db.scalar(select(FuelTransaction).where(FuelTransaction.client_entry_id == bad))
    assert bad_tx is not None and case.subject_id == bad_tx.id
