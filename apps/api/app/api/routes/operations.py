"""Operation types and route definitions."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission
from app.models.operations import OperationType, RouteDefinition
from app.models.user import User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.operations import (
    OperationTypeCreate,
    OperationTypeOut,
    OperationTypeUpdate,
    RouteCreate,
    RouteOut,
    RouteUpdate,
)
from app.services import operations as ops_service

router = APIRouter(tags=["operations"])

Reader = Annotated[User, Depends(require_permissions(Permission.OPERATIONS_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.OPERATIONS_WRITE))]
SettingsAdmin = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]


@router.get("/operation-types", response_model=list[OperationTypeOut])
def list_operation_types(
    _: Reader, db: DbSession, include_inactive: bool = False
) -> list[OperationType]:
    return ops_service.list_operation_types(db, include_inactive=include_inactive)


@router.post(
    "/operation-types", response_model=OperationTypeOut, status_code=status.HTTP_201_CREATED
)
def create_operation_type(
    body: OperationTypeCreate, actor: SettingsAdmin, db: DbSession
) -> OperationType:
    return ops_service.create_operation_type(db, actor=actor, data=body)


@router.patch("/operation-types/{type_id}", response_model=OperationTypeOut)
def update_operation_type(
    type_id: uuid.UUID, body: OperationTypeUpdate, actor: SettingsAdmin, db: DbSession
) -> OperationType:
    return ops_service.update_operation_type(db, actor=actor, type_id=type_id, data=body)


@router.get("/routes", response_model=Page[RouteOut])
def list_routes(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Query(max_length=100)] = None,
    operation_type_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> Page[RouteOut]:
    rows, total = ops_service.list_routes(
        db, params, q=q, operation_type_id=operation_type_id, is_active=is_active
    )
    return Page(
        items=[RouteOut.model_validate(r) for r in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/routes", response_model=RouteOut, status_code=status.HTTP_201_CREATED)
def create_route(body: RouteCreate, actor: Writer, db: DbSession) -> RouteDefinition:
    return ops_service.create_route(db, actor=actor, data=body)


@router.get("/routes/{route_id}", response_model=RouteOut)
def get_route(route_id: uuid.UUID, _: Reader, db: DbSession) -> RouteDefinition:
    return ops_service.get_route(db, route_id)


@router.patch("/routes/{route_id}", response_model=RouteOut)
def update_route(
    route_id: uuid.UUID, body: RouteUpdate, actor: Writer, db: DbSession
) -> RouteDefinition:
    return ops_service.update_route(db, actor=actor, route_id=route_id, data=body)


@router.post("/routes/{route_id}/activate", response_model=RouteOut)
def activate_route(route_id: uuid.UUID, actor: Writer, db: DbSession) -> RouteDefinition:
    return ops_service.set_route_active(db, actor=actor, route_id=route_id, active=True)


@router.post("/routes/{route_id}/deactivate", response_model=RouteOut)
def deactivate_route(route_id: uuid.UUID, actor: Writer, db: DbSession) -> RouteDefinition:
    return ops_service.set_route_active(db, actor=actor, route_id=route_id, active=False)
