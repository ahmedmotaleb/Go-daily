"""Tracker event ingestion, quarantine and device bindings (U05).

Every event received is stored as sent. It is accepted only when its device
is registered and active, the device was fitted to a vehicle at the event's
time, the coordinates are possible and the time is neither in the future
nor too old. Anything else is quarantined with a reason, never silently
dropped and never "fixed": no position is invented or moved.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, field_error
from app.core.time import utcnow
from app.models.fleet import Vehicle
from app.models.trackers import (
    RawEventStatus,
    TrackerBinding,
    TrackerDevice,
    TrackerLocation,
    TrackerRawEvent,
)
from app.models.user import User
from app.services import audit
from app.services.trackers.adapters import ADAPTERS, AdapterError, NormalizedEvent, TrackerAdapter

FUTURE_TOLERANCE = timedelta(minutes=5)
# Quarantine reasons that registering or fitting a device can resolve.
FIXABLE = ("UNKNOWN_DEVICE", "DEVICE_INACTIVE", "NO_VEHICLE_BINDING")
REASONS_AR = {
    "INVALID_EVENT": "حدث غير مقروء",
    "UNKNOWN_DEVICE": "جهاز غير مسجل",
    "DEVICE_INACTIVE": "جهاز موقوف",
    "NO_VEHICLE_BINDING": "الجهاز غير مركب على سيارة في هذا الوقت",
    "INVALID_COORDINATES": "إحداثيات غير ممكنة",
    "FUTURE_TIME": "وقت في المستقبل",
    "TOO_OLD": "حدث قديم جدًا",
}


def adapter(provider: str) -> TrackerAdapter:
    found = ADAPTERS.get(provider)
    if found is None:
        raise NotFoundError("مزود التتبع غير معروف")
    return found


def signature_ok(body: bytes, header: str | None) -> bool:
    """`X-GoDaily-Signature: sha256=<hex HMAC of the raw body>`."""
    secret = get_settings().tracker_webhook_secret
    if secret is None or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.get_secret_value().encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


@dataclass
class IngestResult:
    accepted: int = 0
    duplicates: int = 0
    quarantined: dict[str, int] = field(default_factory=dict)


def _binding(db: Session, device: TrackerDevice, at: datetime) -> TrackerBinding | None:
    return db.scalar(
        select(TrackerBinding).where(
            TrackerBinding.device_id == device.id,
            TrackerBinding.starts_at <= at,
            or_(TrackerBinding.ends_at.is_(None), TrackerBinding.ends_at > at),
        )
    )


def _check(
    db: Session, provider: str, event: NormalizedEvent
) -> tuple[str | None, TrackerDevice | None, TrackerBinding | None]:
    """(quarantine reason or None, device, binding)."""
    now = utcnow()
    if not (-90 <= event.latitude <= 90 and -180 <= event.longitude <= 180) or (
        event.latitude == 0 and event.longitude == 0
    ):
        return "INVALID_COORDINATES", None, None
    if event.recorded_at > now + FUTURE_TOLERANCE:
        return "FUTURE_TIME", None, None
    if event.recorded_at < now - timedelta(days=get_settings().tracker_max_event_age_days):
        return "TOO_OLD", None, None
    device = db.scalar(
        select(TrackerDevice).where(
            TrackerDevice.provider == provider, TrackerDevice.external_id == event.device_id
        )
    )
    if device is None:
        return "UNKNOWN_DEVICE", None, None
    if not device.is_active:
        return "DEVICE_INACTIVE", device, None
    binding = _binding(db, device, event.recorded_at)
    if binding is None:
        return "NO_VEHICLE_BINDING", device, None
    return None, device, binding


def _store_location(
    db: Session,
    raw: TrackerRawEvent,
    event: NormalizedEvent,
    device: TrackerDevice,
    vehicle: uuid.UUID,
) -> None:
    db.add(
        TrackerLocation(
            device_id=device.id,
            vehicle_id=vehicle,
            raw_event_id=raw.id,
            recorded_at=event.recorded_at,
            latitude=event.latitude,
            longitude=event.longitude,
            speed_mps=event.speed_mps,
            heading_deg=event.heading_deg,
            ignition_on=event.ignition_on,
            external_power=event.external_power,
        )
    )


def ingest(db: Session, provider: str, body: Any) -> IngestResult:
    """Store every event of a webhook body; accept or quarantine each one."""
    source = adapter(provider)
    result = IngestResult()
    try:
        items = list(source.items(body))
    except AdapterError as exc:
        raise field_error("events", str(exc), code="invalid_tracker_body") from exc
    for item in items:
        event_id = source.event_id(item)
        reason: str | None
        try:
            event: NormalizedEvent | None = source.parse(item)
        except AdapterError:
            event, reason = None, "INVALID_EVENT"
        device = binding = None
        if event is not None:
            reason, device, binding = _check(db, provider, event)
        row_id = db.execute(
            pg_insert(TrackerRawEvent)
            .values(
                provider=provider,
                provider_event_id=event_id,
                device_external_id=source.device_id(item),
                payload=item,
                status=RawEventStatus.QUARANTINED if reason else RawEventStatus.ACCEPTED,
                reason=reason,
                received_at=utcnow(),
            )
            .on_conflict_do_nothing(constraint="uq_tracker_raw_events_ref")
            .returning(TrackerRawEvent.id)
        ).scalar()
        if row_id is None:
            result.duplicates += 1
            continue
        if reason is not None:
            result.quarantined[reason] = result.quarantined.get(reason, 0) + 1
            continue
        assert event is not None and device is not None and binding is not None  # noqa: S101
        raw = db.get(TrackerRawEvent, row_id)
        assert raw is not None  # noqa: S101
        _store_location(db, raw, event, device, binding.vehicle_id)
        result.accepted += 1
    db.commit()
    return result


def reprocess(db: Session, *, actor: User) -> dict[str, int]:
    """Check again the events quarantined for a device reason (after registering or fitting)."""
    accepted = still = 0
    for raw in db.scalars(
        select(TrackerRawEvent)
        .where(
            TrackerRawEvent.status == RawEventStatus.QUARANTINED,
            TrackerRawEvent.reason.in_(FIXABLE),
        )
        .with_for_update()
    ).all():
        source = ADAPTERS.get(raw.provider)
        if source is None:
            still += 1
            continue
        event = source.parse(raw.payload)
        reason, device, binding = _check(db, raw.provider, event)
        raw.reprocessed_at = utcnow()
        if reason is not None:
            raw.reason = reason
            still += 1
            continue
        assert device is not None and binding is not None  # noqa: S101
        raw.status = RawEventStatus.ACCEPTED
        raw.reason = None
        _store_location(db, raw, event, device, binding.vehicle_id)
        accepted += 1
    audit.record(
        db,
        action="tracker.events_reprocessed",
        actor=actor,
        entity_type="tracker_raw_event",
        details={"accepted": accepted, "still_quarantined": still},
    )
    db.commit()
    return {"accepted": accepted, "still_quarantined": still}


# --- Devices --------------------------------------------------------------------------


def list_devices(db: Session) -> list[tuple[TrackerDevice, TrackerBinding | None]]:
    now = utcnow()
    out = []
    for device in db.scalars(
        select(TrackerDevice).order_by(TrackerDevice.provider, TrackerDevice.external_id)
    ).all():
        out.append((device, _binding(db, device, now)))
    return out


def create_device(
    db: Session, *, actor: User, provider: str, external_id: str, label: str | None
) -> TrackerDevice:
    adapter(provider)
    if db.scalar(
        select(TrackerDevice.id).where(
            TrackerDevice.provider == provider, TrackerDevice.external_id == external_id
        )
    ):
        raise field_error("external_id", "الجهاز مسجل بالفعل", code="duplicate_device")
    device = TrackerDevice(provider=provider, external_id=external_id, label=label)
    db.add(device)
    db.flush()
    audit.record(
        db,
        action="tracker.device_created",
        actor=actor,
        entity_type="tracker_device",
        entity_id=device.id,
        details={"provider": provider, "external_id": external_id},
    )
    db.commit()
    return device


def _device(db: Session, device_id: uuid.UUID) -> TrackerDevice:
    device = db.get(TrackerDevice, device_id)
    if device is None:
        raise NotFoundError("الجهاز غير موجود")
    return device


def bind(
    db: Session,
    *,
    actor: User,
    device_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    starts_at: datetime | None,
) -> TrackerBinding:
    """Fit a tracker to a vehicle; any open binding of the device ends then."""
    device = _device(db, device_id)
    if db.get(Vehicle, vehicle_id) is None:
        raise field_error("vehicle_id", "المركبة غير موجودة")
    start = starts_at or utcnow()
    current = db.scalar(
        select(TrackerBinding).where(
            TrackerBinding.device_id == device.id, TrackerBinding.ends_at.is_(None)
        )
    )
    if current is not None:
        if start <= current.starts_at:
            raise ConflictError("بداية التركيب قبل التركيب الحالي", code="binding_overlap")
        current.ends_at = start
    later = db.scalar(
        select(TrackerBinding.id).where(
            TrackerBinding.device_id == device.id, TrackerBinding.starts_at > start
        )
    )
    if later:
        raise ConflictError("يوجد تركيب لاحق لهذا الجهاز", code="binding_overlap")
    binding = TrackerBinding(
        device_id=device.id, vehicle_id=vehicle_id, starts_at=start, created_by_id=actor.id
    )
    db.add(binding)
    db.flush()
    audit.record(
        db,
        action="tracker.device_bound",
        actor=actor,
        entity_type="tracker_device",
        entity_id=device.id,
        details={"vehicle_id": vehicle_id, "starts_at": start},
    )
    db.commit()
    return binding


def unbind(db: Session, *, actor: User, device_id: uuid.UUID) -> None:
    device = _device(db, device_id)
    current = db.scalar(
        select(TrackerBinding).where(
            TrackerBinding.device_id == device.id, TrackerBinding.ends_at.is_(None)
        )
    )
    if current is None:
        raise ConflictError("الجهاز غير مركب على سيارة", code="not_bound")
    current.ends_at = max(utcnow(), current.starts_at + timedelta(seconds=1))
    audit.record(
        db,
        action="tracker.device_unbound",
        actor=actor,
        entity_type="tracker_device",
        entity_id=device.id,
        details={"vehicle_id": current.vehicle_id},
    )
    db.commit()


def recent_events(
    db: Session, status: RawEventStatus | None, limit: int = 100
) -> list[TrackerRawEvent]:
    stmt = select(TrackerRawEvent).order_by(TrackerRawEvent.received_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(TrackerRawEvent.status == status)
    return list(db.scalars(stmt).all())


__all__ = [
    "REASONS_AR",
    "IngestResult",
    "bind",
    "create_device",
    "ingest",
    "list_devices",
    "recent_events",
    "reprocess",
    "signature_ok",
    "unbind",
]


def prune(db: Session, *, older_than_days: int) -> int:
    """Delete tracker positions and raw events past the GPS retention period."""
    from sqlalchemy import delete  # noqa: PLC0415

    cutoff = utcnow() - timedelta(days=older_than_days)
    locations = db.execute(delete(TrackerLocation).where(TrackerLocation.recorded_at < cutoff))
    raw = db.execute(
        delete(TrackerRawEvent).where(
            TrackerRawEvent.received_at < cutoff,
            ~select(TrackerLocation.id)
            .where(TrackerLocation.raw_event_id == TrackerRawEvent.id)
            .exists(),
        )
    )
    db.commit()
    return int(locations.rowcount or 0) + int(raw.rowcount or 0)  # type: ignore[attr-defined]
