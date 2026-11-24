"""Operational metrics and error counters (U37/U38)."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core import monitoring
from app.core.config import get_settings
from app.core.storage import StorageError
from app.services import attachments as attachments_service
from tests.factories import fuel_type_id, make_driver_account
from tests.test_driver_cash import _start

H = {"Authorization": "Bearer scrape-secret"}


def _scrape(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(get_settings(), "metrics_token", SecretStr("scrape-secret"))
    res = client.get("/metrics", headers=H)
    assert res.status_code == 200
    return res.text


def test_new_gauges_and_bounded_labels(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    shift = _start(client, h, vehicle)
    client.post(
        "/api/v1/driver/fuel",
        headers=h,
        json={"fuel_type_id": fuel_type_id(db, "CNG"), "quantity": "20", "total_amount": "200"},
    )
    body = _scrape(client, monkeypatch)
    for name in (
        "godaily_migrations_current 1",
        "godaily_gps_points_per_minute",
        "godaily_gps_points_rejected_5m",
        'godaily_gps_sync_lag_seconds{stat="max"}',
        "godaily_device_pending_points",
        "godaily_loop_detections_1h",
        'godaily_submissions_today{kind="fuel"}',
        "godaily_errors_total",
    ):
        assert name in body, name
    fuel_today = re.search(r'godaily_submissions_today\{kind="fuel"\} (\d+)', body)
    assert fuel_today is not None and int(fuel_today.group(1)) >= 1
    # Label values are fixed words or route templates: never ids or coordinates.
    labels = re.findall(r'="([^"]*)"', body)
    assert shift["id"] not in body
    assert not any(re.fullmatch(r"-?\d+\.\d{3,}", v) for v in labels)
    assert not any(k in body for k in ("latitude", "longitude", 'lat="', 'lon="'))


def test_errors_are_counted_by_component(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monitoring.reset_counts()

    class Broken:
        def put(self, key: str, data: bytes, content_type: str) -> None:
            raise StorageError("bucket unreachable")

    _, _, h, _ = make_driver_account(client, db)
    monkeypatch.setattr(attachments_service, "get_storage", Broken)
    res = client.post(
        "/api/v1/driver/odometer-photo",
        headers=h,
        files={"file": ("odo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")},
    )
    assert res.status_code == 422
    assert monitoring.error_counts().get("storage") == 1
    assert 'godaily_errors_total{component="storage"} 1' in _scrape(client, monkeypatch)
