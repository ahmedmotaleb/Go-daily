"""Operation types and route definitions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.models.operations import (
    OperationType,
    RouteDefinition,
    RouteStop,
    StopKind,
)
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.operations import (
    OperationTypeCreate,
    OperationTypeUpdate,
    RouteCreate,
    RouteUpdate,
    StopIn,
)
from app.services import audit
from app.services.common import apply_changes, like_pattern, paginate

ROUTE_AUDITED = (
    "name",
    "operation_type_id",
    "trip_pattern",
    "is_active",
    "expected_distance_km",
    "expected_duration_minutes",
    "window_start",
    "window_end",
    "operating_days",
    "notes",
)

# ------------------------------------------------------------------ types


def list_operation_types(db: Session, *, include_inactive: bool = False) -> list[OperationType]:
    stmt = select(OperationType).order_by(OperationType.sort_order, OperationType.code)
    if not include_inactive:
        stmt = stmt.where(OperationType.is_active.is_(True))
    return list(db.scalars(stmt).all())


def get_operation_type(
    db: Session, type_id: uuid.UUID, *, active_only: bool = False
) -> OperationType:
    ot = db.get(OperationType, type_id)
    if ot is None or (active_only and not ot.is_active):
        raise ValidationFailed("نوع التشغيل غير صحيح", code="invalid_operation_type")
    return ot


def create_operation_type(db: Session, *, actor: User, data: OperationTypeCreate) -> OperationType:
    if db.scalar(select(OperationType.id).where(OperationType.code == data.code)):
        raise ConflictError("كود نوع التشغيل مستخدم بالفعل", code="operation_type_code_taken")
    ot = OperationType(**data.model_dump())
    db.add(ot)
    db.flush()
    audit.record(
        db,
        action="operation_type.created",
        actor=actor,
        entity_type="operation_type",
        entity_id=ot.id,
        changes=audit.diff({}, audit.snapshot(ot, ("code", "kind", "name_ar", "name_en"))),
    )
    db.commit()
    return ot


def update_operation_type(
    db: Session, *, actor: User, type_id: uuid.UUID, data: OperationTypeUpdate
) -> OperationType:
    ot = db.get(OperationType, type_id)
    if ot is None:
        raise NotFoundError("نوع التشغيل غير موجود")
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    changes = apply_changes(ot, fields, ("name_ar", "name_en", "is_active", "sort_order"))
    if changes:
        audit.record(
            db,
            action="operation_type.updated",
            actor=actor,
            entity_type="operation_type",
            entity_id=ot.id,
            changes=changes,
        )
        db.commit()
    return ot


# ------------------------------------------------------------------ routes


def get_route(db: Session, route_id: uuid.UUID) -> RouteDefinition:
    route = db.get(RouteDefinition, route_id)
    if route is None:
        raise NotFoundError("المسار غير موجود")
    return route


def list_routes(
    db: Session,
    params: PageParams,
    *,
    q: str | None = None,
    operation_type_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> tuple[list[RouteDefinition], int]:
    stmt = select(RouteDefinition)
    if q and q.strip():
        stmt = stmt.where(RouteDefinition.name.ilike(like_pattern(q)))
    if operation_type_id:
        stmt = stmt.where(RouteDefinition.operation_type_id == operation_type_id)
    if is_active is not None:
        stmt = stmt.where(RouteDefinition.is_active.is_(is_active))
    return paginate(db, stmt.order_by(RouteDefinition.name, RouteDefinition.id), params)


def _stops_snapshot(route: RouteDefinition) -> list[dict[str, Any]]:
    return [
        {
            "sequence": s.sequence,
            "kind": s.kind.value,
            "name": s.name,
            "latitude": audit.to_jsonable(s.latitude),
            "longitude": audit.to_jsonable(s.longitude),
            "radius_m": s.radius_m,
        }
        for s in route.stops
    ]


def _sync_stops(
    db: Session, route: RouteDefinition, ordered: list[tuple[StopKind, StopIn]]
) -> None:
    """Update stops in place by position so stop IDs stay stable for later references."""
    existing = sorted(route.stops, key=lambda s: s.sequence)
    # Free the sequence numbers first to avoid unique-index clashes while reordering.
    for stop in existing:
        stop.sequence = stop.sequence + 1000
    db.flush()
    for index, (kind, data) in enumerate(ordered):
        values = {"sequence": index + 1, "kind": kind, **data.model_dump()}
        if index < len(existing):
            for key, value in values.items():
                setattr(existing[index], key, value)
        else:
            route.stops.append(RouteStop(**values))
    for surplus in existing[len(ordered) :]:
        route.stops.remove(surplus)
        db.delete(surplus)
    db.flush()


def _ordered_stops(
    origin: StopIn, intermediate: list[StopIn], destination: StopIn
) -> list[tuple[StopKind, StopIn]]:
    return (
        [(StopKind.ORIGIN, origin)]
        + [(StopKind.INTERMEDIATE, s) for s in intermediate]
        + [(StopKind.DESTINATION, destination)]
    )


def create_route(db: Session, *, actor: User, data: RouteCreate) -> RouteDefinition:
    get_operation_type(db, data.operation_type_id, active_only=True)
    fields = data.model_dump(exclude={"origin", "destination", "intermediate_stops"})
    if fields.get("operating_days"):
        fields["operating_days"] = sorted(set(fields["operating_days"]))
    route = RouteDefinition(**fields)
    db.add(route)
    db.flush()
    _sync_stops(db, route, _ordered_stops(data.origin, data.intermediate_stops, data.destination))
    audit.record(
        db,
        action="route.created",
        actor=actor,
        entity_type="route",
        entity_id=route.id,
        changes=audit.diff(
            {}, {**audit.snapshot(route, ROUTE_AUDITED), "stops": _stops_snapshot(route)}
        ),
    )
    db.commit()
    db.refresh(route)
    return route


def update_route(
    db: Session, *, actor: User, route_id: uuid.UUID, data: RouteUpdate
) -> RouteDefinition:
    route = get_route(db, route_id)
    fields: dict[str, Any] = data.model_dump(exclude_unset=True)
    stop_fields = {
        k: fields.pop(k) for k in ("origin", "destination", "intermediate_stops") if k in fields
    }
    for key in ("name", "trip_pattern"):
        if key in fields and fields[key] is None:
            fields.pop(key)
    if fields.get("operating_days"):
        fields["operating_days"] = sorted(set(fields["operating_days"]))

    before = {**audit.snapshot(route, ROUTE_AUDITED), "stops": _stops_snapshot(route)}
    apply_changes(route, fields, ())
    if stop_fields:
        current = sorted(route.stops, key=lambda s: s.sequence)

        def as_in(s: RouteStop) -> StopIn:
            return StopIn(
                name=s.name, latitude=s.latitude, longitude=s.longitude, radius_m=s.radius_m
            )

        origin = data.origin or as_in(current[0])
        destination = data.destination or as_in(current[-1])
        intermediate = (
            data.intermediate_stops
            if data.intermediate_stops is not None
            else [as_in(s) for s in current[1:-1]]
        )
        _sync_stops(db, route, _ordered_stops(origin, intermediate, destination))
    db.flush()
    db.refresh(route)
    changes = audit.diff(
        before, {**audit.snapshot(route, ROUTE_AUDITED), "stops": _stops_snapshot(route)}
    )
    if changes:
        audit.record(
            db,
            action="route.updated",
            actor=actor,
            entity_type="route",
            entity_id=route.id,
            changes=changes,
        )
        db.commit()
    return route


def set_route_active(
    db: Session, *, actor: User, route_id: uuid.UUID, active: bool
) -> RouteDefinition:
    route = get_route(db, route_id)
    if route.is_active != active:
        route.is_active = active
        audit.record(
            db,
            action="route.activated" if active else "route.deactivated",
            actor=actor,
            entity_type="route",
            entity_id=route.id,
            changes={"is_active": {"old": not active, "new": active}},
        )
        db.commit()
    return route


def validate_route_for_type(
    db: Session, *, operation_type: OperationType, route_id: uuid.UUID | None
) -> RouteDefinition | None:
    """A route-based operation needs an active route of the same type."""
    if route_id is None:
        if operation_type.uses_routes:
            raise ValidationFailed("اختر المسار لهذا النوع من التشغيل", code="route_required")
        return None
    route = db.get(RouteDefinition, route_id)
    if route is None or not route.is_active:
        raise ValidationFailed("المسار غير صحيح أو غير نشط", code="invalid_route")
    if route.operation_type_id != operation_type.id:
        raise ValidationFailed("المسار لا يتبع نوع التشغيل المختار", code="route_type_mismatch")
    return route
