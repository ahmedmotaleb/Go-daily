"""Tracker provider adapters (U05).

An adapter turns one provider's webhook body into normalised events. Only
the generic adapter exists: it reads a documented JSON format that any
provider, or a small relay in front of one, can send. A real provider gets
its own adapter when one is chosen; nothing here imitates a specific vendor.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class AdapterError(ValueError):
    """One event the adapter could not read (it is quarantined, not dropped)."""


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    device_id: str
    recorded_at: datetime
    latitude: float
    longitude: float
    speed_mps: float | None = None
    heading_deg: float | None = None
    ignition_on: bool | None = None
    external_power: bool | None = None


class TrackerAdapter(Protocol):
    code: str

    def items(self, body: Any) -> Iterator[dict[str, Any]]:
        """The individual events in a webhook body, as sent."""
        ...

    def event_id(self, item: dict[str, Any]) -> str:
        """The provider's own id for the event (stable across resends)."""
        ...

    def device_id(self, item: dict[str, Any]) -> str | None: ...

    def parse(self, item: dict[str, Any]) -> NormalizedEvent:
        """Normalise one event or raise AdapterError."""
        ...


def fallback_id(item: dict[str, Any]) -> str:
    """A stable id for an event sent without one, so a resend is still a duplicate."""
    digest = hashlib.sha256(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest()
    return f"sha256:{digest[:40]}"


def _float(item: dict[str, Any], key: str, *, required: bool = False) -> float | None:
    value = item.get(key)
    if value is None or value == "":
        if required:
            raise AdapterError(f"missing {key}")
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AdapterError(f"invalid {key}") from exc


def _bool(item: dict[str, Any], key: str) -> bool | None:
    value = item.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise AdapterError(f"invalid {key}")


class GenericAdapter:
    """`{"events": [{"event_id", "device_id", "recorded_at", "lat", "lon", ...}]}`.

    Optional: `speed_kmh`, `heading_deg`, `ignition` (bool), `external_power`
    (bool). `recorded_at` is ISO 8601 with a time zone.
    """

    code = "generic"

    def items(self, body: Any) -> Iterator[dict[str, Any]]:
        events = body.get("events") if isinstance(body, dict) else None
        if not isinstance(events, list):
            raise AdapterError('body must be {"events": [...]}')
        for item in events:
            yield item if isinstance(item, dict) else {"_invalid": item}

    def event_id(self, item: dict[str, Any]) -> str:
        value = item.get("event_id")
        return str(value)[:120] if value not in (None, "") else fallback_id(item)

    def device_id(self, item: dict[str, Any]) -> str | None:
        value = item.get("device_id")
        return str(value)[:100] if value not in (None, "") else None

    def parse(self, item: dict[str, Any]) -> NormalizedEvent:
        device = self.device_id(item)
        if device is None:
            raise AdapterError("missing device_id")
        raw_time = item.get("recorded_at")
        if not isinstance(raw_time, str):
            raise AdapterError("missing recorded_at")
        try:
            recorded = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AdapterError("invalid recorded_at") from exc
        if recorded.tzinfo is None:
            raise AdapterError("recorded_at needs a time zone")
        lat = _float(item, "lat", required=True)
        lon = _float(item, "lon", required=True)
        assert lat is not None and lon is not None  # noqa: S101
        speed = _float(item, "speed_kmh")
        return NormalizedEvent(
            event_id=self.event_id(item),
            device_id=device,
            recorded_at=recorded,
            latitude=lat,
            longitude=lon,
            speed_mps=speed / 3.6 if speed is not None else None,
            heading_deg=_float(item, "heading_deg"),
            ignition_on=_bool(item, "ignition"),
            external_power=_bool(item, "external_power"),
        )


ADAPTERS: dict[str, TrackerAdapter] = {GenericAdapter.code: GenericAdapter()}


__all__ = ["ADAPTERS", "AdapterError", "GenericAdapter", "NormalizedEvent", "TrackerAdapter"]
