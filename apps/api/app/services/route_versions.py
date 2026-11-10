"""Route versioning (U08): immutable snapshots of route definitions.

Creating a route stores version 1; every edit that changes it stores the
next version, effective from that moment. Route events record the version
in force when they happened (`version_at`), so later edits never rewrite
what past loops, legs and review cases were measured against.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.operations import RouteDefinition, RouteVersion
from app.models.user import User
from app.services import audit


def snapshot(route: RouteDefinition) -> dict[str, Any]:
    data = {
        "name": route.name,
        "trip_pattern": route.trip_pattern.value,
        "expected_distance_km": route.expected_distance_km,
        "expected_duration_minutes": route.expected_duration_minutes,
        "window_start": route.window_start,
        "window_end": route.window_end,
        "operating_days": route.operating_days,
        "stops": [
            {
                "id": s.id,
                "sequence": s.sequence,
                "kind": s.kind.value,
                "name": s.name,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "radius_m": s.radius_m,
            }
            for s in sorted(route.stops, key=lambda s: s.sequence)
        ],
    }
    result: dict[str, Any] = audit.to_jsonable(data)
    return result


def record(db: Session, route: RouteDefinition, actor: User | None) -> RouteVersion:
    """Store the route as it is now as its next version."""
    number = (
        db.scalar(select(func.max(RouteVersion.version)).where(RouteVersion.route_id == route.id))
        or 0
    ) + 1
    version = RouteVersion(
        route_id=route.id,
        version=number,
        effective_from=utcnow(),
        snapshot=snapshot(route),
        created_by_id=actor.id if actor else None,
    )
    db.add(version)
    db.flush()
    return version


def version_at(db: Session, route_id: uuid.UUID, at: datetime) -> int | None:
    """The version in force at `at` (the first one for times before it existed)."""
    found = db.scalar(
        select(RouteVersion.version)
        .where(RouteVersion.route_id == route_id, RouteVersion.effective_from <= at)
        .order_by(RouteVersion.version.desc())
        .limit(1)
    )
    if found is not None:
        return int(found)
    first = db.scalar(
        select(func.min(RouteVersion.version)).where(RouteVersion.route_id == route_id)
    )
    return int(first) if first is not None else None


def history(db: Session, route_id: uuid.UUID) -> list[RouteVersion]:
    return list(
        db.scalars(
            select(RouteVersion)
            .where(RouteVersion.route_id == route_id)
            .order_by(RouteVersion.version.desc())
        ).all()
    )


__all__ = ["history", "record", "snapshot", "version_at"]
