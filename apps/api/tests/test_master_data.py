"""Master data management (U48): deactivate, never delete; notification rules."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today
from app.models.audit import AuditLog
from app.models.notifications import Notification
from app.services import notifications
from tests.factories import login_as, make_vehicle

MASTER_LISTS = (
    ("/api/v1/operation-types", {"code": "SHUTTLE_X", "kind": "PRIVATE_TRIP", "name_ar": "نقل"}),
    ("/api/v1/vehicle-types", {"code": "VAN_X", "name_ar": "فان"}),
    ("/api/v1/expense-categories", {"code": "WASH_X", "name_ar": "غسيل", "pnl_group": "OTHER"}),
    (
        "/api/v1/fuel-types",
        {
            "code": "COOLANT_X",
            "name_ar": "مياه تبريد",
            "category": "CONSUMABLE",
            "default_unit": "LITER",
        },
    ),
    ("/api/v1/maintenance/types", {"code": "WIPERS_X", "name_ar": "مساحات", "interval_days": 180}),
)


def test_master_lists_are_deactivated_never_deleted(client: TestClient, db: Session) -> None:
    _, admin = login_as(client, db, UserRole.SUPER_ADMIN)
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    for url, body in MASTER_LISTS:
        created = client.post(url, headers=admin, json=body)
        assert created.status_code == 201, (url, created.text)
        item = created.json()
        path = f"{url}/{item['id']}"
        # There is no delete: history keeps pointing at the item.
        assert client.delete(path, headers=admin).status_code == 405, url
        # Only settings managers change master data.
        assert client.patch(path, headers=ops, json={"is_active": False}).status_code == 403, url
        renamed = client.patch(
            path, headers=admin, json={"name_ar": "اسم جديد", "is_active": False}
        )
        assert renamed.status_code == 200, (url, renamed.text)
        listed = {x["id"] for x in client.get(url, headers=admin).json()}
        assert item["id"] not in listed, url
        everything = client.get(url, headers=admin, params={"include_inactive": True}).json()
        assert item["id"] in {x["id"] for x in everything}, url
        assert db.scalar(select(AuditLog.id).where(AuditLog.entity_id == item["id"])), url


def test_a_maintenance_type_names_its_consumable(client: TestClient, db: Session) -> None:
    _, admin = login_as(client, db, UserRole.SUPER_ADMIN)
    types = client.get("/api/v1/fuel-types", headers=admin).json()
    oil = next(t["id"] for t in types if t["code"] == "ENGINE_OIL")
    cng = next(t["id"] for t in types if t["code"] == "CNG")
    url = "/api/v1/maintenance/types"
    created = client.post(
        url,
        headers=admin,
        json={"code": "GEARBOX_OIL_X", "name_ar": "زيت فتيس", "consumable_type_id": oil},
    ).json()
    assert created["consumable_type_id"] == oil
    # Fuel is not a consumable a service uses.
    bad = client.patch(f"{url}/{created['id']}", headers=admin, json={"consumable_type_id": cng})
    assert bad.status_code == 422


def _open(db: Session, kind: str) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(Notification.kind == kind, Notification.cleared_at.is_(None))
        ).all()
    )


def test_notification_kinds_can_be_turned_off_by_policy(client: TestClient, db: Session) -> None:
    _, admin = login_as(client, db, UserRole.SUPER_ADMIN)
    make_vehicle(db, license_expiry=local_today() + timedelta(days=5))
    notifications.generate(db)
    assert _open(db, "VEHICLE_DOCUMENT")

    off = client.post(
        "/api/v1/policies",
        headers=admin,
        json={"changes": {"notify_vehicle_document": 0}, "reason": "تُتابع من نظام آخر"},
    )
    assert off.status_code == 200, off.text
    toggle = next(v for v in off.json()["values"] if v["key"] == "notify_vehicle_document")
    assert toggle["toggle"] is True and toggle["value"] == 0
    outcome = notifications.generate(db)
    assert outcome["results"]["VEHICLE_DOCUMENT"]["enabled"] is False
    assert _open(db, "VEHICLE_DOCUMENT") == []  # cleared, not deleted

    for bad in (2, 0.5):
        res = client.post(
            "/api/v1/policies",
            headers=admin,
            json={"changes": {"notify_vehicle_document": bad}, "reason": "قيمة خاطئة"},
        )
        assert res.status_code == 422, bad

    client.post(
        "/api/v1/policies",
        headers=admin,
        json={"changes": {"notify_vehicle_document": None}, "reason": "إعادة التشغيل"},
    )
    notifications.generate(db)
    assert _open(db, "VEHICLE_DOCUMENT")  # the same condition is active again
