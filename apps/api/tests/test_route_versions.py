"""Route versioning (U08): edits never rewrite historical evidence."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.core.time import local_today, utcnow
from app.models.operations import RouteStop, RouteVersion
from app.models.route_events import EventSource, RouteEvent, RouteEventType
from app.services import route_versions
from tests.factories import login_as, make_completed_shift, make_driver, make_vehicle
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


def test_a_stop_taken_off_a_route_is_kept_not_deleted(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    route = client.post(R, headers=h, json=_route_body(db)).json()
    middle = next(s for s in route["stops"] if s["kind"] == "INTERMEDIATE")
    # A route event recorded at the intermediate stop.
    driver, vehicle = make_driver(db), make_vehicle(db)
    shift = make_completed_shift(db, driver, vehicle, day=local_today() - timedelta(days=1))
    db.add(
        RouteEvent(
            session_id=shift.sessions[0].id,
            shift_id=shift.id,
            route_id=route["id"],
            vehicle_id=vehicle.id,
            stop_id=middle["id"],
            event_type=RouteEventType.ENTERED,
            occurred_at=utcnow() - timedelta(days=1),
            source=EventSource.AUTO,
            dedupe_key=f"{shift.sessions[0].id}:ENTERED:{middle['id']}",
        )
    )
    db.commit()

    # Taking the stop off the route used to delete it (and fail on the event's FK).
    res = client.patch(f"{R}/{route['id']}", headers=h, json={"intermediate_stops": []})
    assert res.status_code == 200, res.text
    assert [s["kind"] for s in res.json()["stops"]] == ["ORIGIN", "DESTINATION"]
    # Matched within their kind: origin and destination keep their ids.
    assert [s["id"] for s in res.json()["stops"]] == [
        route["stops"][0]["id"],
        route["stops"][-1]["id"],
    ]
    kept = db.get(RouteStop, uuid.UUID(middle["id"]))
    assert kept is not None and kept.removed_at is not None
    assert kept.name == middle["name"]  # the event still names the stop it was at

    # A stop added later at the same position is a new row (the order is
    # unique among current stops only).
    res = client.patch(
        f"{R}/{route['id']}", headers=h, json={"intermediate_stops": [{"name": "محطة جديدة"}]}
    )
    assert res.status_code == 200, res.text
    new_middle = res.json()["stops"][1]
    assert new_middle["name"] == "محطة جديدة" and new_middle["id"] != middle["id"]
    rows = db.scalars(select(RouteStop).where(RouteStop.route_id == uuid.UUID(route["id"]))).all()
    assert len(rows) == 4 and sum(r.removed_at is not None for r in rows) == 1
