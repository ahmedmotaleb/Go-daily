"""Route (geofence) events and school runs."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission
from app.models.driver import Driver
from app.models.fleet import Vehicle
from app.models.operations import RouteDefinition, RouteStop
from app.models.route_events import (
    EventStatus,
    RouteEvent,
    RouteEventType,
    SchoolRun,
    SchoolRunStatus,
)
from app.models.shift import OperationSession
from app.models.user import User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.route_events import (
    ManualRouteEventIn,
    RecomputeOut,
    RouteEventOut,
    SchoolRunEvidence,
    SchoolRunGenerate,
    SchoolRunGenerateOut,
    SchoolRunOut,
    SchoolRunStatusIn,
    SchoolRunUpdate,
    VoidIn,
)
from app.schemas.shift import PersonRef, RouteRef, VehicleRef
from app.services import route_events as events_service
from app.services import school_runs as runs_service

router = APIRouter(tags=["route-events"])

TrackingReader = Annotated[User, Depends(require_permissions(Permission.TRACKING_READ))]
ShiftWriter = Annotated[User, Depends(require_permissions(Permission.SHIFTS_WRITE))]
OpsReader = Annotated[User, Depends(require_permissions(Permission.OPERATIONS_READ))]
OpsWriter = Annotated[User, Depends(require_permissions(Permission.OPERATIONS_WRITE))]


def _event_out(e: RouteEvent, stop_names: dict[uuid.UUID, str]) -> RouteEventOut:
    return RouteEventOut(
        id=e.id,
        session_id=e.session_id,
        stop_id=e.stop_id,
        stop_name=stop_names.get(e.stop_id) if e.stop_id else None,
        event_type=e.event_type,
        direction=e.direction,
        occurred_at=e.occurred_at,
        sequence_no=e.sequence_no,
        source=e.source,
        status=e.status,
        reason=e.reason,
        void_reason=e.void_reason,
    )


@router.get("/operation-sessions/{session_id}/route-events", response_model=list[RouteEventOut])
def list_route_events(
    session_id: uuid.UUID, _: TrackingReader, db: DbSession
) -> list[RouteEventOut]:
    events = events_service.list_events(db, session_id)
    stop_ids = {e.stop_id for e in events if e.stop_id}
    names = (
        {
            s.id: s.name
            for s in db.scalars(select(RouteStop).where(RouteStop.id.in_(stop_ids))).all()
        }
        if stop_ids
        else {}
    )
    return [_event_out(e, names) for e in events]


@router.post("/operation-sessions/{session_id}/route-events/recompute", response_model=RecomputeOut)
def recompute(session_id: uuid.UUID, actor: ShiftWriter, db: DbSession) -> RecomputeOut:
    return RecomputeOut(**events_service.recompute(db, actor=actor, session_id=session_id))


@router.post(
    "/operation-sessions/{session_id}/route-events",
    response_model=RouteEventOut,
    status_code=status.HTTP_201_CREATED,
)
def add_manual_event(
    session_id: uuid.UUID, body: ManualRouteEventIn, actor: ShiftWriter, db: DbSession
) -> RouteEventOut:
    event = events_service.add_manual_event(
        db,
        actor=actor,
        session_id=session_id,
        event_type=RouteEventType(body.event_type),
        occurred_at=body.occurred_at,
        direction=body.direction,
        reason=body.reason,
    )
    return _event_out(event, {})


@router.post("/route-events/{event_id}/void", response_model=RouteEventOut)
def void_event(
    event_id: uuid.UUID, body: VoidIn, actor: ShiftWriter, db: DbSession
) -> RouteEventOut:
    return _event_out(
        events_service.void_event(db, actor=actor, event_id=event_id, reason=body.reason), {}
    )


# ------------------------------------------------------------------ school runs


def _run_out(db: DbSession, run: SchoolRun) -> SchoolRunOut:
    route_obj = db.get(RouteDefinition, run.route_id)
    vehicle = db.get(Vehicle, run.vehicle_id)
    driver = db.get(Driver, run.driver_id) if run.driver_id else None
    session = db.get(OperationSession, run.session_id) if run.session_id else None
    evidence_types: set[RouteEventType] = set()
    total = 0
    if run.session_id:
        for e in db.scalars(
            select(RouteEvent).where(
                RouteEvent.session_id == run.session_id, RouteEvent.status == EventStatus.ACTIVE
            )
        ).all():
            evidence_types.add(e.event_type)
            total += 1
    assert route_obj is not None and vehicle is not None  # noqa: S101
    return SchoolRunOut(
        id=run.id,
        route=RouteRef(id=route_obj.id, name=route_obj.name),
        service_date=run.service_date,
        scheduled_start_at=run.scheduled_start_at,
        scheduled_end_at=run.scheduled_end_at,
        vehicle=VehicleRef(
            id=vehicle.id, internal_code=vehicle.internal_code, plate_number=vehicle.plate_number
        ),
        driver=PersonRef(id=driver.id, full_name=driver.full_name) if driver else None,
        status=run.status,
        session_id=run.session_id,
        shift_id=session.shift_id if session else None,
        actual_start_at=run.actual_start_at,
        actual_end_at=run.actual_end_at,
        label=run.label,
        notes=run.notes,
        status_reason=run.status_reason,
        evidence=SchoolRunEvidence(
            reached_origin=RouteEventType.REACHED_ORIGIN in evidence_types,
            reached_destination=RouteEventType.REACHED_DESTINATION in evidence_types,
            route_events=total,
        ),
    )


@router.get("/school-runs", response_model=Page[SchoolRunOut])
def list_school_runs(
    _: OpsReader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    date_from: date | None = None,
    date_to: date | None = None,
    route_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    status: SchoolRunStatus | None = None,
) -> Page[SchoolRunOut]:
    rows, total = runs_service.list_runs(
        db,
        params,
        date_from=date_from,
        date_to=date_to,
        route_id=route_id,
        vehicle_id=vehicle_id,
        status=status,
    )
    return Page(
        items=[_run_out(db, r) for r in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post(
    "/school-runs/generate",
    response_model=SchoolRunGenerateOut,
    status_code=status.HTTP_201_CREATED,
)
def generate_school_runs(
    body: SchoolRunGenerate, actor: OpsWriter, db: DbSession
) -> SchoolRunGenerateOut:
    created = runs_service.generate_runs(db, actor=actor, **body.model_dump())
    return SchoolRunGenerateOut(created=len(created))


@router.get("/school-runs/{run_id}", response_model=SchoolRunOut)
def get_school_run(run_id: uuid.UUID, _: OpsReader, db: DbSession) -> SchoolRunOut:
    return _run_out(db, runs_service.get_run(db, run_id))


@router.patch("/school-runs/{run_id}", response_model=SchoolRunOut)
def update_school_run(
    run_id: uuid.UUID, body: SchoolRunUpdate, actor: OpsWriter, db: DbSession
) -> SchoolRunOut:
    run = runs_service.update_run(
        db,
        actor=actor,
        run_id=run_id,
        vehicle_id=body.vehicle_id,
        driver_id=body.driver_id,
        notes=body.notes,
        fields_set=body.model_fields_set,
    )
    return _run_out(db, run)


@router.post("/school-runs/{run_id}/status", response_model=SchoolRunOut)
def correct_school_run_status(
    run_id: uuid.UUID, body: SchoolRunStatusIn, actor: OpsWriter, db: DbSession
) -> SchoolRunOut:
    run = runs_service.correct_status(
        db, actor=actor, run_id=run_id, status=SchoolRunStatus(body.status), reason=body.reason
    )
    return _run_out(db, run)
