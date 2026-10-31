"""Attachment storage, validation, access control and deletion policy (Task 24)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import UserRole
from app.core.storage import LocalStorage, S3Storage, StorageError, sniff_content_type
from app.core.time import utcnow
from tests.factories import fuel_type_id, login_as, make_driver_account, make_vehicle

JPEG = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF" + b"x" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"y" * 100
PDF = b"%PDF-1.7\n" + b"z" * 100


def _fuel(client: TestClient, h: dict[str, str], db: Session, **extra: object) -> Any:
    res = client.post(
        "/api/v1/fuel",
        json={
            "vehicle_id": str(make_vehicle(db).id),
            "fuel_type_id": fuel_type_id(db, "CNG"),
            "quantity": "10",
            "total_amount": "70",
            "occurred_at": (utcnow() - timedelta(hours=1)).isoformat(),
            **extra,
        },
        headers=h,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _upload(
    client: TestClient,
    h: dict[str, str],
    owner_id: str,
    data: bytes,
    name: str = "receipt.jpg",
    owner_type: str = "fuel_transaction",
) -> Any:
    return client.post(
        "/api/v1/attachments",
        data={"owner_type": owner_type, "owner_id": owner_id},
        files={"file": (name, data, "application/octet-stream")},
        headers=h,
    )


def test_upload_list_and_download_through_the_api(
    client: TestClient, db: Session, _isolated_storage: LocalStorage
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    tx = _fuel(client, h, db)
    res = _upload(client, h, tx["id"], JPEG, name="../../etc/فاتورة<1>.png")
    assert res.status_code == 201, res.text
    body = res.json()
    att = body["attachment"]
    assert att["content_type"] == "image/jpeg"  # from the bytes, not the name or header
    assert att["original_filename"] == "فاتورة1.jpg"  # path and unsafe characters dropped
    assert att["kind"] == "FUEL_RECEIPT"
    assert att["uploaded_by"]["full_name"]
    assert body["duplicates"] == []

    listed = client.get(
        "/api/v1/attachments",
        params={"owner_type": "fuel_transaction", "owner_id": tx["id"]},
        headers=h,
    ).json()
    assert [a["id"] for a in listed] == [att["id"]]
    content = client.get(f"/api/v1/attachments/{att['id']}/content", headers=h)
    assert content.status_code == 200
    assert content.content == JPEG
    assert content.headers["content-type"] == "image/jpeg"
    assert content.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in content.headers["content-security-policy"]
    # The object key is server-made and stays inside the storage root.
    stored = list(_isolated_storage.root.rglob("*.jpg"))
    assert len(stored) == 1 and stored[0].name != "receipt.jpg"


def test_type_and_size_are_validated(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    tx = _fuel(client, h, db)
    html = _upload(client, h, tx["id"], b"<html><script>alert(1)</script>", name="x.jpg")
    assert html.status_code == 422
    assert html.json()["error"]["code"] == "file_type"
    svg = _upload(client, h, tx["id"], b"<svg xmlns='http://www.w3.org/2000/svg'/>", name="a.svg")
    assert svg.status_code == 422
    assert _upload(client, h, tx["id"], PDF, name="statement.pdf").status_code == 201
    monkeypatch.setattr(get_settings(), "attachment_max_bytes", 50)
    big = _upload(client, h, tx["id"], PNG)
    assert big.status_code == 422
    assert big.json()["error"]["code"] == "file_too_large"


def test_identical_files_are_reported_as_possible_duplicates(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    first = _fuel(client, h, db)
    second = _fuel(client, h, db)
    _upload(client, h, first["id"], JPEG)
    res = _upload(client, h, second["id"], JPEG).json()
    assert [d["owner_id"] for d in res["duplicates"]] == [first["id"]]


def test_access_follows_the_owning_record(client: TestClient, db: Session) -> None:
    _, accountant = login_as(client, db, UserRole.ACCOUNTANT)
    tx = _fuel(client, accountant, db)
    att = _upload(client, accountant, tx["id"], JPEG).json()["attachment"]
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    # Operations can read fuel but not write it.
    assert client.get(f"/api/v1/attachments/{att['id']}/content", headers=ops).status_code == 200
    assert _upload(client, ops, tx["id"], PNG).status_code == 403
    _, _, driver_h, _ = make_driver_account(client, db)
    assert (
        client.get(f"/api/v1/attachments/{att['id']}/content", headers=driver_h).status_code == 403
    )
    missing = _upload(client, accountant, "00000000-0000-0000-0000-000000000000", PNG)
    assert missing.status_code == 404


def test_evidence_on_approved_records_cannot_change(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.ACCOUNTANT)
    tx = _fuel(client, h, db)
    att = _upload(client, h, tx["id"], JPEG).json()["attachment"]
    other = _upload(client, h, tx["id"], PNG).json()["attachment"]
    deleted = client.post(
        f"/api/v1/attachments/{other['id']}/delete", json={"reason": "صورة خاطئة"}, headers=h
    ).json()
    assert deleted["deleted_at"] is not None
    gone = client.get(f"/api/v1/attachments/{other['id']}/content", headers=h)
    assert gone.status_code == 404

    client.post(f"/api/v1/fuel/{tx['id']}/approve", json={}, headers=h)
    locked = client.post(
        f"/api/v1/attachments/{att['id']}/delete", json={"reason": "محاولة"}, headers=h
    )
    assert locked.status_code == 409
    assert _upload(client, h, tx["id"], PDF).status_code == 409


def test_driver_can_attach_a_receipt_to_own_entry(client: TestClient, db: Session) -> None:
    _, _, h, vehicle = make_driver_account(client, db)
    client.post(
        "/api/v1/driver/shifts/start",
        json={"vehicle_id": str(vehicle.id), "start_odometer_km": 50_000},
        headers=h,
    )
    entry = client.post(
        "/api/v1/driver/fuel",
        json={"fuel_type_id": fuel_type_id(db, "CNG"), "quantity": "10", "total_amount": "70"},
        headers=h,
    ).json()
    res = client.post(
        f"/api/v1/driver/fuel/{entry['id']}/receipt",
        files={"file": ("receipt.jpg", JPEG, "image/jpeg")},
        headers=h,
    )
    assert res.status_code == 201, res.text
    _, _, other_h, _ = make_driver_account(client, db)
    foreign = client.post(
        f"/api/v1/driver/fuel/{entry['id']}/receipt",
        files={"file": ("receipt.jpg", JPEG, "image/jpeg")},
        headers=other_h,
    )
    assert foreign.status_code == 404


def test_sniffing_and_keys() -> None:
    assert sniff_content_type(JPEG) == "image/jpeg"
    assert sniff_content_type(PNG) == "image/png"
    assert sniff_content_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_content_type(PDF) == "application/pdf"
    assert sniff_content_type(b"GIF89a") is None
    storage = LocalStorage("unused-root")
    for bad in ("../etc/passwd.txt", "/abs/path.jpg", "a/../../b.jpg", "UPPER/x.jpg", "noext"):
        with pytest.raises(StorageError):
            storage._path(bad)


def test_s3_backend_round_trip_with_private_objects() -> None:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="go-daily-test")
        storage = S3Storage("go-daily-test", client, prefix="/attachments/")
        storage.put("fuel_transaction/2026/03/abc.jpg", JPEG, "image/jpeg")
        assert storage.get("fuel_transaction/2026/03/abc.jpg") == JPEG
        head = client.head_object(
            Bucket="go-daily-test", Key="attachments/fuel_transaction/2026/03/abc.jpg"
        )
        assert head["ContentType"] == "image/jpeg"
        acl = client.get_object_acl(
            Bucket="go-daily-test", Key="attachments/fuel_transaction/2026/03/abc.jpg"
        )
        assert all(g["Grantee"].get("URI") is None for g in acl["Grants"])  # no public grants
        storage.delete("fuel_transaction/2026/03/abc.jpg")
        with pytest.raises(StorageError):
            storage.get("fuel_transaction/2026/03/abc.jpg")
