"""Hardware GPS tracker endpoints (U05).

The webhook is off until TRACKER_WEBHOOK_SECRET is set and needs an HMAC
signature of the raw body; it never uses a staff or driver session.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, Field

from app.api.deps import DbSession, require_permissions
from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.core.permissions import Permission
from app.models.trackers import RawEventStatus, TrackerBinding, TrackerDevice
from app.models.user import User
from app.services.trackers import ingest as service

router = APIRouter(prefix="/trackers", tags=["trackers"])

Reader = Annotated[User, Depends(require_permissions(Permission.TRACKING_READ))]
Manager = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]

MAX_BODY = 256 * 1024


class IngestOut(BaseModel):
    accepted: int
    duplicates: int
    quarantined: dict[str, int]


class DeviceIn(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    external_id: str = Field(min_length=1, max_length=100)
    label: str | None = Field(default=None, max_length=100)


class BindIn(BaseModel):
    vehicle_id: uuid.UUID
    starts_at: AwareDatetime | None = None


class DeviceOut(BaseModel):
    id: uuid.UUID
    provider: str
    external_id: str
    label: str | None
    is_active: bool
    vehicle: dict[str, str] | None
    bound_since: datetime | None


class RawEventOut(BaseModel):
    id: uuid.UUID
    provider: str
    provider_event_id: str
    device_external_id: str | None
    received_at: datetime
    status: RawEventStatus
    reason: str | None
    reason_ar: str | None


@router.post("/{provider}/events", response_model=IngestOut)
async def receive_events(
    provider: str, request: Request, db: DbSession
) -> IngestOut | JSONResponse:
    if get_settings().tracker_webhook_secret is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "tracker_ingestion_disabled",
                    "message": "استقبال أجهزة التتبع غير مفعل",
                }
            },
        )
    body = await request.body()
    if len(body) > MAX_BODY:
        raise ValidationFailed("الطلب أكبر من المسموح", code="payload_too_large")
    if not service.signature_ok(body, request.headers.get("x-godaily-signature")):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": {"code": "invalid_signature", "message": "توقيع غير صحيح"}},
        )
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise ValidationFailed("JSON غير صالح", code="invalid_json") from exc
    # The database session is synchronous: keep it off the event loop.
    result = await run_in_threadpool(service.ingest, db, provider, payload)
    return IngestOut(
        accepted=result.accepted, duplicates=result.duplicates, quarantined=result.quarantined
    )


def _device_out(device: TrackerDevice, binding: TrackerBinding | None) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        provider=device.provider,
        external_id=device.external_id,
        label=device.label,
        is_active=device.is_active,
        vehicle=(
            {"id": str(binding.vehicle.id), "name": binding.vehicle.internal_code}
            if binding is not None
            else None
        ),
        bound_since=binding.starts_at if binding is not None else None,
    )


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(_: Reader, db: DbSession) -> list[DeviceOut]:
    return [_device_out(d, b) for d, b in service.list_devices(db)]


@router.post("/devices", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def create_device(body: DeviceIn, actor: Manager, db: DbSession) -> DeviceOut:
    device = service.create_device(
        db, actor=actor, provider=body.provider, external_id=body.external_id, label=body.label
    )
    return _device_out(device, None)


@router.post("/devices/{device_id}/bind", response_model=DeviceOut)
def bind_device(device_id: uuid.UUID, body: BindIn, actor: Manager, db: DbSession) -> DeviceOut:
    service.bind(
        db, actor=actor, device_id=device_id, vehicle_id=body.vehicle_id, starts_at=body.starts_at
    )
    return next(_device_out(d, b) for d, b in service.list_devices(db) if d.id == device_id)


@router.post("/devices/{device_id}/unbind", response_model=DeviceOut)
def unbind_device(device_id: uuid.UUID, actor: Manager, db: DbSession) -> DeviceOut:
    service.unbind(db, actor=actor, device_id=device_id)
    return next(_device_out(d, b) for d, b in service.list_devices(db) if d.id == device_id)


@router.get("/events", response_model=list[RawEventOut])
def list_events(
    _: Reader, db: DbSession, status: RawEventStatus | None = None
) -> list[RawEventOut]:
    return [
        RawEventOut(
            id=e.id,
            provider=e.provider,
            provider_event_id=e.provider_event_id,
            device_external_id=e.device_external_id,
            received_at=e.received_at,
            status=e.status,
            reason=e.reason,
            reason_ar=service.REASONS_AR.get(e.reason) if e.reason else None,
        )
        for e in service.recent_events(db, status)
    ]


@router.post("/events/reprocess")
def reprocess_events(actor: Manager, db: DbSession) -> dict[str, int]:
    return service.reprocess(db, actor=actor)
