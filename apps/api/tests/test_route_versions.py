"""Route versioning (U08): edits never rewrite historical evidence."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import utcnow
from app.models.operations import RouteVersion
from app.services import route_versions
from tests.factories import login_as
from tests.test_operations import R, _route_body


def test_each_edit_is_a_new_immutable_version(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    route = client.post(R, headers=h, json=_route_body(db)).json()
    first = client.get(f"{R}/{route['id']}/versions", headers=h).json()
    assert [v["version"] for v in first] == [1]
    v1_origin = first[0]["snapshot"]["stops"][0]
    assert v1_origin["latitude"] == "31.040900" and v1_origin["radius_m"] == 120

    # Move the origin: a new version; version 1 still shows the old place.
    res = client.patch(
        f"{R}/{route['id']}",
        headers=h,
        json={
            "origin": {"name": "الموقف الجديد", "latitude": "31.050000", "longitude": "31.380000"}
        },
    )
    assert res.status_code == 200, res.text
    versions = client.get(f"{R}/{route['id']}/versions", headers=h).json()
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[0]["snapshot"]["stops"][0]["name"] == "الموقف الجديد"
    assert versions[1]["snapshot"]["stops"][0]["latitude"] == "31.040900"
    # The stop keeps its id across versions (events still point to it).
    assert versions[0]["snapshot"]["stops"][0]["id"] == v1_origin["id"]
    assert versions[0]["created_by"]

    # A save without changes does not create a version.
    client.patch(f"{R}/{route['id']}", headers=h, json={"name": route["name"]})
    assert len(client.get(f"{R}/{route['id']}/versions", headers=h).json()) == 2


def test_events_get_the_version_in_force_when_they_happened(
    client: TestClient, db: Session
) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    route = client.post(R, headers=h, json=_route_body(db)).json()
    client.patch(f"{R}/{route['id']}", headers=h, json={"expected_distance_km": "8.0"})
    # Version 1 was in force until an hour ago, version 2 since.
    db.execute(
        update(RouteVersion)
        .where(RouteVersion.route_id == route["id"], RouteVersion.version == 1)
        .values(effective_from=utcnow() - timedelta(days=2))
    )
    db.execute(
        update(RouteVersion)
        .where(RouteVersion.route_id == route["id"], RouteVersion.version == 2)
        .values(effective_from=utcnow() - timedelta(hours=1))
    )
    db.commit()
    rid = route["id"]
    assert route_versions.version_at(db, rid, utcnow() - timedelta(days=1)) == 1
    assert route_versions.version_at(db, rid, utcnow()) == 2
    # Before the route existed: its first definition.
    assert route_versions.version_at(db, rid, utcnow() - timedelta(days=30)) == 1
