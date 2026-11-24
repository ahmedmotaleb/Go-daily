"""Driver app version policy (U43/U44): update notices, never cut off mid-shift."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from tests.factories import fuel_type_id, make_driver_account, start_photo
from tests.test_driver_cash import CLOSE

DA = "/api/v1/driver"


@pytest.fixture()
def policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "driver_app_min_version", 5)
    monkeypatch.setattr(get_settings(), "driver_app_recommended_version", 8)


def _start(client: TestClient, h: dict[str, str], vehicle: object, version: str | None) -> int:
    headers = {**h, **({"X-App-Version": version} if version is not None else {})}
    res = client.post(
        f"{DA}/shifts/start",
        headers=headers,
        json={
            "vehicle_id": str(vehicle.id),  # type: ignore[attr-defined]
            "start_odometer_km": 50_000,
            "start_odometer_photo_id": start_photo(client, h),
        },
    )
    return res.status_code


def test_status_is_reported(client: TestClient, db: Session, policy: None) -> None:
    _, _, h, _ = make_driver_account(client, db)
    for version, expected in (("3", "UPDATE_REQUIRED"), ("6", "UPDATE_RECOMMENDED"), ("8", "OK")):
        me = client.get(f"{DA}/me", headers={**h, "X-App-Version": version}).json()
        assert me["app_update"]["status"] == expected
        assert me["app_update"]["minimum_version"] == 5
    # Builds that send no version count as version 0.
    assert client.get(f"{DA}/me", headers=h).json()["app_update"]["status"] == "UPDATE_REQUIRED"


def test_outdated_app_cannot_start_a_new_shift(
    client: TestClient, db: Session, policy: None
) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    res_code = _start(client, h, vehicle, "4")
    assert res_code == 426
    assert _start(client, h, vehicle, "6") == 201  # recommended only: allowed


def test_running_shift_is_never_interrupted(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    assert _start(client, h, vehicle, "4") == 201  # no policy yet
    shift = client.get(f"{DA}/me", headers=h).json()["active_shift"]
    # The minimum is raised while the shift runs: everything for that shift keeps working.
    monkeypatch.setattr(get_settings(), "driver_app_min_version", 5)
    old = {**h, "X-App-Version": "4"}
    fuel = client.post(
        f"{DA}/fuel",
        headers=old,
        json={"fuel_type_id": fuel_type_id(db, "CNG"), "quantity": "20", "total_amount": "200"},
    )
    assert fuel.status_code == 201, fuel.text
    close = client.post(f"{DA}/shifts/{shift['id']}/closeout", headers=old, json=CLOSE)
    assert close.status_code == 201, close.text
