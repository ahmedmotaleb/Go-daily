"""Idempotency-Key on the driver-app writes that had none (retry after a lost response)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.attachment import Attachment, AttachmentOwner
from tests.factories import (
    fuel_type_id,
    make_driver_account,
    make_route,
    operation_type_id,
    start_photo,
)
from tests.test_driver_cash import _close, _start

DA = "/api/v1/driver"
PNG = b"\x89PNG\r\n\x1a\n" + b"i" * 90
OTHER_PNG = b"\x89PNG\r\n\x1a\n" + b"j" * 90


def _key() -> dict[str, str]:
    return {"Idempotency-Key": f"test-{uuid.uuid4()}"}


def _png(data: bytes = PNG, name: str = "photo.png") -> dict[str, Any]:
    return {"file": (name, data, "image/png")}


def _attachments(db: Session, owner: AttachmentOwner, owner_id: Any) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Attachment)
            .where(Attachment.owner_type == owner, Attachment.owner_id == owner_id)
        )
        or 0
    )


def test_session_end_retry_returns_the_first_result(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle)
    school = make_route(db, code="SCHOOL_ROUTE", name="مدرسة")
    session = client.post(
        f"{DA}/shifts/{shift['id']}/sessions",
        headers=h,
        json={
            "operation_type_id": operation_type_id(db, "SCHOOL_ROUTE"),
            "route_id": str(school.id),
        },
    ).json()
    key = {**h, **_key()}
    first = client.post(f"{DA}/sessions/{session['id']}/end", headers=key)
    assert first.status_code == 200, first.text
    # Without the key a second end is refused; with it, it is a replay.
    replay = client.post(f"{DA}/sessions/{session['id']}/end", headers=key)
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert client.post(f"{DA}/sessions/{session['id']}/end", headers=h).status_code == 409


def test_day_off_cancel_retry_returns_the_first_result(client: TestClient, db: Session) -> None:
    _, _, h, _ = make_driver_account(client, db)
    assert client.post(f"{DA}/day-off", headers=h, json={}).status_code == 201
    key = {**h, **_key()}
    first = client.post(f"{DA}/day-off/cancel", headers=key)
    assert first.status_code == 200, first.text
    replay = client.post(f"{DA}/day-off/cancel", headers=key)
    assert replay.status_code == 200 and replay.json() == first.json()


def test_odometer_photo_retry_uploads_once(client: TestClient, db: Session) -> None:
    driver, _, h, _ = make_driver_account(client, db)
    key = {**h, **_key()}
    before = _attachments(db, AttachmentOwner.DRIVER, driver.id)
    first = client.post(f"{DA}/odometer-photo", headers=key, files=_png())
    assert first.status_code == 201, first.text
    replay = client.post(f"{DA}/odometer-photo", headers=key, files=_png())
    assert replay.status_code == 201
    assert replay.json()["attachment_id"] == first.json()["attachment_id"]
    assert _attachments(db, AttachmentOwner.DRIVER, driver.id) == before + 1

    # The same key with another photo is a different request, not a replay.
    other = client.post(f"{DA}/odometer-photo", headers=key, files=_png(OTHER_PNG))
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "idempotency_key_reused"


def test_closeout_receipt_retry_uploads_once(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    out = _close(client, h, _start(client, h, vehicle)["id"])
    key = {**h, **_key()}
    url = f"{DA}/closeouts/{out['id']}/receipt"
    first = client.post(url, headers=key, files=_png(name="receipt.png"))
    assert first.status_code == 201, first.text
    replay = client.post(url, headers=key, files=_png(name="receipt.png"))
    assert replay.json()["attachment_id"] == first.json()["attachment_id"]
    assert _attachments(db, AttachmentOwner.SHIFT_CLOSEOUT, uuid.UUID(out["id"])) == 1


def test_fuel_receipt_retry_uploads_once(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    client.post(
        f"{DA}/shifts/start",
        headers=h,
        json={
            "vehicle_id": str(vehicle.id),
            "start_odometer_km": 50_000,
            "start_odometer_photo_id": start_photo(client, h),
        },
    )
    entry = client.post(
        f"{DA}/fuel",
        headers=h,
        json={"fuel_type_id": fuel_type_id(db, "CNG"), "quantity": "10", "total_amount": "70"},
    ).json()
    key = {**h, **_key()}
    url = f"{DA}/fuel/{entry['id']}/receipt"
    first = client.post(url, headers=key, files=_png(name="receipt.png"))
    assert first.status_code == 201, first.text
    replay = client.post(url, headers=key, files=_png(name="receipt.png"))
    assert replay.status_code == 201
    assert replay.json()["attachment"]["id"] == first.json()["attachment"]["id"]
    assert _attachments(db, AttachmentOwner.FUEL_TRANSACTION, uuid.UUID(entry["id"])) == 1


def test_a_key_is_never_replayed_for_another_driver(client: TestClient, db: Session) -> None:
    _, _, h, _ = make_driver_account(client, db)
    _, _, other_h, _ = make_driver_account(client, db)
    shared = _key()
    mine = client.post(f"{DA}/odometer-photo", headers={**h, **shared}, files=_png())
    theirs = client.post(f"{DA}/odometer-photo", headers={**other_h, **shared}, files=_png())
    assert mine.status_code == theirs.status_code == 201
    assert mine.json()["attachment_id"] != theirs.json()["attachment_id"]


# --- Security audit M9 (runtime L5): the key is required and claimed atomically ---------

NO_KEY = {"X-Test-No-Idempotency-Key": "1"}  # conftest: do not add a key to this request


def test_driver_writes_require_an_idempotency_key(client: TestClient, db: Session) -> None:
    _, _, h, _ = make_driver_account(client, db)
    res = client.post(f"{DA}/day-off", headers={**h, **NO_KEY}, json={})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "idempotency_key_required"
    photo = client.post(f"{DA}/odometer-photo", headers={**h, **NO_KEY}, files=_png())
    assert photo.json()["error"]["code"] == "idempotency_key_required"


def test_a_crash_after_the_action_never_lets_a_retry_run_it_twice(
    client: TestClient, db: Session, monkeypatch: Any
) -> None:
    import pytest
    from fastapi.encoders import jsonable_encoder as real

    from app.schemas.driver_app import DriverFuelOut

    _, _, h, vehicle = make_driver_account(client, db)
    _start(client, h, vehicle)
    body = {"fuel_type_id": fuel_type_id(db, "CNG"), "quantity": "5", "total_amount": "35"}
    key = _key()

    def crash_on_result(obj: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(obj, DriverFuelOut):
            raise RuntimeError("process died before the response was stored")
        return real(obj, *args, **kwargs)

    monkeypatch.setattr("app.services.idempotency.jsonable_encoder", crash_on_result)
    with pytest.raises(RuntimeError):
        client.post(f"{DA}/fuel", headers={**h, **key}, json=body)
    monkeypatch.undo()

    retry = client.post(f"{DA}/fuel", headers={**h, **key}, json=body)
    assert retry.status_code == 409, retry.text
    assert retry.json()["error"]["code"] == "request_in_progress"
    mine = client.get(f"{DA}/fuel", headers=h).json()
    assert len([f for f in mine if f["total_amount"] in ("35", "35.00")]) == 1
