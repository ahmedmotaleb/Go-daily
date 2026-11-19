"""Fuel stations and vendors (U16).

A station is optional on a purchase. The free-text vendor stays, and an
unknown or new station is never a reason to refuse an entry. A station
marked trusted, with a location and a radius, is linked automatically to
driver-app purchases recorded inside it; nothing else is inferred.

Station pages show the purchase history, receipts, and average and
historical unit prices from approved purchases next to the fleet's average
for the same fuel type. A price far from the fleet's is a figure to look
at, not a finding.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, field_error
from app.core.geo import haversine_m
from app.core.time import to_local_date
from app.models.attachment import Attachment, AttachmentOwner
from app.models.finance import FuelStation, FuelTransaction, FuelType, RecordStatus
from app.models.user import User
from app.schemas.fuel_stations import FuelStationCreate, FuelStationUpdate
from app.services import audit
from app.services import finance_common as fc

ENTITY = "fuel_station"
FIELDS = ("name", "brand", "address", "latitude", "longitude", "radius_m", "is_trusted", "notes")
PRICE = Decimal("0.001")
RECENT = 30


def get(db: Session, station_id: uuid.UUID) -> FuelStation:
    station = db.get(FuelStation, station_id)
    if station is None:
        raise NotFoundError("المحطة غير موجودة")
    return station


def active(db: Session, station_id: uuid.UUID) -> FuelStation:
    """A station a new or edited purchase may point to."""
    station = db.get(FuelStation, station_id)
    if station is None or not station.is_active:
        raise field_error("station_id", "المحطة غير موجودة أو موقوفة")
    return station


def list_stations(db: Session, *, include_inactive: bool = False) -> list[FuelStation]:
    stmt = select(FuelStation).order_by(FuelStation.name)
    if not include_inactive:
        stmt = stmt.where(FuelStation.is_active.is_(True))
    return list(db.scalars(stmt).all())


def usage(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, datetime | None]]:
    """Live purchases (submitted or approved) and the latest one, per station."""
    if not ids:
        return {}
    rows = db.execute(
        select(
            FuelTransaction.station_id,
            func.count(),
            func.max(FuelTransaction.occurred_at),
        )
        .where(
            FuelTransaction.station_id.in_(ids),
            FuelTransaction.status.in_((RecordStatus.SUBMITTED, RecordStatus.APPROVED)),
        )
        .group_by(FuelTransaction.station_id)
    ).all()
    return {sid: (n, last) for sid, n, last in rows if sid is not None}


def _fuel_types(db: Session, ids: list[uuid.UUID]) -> list[FuelType]:
    found = list(db.scalars(select(FuelType).where(FuelType.id.in_(ids))).all())
    if len(found) != len(set(ids)):
        raise field_error("fuel_type_ids", "نوع وقود غير موجود")
    return found


def _check(station: FuelStation) -> None:
    if station.is_trusted and station.latitude is None:
        raise field_error(
            "is_trusted", "المحطة الموثوقة تحتاج موقعًا على الخريطة", code="trusted_needs_location"
        )


def _snapshot(station: FuelStation) -> dict[str, Any]:
    data = audit.snapshot(station, FIELDS)
    data["fuel_types"] = sorted(t.code for t in station.fuel_types)
    data["is_active"] = station.is_active
    return data


def create(db: Session, *, actor: User, data: FuelStationCreate) -> FuelStation:
    values = data.model_dump(exclude_none=True, exclude={"fuel_type_ids"})
    station = FuelStation(**values)
    station.fuel_types = _fuel_types(db, data.fuel_type_ids or [])
    _check(station)
    db.add(station)
    db.flush()
    audit.record(
        db,
        action=f"{ENTITY}.created",
        actor=actor,
        entity_type=ENTITY,
        entity_id=station.id,
        changes=audit.diff({}, _snapshot(station)),
    )
    db.commit()
    return station


def update(
    db: Session, *, actor: User, station_id: uuid.UUID, data: FuelStationUpdate
) -> FuelStation:
    """Edit or (de)activate a station. Stations are never deleted."""
    station = get(db, station_id)
    before = _snapshot(station)
    fields = data.model_dump(exclude_unset=True)
    types = fields.pop("fuel_type_ids", None)
    for key, value in fields.items():
        if value is None and key in ("name", "radius_m", "is_trusted", "is_active"):
            continue  # required columns: "not sent" and null mean the same
        setattr(station, key, value)
    if types is not None:
        station.fuel_types = _fuel_types(db, types)
    _check(station)
    changes = audit.diff(before, _snapshot(station))
    if changes:
        db.flush()
        audit.record(
            db,
            action=f"{ENTITY}.updated",
            actor=actor,
            entity_type=ENTITY,
            entity_id=station.id,
            changes=changes,
        )
    db.commit()
    return station


def match(db: Session, latitude: float, longitude: float) -> FuelStation | None:
    """The nearest active trusted station whose radius contains the point."""
    best: tuple[float, FuelStation] | None = None
    for s in db.scalars(
        select(FuelStation).where(
            FuelStation.is_active.is_(True),
            FuelStation.is_trusted.is_(True),
            FuelStation.latitude.is_not(None),
        )
    ).all():
        assert s.latitude is not None and s.longitude is not None  # noqa: S101
        distance = haversine_m(latitude, longitude, s.latitude, s.longitude)
        if distance <= s.radius_m and (best is None or distance < best[0]):
            best = (distance, s)
    return best[1] if best else None


# --- Station page ----------------------------------------------------------------


@dataclass
class _Totals:
    fuel_type: FuelType
    unit: Any
    count: int = 0
    quantity: Decimal = Decimal(0)
    total: Decimal = Decimal(0)
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    last_price: Decimal | None = None
    last_at: datetime | None = None


def _unit_price(t: FuelTransaction) -> Decimal:
    return (t.total_amount / t.quantity).quantize(PRICE)


def _fleet_averages(db: Session, type_ids: list[uuid.UUID]) -> dict[tuple[uuid.UUID, Any], Decimal]:
    """Quantity-weighted average price of approved purchases at all stations."""
    if not type_ids:
        return {}
    rows = db.execute(
        select(
            FuelTransaction.fuel_type_id,
            FuelTransaction.unit,
            func.sum(FuelTransaction.total_amount),
            func.sum(FuelTransaction.quantity),
        )
        .where(
            FuelTransaction.fuel_type_id.in_(type_ids),
            FuelTransaction.status == RecordStatus.APPROVED,
        )
        .group_by(FuelTransaction.fuel_type_id, FuelTransaction.unit)
    ).all()
    return {(tid, unit): (total / qty).quantize(PRICE) for tid, unit, total, qty in rows if qty}


def prices(db: Session, approved: list[FuelTransaction]) -> list[dict[str, Any]]:
    totals: dict[tuple[uuid.UUID, Any], _Totals] = {}
    for t in approved:
        key = (t.fuel_type_id, t.unit)
        row = totals.setdefault(key, _Totals(t.fuel_type, t.unit))
        price = _unit_price(t)
        row.count += 1
        row.quantity += t.quantity
        row.total += t.total_amount
        row.min_price = price if row.min_price is None else min(row.min_price, price)
        row.max_price = price if row.max_price is None else max(row.max_price, price)
        if row.last_at is None or t.occurred_at > row.last_at:
            row.last_at, row.last_price = t.occurred_at, price
    fleet = _fleet_averages(db, list({k[0] for k in totals}))
    out = []
    for key, row in totals.items():
        average = (row.total / row.quantity).quantize(PRICE)
        reference = fleet.get(key)
        out.append(
            {
                "fuel_type": row.fuel_type,
                "unit": row.unit,
                "count": row.count,
                "quantity": row.quantity,
                "total_amount": fc.money(row.total),
                "average_price": average,
                "min_price": row.min_price,
                "max_price": row.max_price,
                "last_price": row.last_price,
                "fleet_average_price": reference,
                "difference_pct": (
                    ((average - reference) / reference * 100).quantize(Decimal("0.1"))
                    if reference
                    else None
                ),
            }
        )
    return sorted(out, key=lambda r: (r["fuel_type"].sort_order, r["fuel_type"].code))


def monthly(approved: list[FuelTransaction]) -> list[dict[str, Any]]:
    groups: dict[tuple[date, str], list[FuelTransaction]] = defaultdict(list)
    for t in approved:
        local = to_local_date(t.occurred_at)
        groups[(local.replace(day=1), t.fuel_type.name_ar)].append(t)
    return [
        {
            "month": month,
            "fuel_type": name,
            "average_price": (
                sum((t.total_amount for t in rows), Decimal(0))
                / sum((t.quantity for t in rows), Decimal(0))
            ).quantize(PRICE),
            "count": len(rows),
        }
        for (month, name), rows in sorted(groups.items(), reverse=True)
    ]


def detail(db: Session, station: FuelStation) -> dict[str, Any]:
    purchases = list(
        db.scalars(
            select(FuelTransaction)
            .where(FuelTransaction.station_id == station.id)
            .order_by(FuelTransaction.occurred_at.desc())
        ).all()
    )
    approved = [t for t in purchases if t.status is RecordStatus.APPROVED]
    live = [t for t in purchases if t.status in (RecordStatus.SUBMITTED, RecordStatus.APPROVED)]
    with_receipt = set(
        db.scalars(
            select(Attachment.owner_id).where(
                Attachment.owner_type == AttachmentOwner.FUEL_TRANSACTION,
                Attachment.owner_id.in_([t.id for t in purchases]),
                Attachment.deleted_at.is_(None),
            )
        ).all()
    )
    return {
        "transactions_count": len(live),
        "last_purchase_at": live[0].occurred_at if live else None,
        "prices": prices(db, approved),
        "monthly": monthly(approved),
        "recent": [
            {
                "id": t.id,
                "occurred_at": t.occurred_at,
                "vehicle": {"id": t.vehicle.id, "name": t.vehicle.internal_code},
                "driver": {"id": t.driver.id, "name": t.driver.full_name} if t.driver else None,
                "fuel_type": t.fuel_type.name_ar,
                "quantity": t.quantity,
                "unit_price": _unit_price(t),
                "total_amount": fc.money(t.total_amount),
                "status": t.status,
                "has_receipt": t.id in with_receipt,
            }
            for t in purchases[:RECENT]
        ],
        "receipts_count": sum(1 for t in live if t.id in with_receipt),
        "pending_count": sum(1 for t in live if t.status is RecordStatus.SUBMITTED),
    }


__all__ = ["active", "create", "detail", "get", "list_stations", "match", "update", "usage"]
