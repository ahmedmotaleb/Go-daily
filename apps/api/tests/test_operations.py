from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from tests.factories import login_as, operation_type_id

R = "/api/v1/routes"


def _route_body(db: Session, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "name": "موقف المنصورة ⇄ الجامعة",
        "operation_type_id": operation_type_id(db, "FIXED_ROUTE"),
        "trip_pattern": "ROUND_TRIP",
        "origin": {
            "name": "الموقف",
            "latitude": "31.040900",
            "longitude": "31.378500",
            "radius_m": 120,
        },
        "destination": {"name": "بوابة الجامعة", "latitude": "31.043800", "longitude": "31.352100"},
        "intermediate_stops": [{"name": "ميدان المحافظة"}],
        "expected_distance_km": "7.5",
        "window_start": "06:30:00",
        "window_end": "18:00:00",
        "operating_days": [6, 7, 1, 2, 3, 3],
    }
    body.update(overrides)
    return body


def test_operation_types_seeded_with_kinds(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    types = client.get("/api/v1/operation-types", headers=h).json()
    by_code = {t["code"]: t for t in types}
    assert set(by_code) >= {
        "RIDE_HAILING",
        "FIXED_ROUTE",
        "SCHOOL_ROUTE",
        "PRIVATE_TRIP",
        "EMPLOYEE_TRANSPORT",
        "OTHER",
    }
    assert by_code["SCHOOL_ROUTE"]["name_ar"] == "دورة مدرسة"
    assert by_code["FIXED_ROUTE"]["uses_routes"] is True
    assert by_code["RIDE_HAILING"]["uses_routes"] is False


def test_custom_operation_type_reuses_a_kind(client: TestClient, db: Session) -> None:
    _, admin = login_as(client, db, UserRole.ADMIN)
    _, ops = login_as(client, db, UserRole.OPERATIONS)
    body = {"code": "factory_shuttle", "kind": "EMPLOYEE_TRANSPORT", "name_ar": "نقل عمال المصنع"}
    assert client.post("/api/v1/operation-types", headers=ops, json=body).status_code == 403
    res = client.post("/api/v1/operation-types", headers=admin, json=body)
    assert res.status_code == 201
    assert res.json()["uses_routes"] is True


def test_create_route_with_ordered_stops(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    res = client.post(R, headers=h, json=_route_body(db))
    assert res.status_code == 201, res.text
    route = res.json()
    assert [(s["sequence"], s["kind"], s["name"]) for s in route["stops"]] == [
        (1, "ORIGIN", "الموقف"),
        (2, "INTERMEDIATE", "ميدان المحافظة"),
        (3, "DESTINATION", "بوابة الجامعة"),
    ]
    assert route["stops"][0]["radius_m"] == 120
    assert route["operating_days"] == [1, 2, 3, 6, 7]
    assert route["operation_type"]["code"] == "FIXED_ROUTE"


def test_route_validation(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    half_coords = _route_body(db, origin={"name": "x", "latitude": "31.0"})
    assert client.post(R, headers=h, json=half_coords).status_code == 422
    bad_days = _route_body(db, operating_days=[0, 8])
    assert client.post(R, headers=h, json=bad_days).status_code == 422
    half_window = _route_body(db, window_end=None)
    assert client.post(R, headers=h, json=half_window).status_code == 422


def test_update_route_stops_keeps_stop_ids(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    route = client.post(R, headers=h, json=_route_body(db)).json()
    origin_id = route["stops"][0]["id"]
    res = client.patch(
        f"{R}/{route['id']}",
        headers=h,
        json={"intermediate_stops": [], "destination": {"name": "البوابة الخلفية"}},
    )
    assert res.status_code == 200, res.text
    stops = res.json()["stops"]
    assert [s["name"] for s in stops] == ["الموقف", "البوابة الخلفية"]
    assert stops[0]["id"] == origin_id
    assert stops[1]["kind"] == "DESTINATION"


def test_route_activation_and_filters(client: TestClient, db: Session) -> None:
    _, h = login_as(client, db, UserRole.OPERATIONS)
    route = client.post(R, headers=h, json=_route_body(db, name="خط تجريبي")).json()
    assert client.post(f"{R}/{route['id']}/deactivate", headers=h).json()["is_active"] is False
    listing = client.get(R, headers=h, params={"q": "تجريبي", "is_active": False}).json()
    assert listing["total"] == 1


def test_route_permissions(client: TestClient, db: Session) -> None:
    _, acc = login_as(client, db, UserRole.ACCOUNTANT)
    assert client.get(R, headers=acc).status_code == 200
    assert client.post(R, headers=acc, json=_route_body(db)).status_code == 403
