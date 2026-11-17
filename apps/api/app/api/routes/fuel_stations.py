"""Fuel station and vendor endpoints (U16)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission
from app.models.finance import FuelStation
from app.models.user import User
from app.schemas.finance import FuelTypeOut
from app.schemas.fuel_stations import (
    FuelStationCreate,
    FuelStationDetail,
    FuelStationOut,
    FuelStationUpdate,
)
from app.services import fuel_stations as stations

router = APIRouter(prefix="/fuel-stations", tags=["fuel"])

Reader = Annotated[User, Depends(require_permissions(Permission.FUEL_READ))]
SettingsAdmin = Annotated[User, Depends(require_permissions(Permission.SETTINGS_MANAGE))]


def _out(station: FuelStation, count: int = 0, last: object = None) -> FuelStationOut:
    return FuelStationOut.model_validate(
        {
            "id": station.id,
            "name": station.name,
            "brand": station.brand,
            "address": station.address,
            "latitude": station.latitude,
            "longitude": station.longitude,
            "radius_m": station.radius_m,
            "is_trusted": station.is_trusted,
            "is_active": station.is_active,
            "notes": station.notes,
            "fuel_types": [FuelTypeOut.model_validate(t) for t in station.fuel_types],
            "transactions_count": count,
            "last_purchase_at": last,
        }
    )


@router.get("", response_model=list[FuelStationOut])
def list_stations(_: Reader, db: DbSession, include_inactive: bool = False) -> list[FuelStationOut]:
    rows = stations.list_stations(db, include_inactive=include_inactive)
    used = stations.usage(db, [s.id for s in rows])
    return [_out(s, *used.get(s.id, (0, None))) for s in rows]


@router.post("", response_model=FuelStationOut, status_code=status.HTTP_201_CREATED)
def create_station(body: FuelStationCreate, actor: SettingsAdmin, db: DbSession) -> FuelStationOut:
    return _out(stations.create(db, actor=actor, data=body))


@router.get("/{station_id}", response_model=FuelStationDetail)
def get_station(station_id: uuid.UUID, _: Reader, db: DbSession) -> FuelStationDetail:
    station = stations.get(db, station_id)
    base = _out(station).model_dump()
    base.update(stations.detail(db, station))
    return FuelStationDetail.model_validate(base)


@router.patch("/{station_id}", response_model=FuelStationOut)
def update_station(
    station_id: uuid.UUID, body: FuelStationUpdate, actor: SettingsAdmin, db: DbSession
) -> FuelStationOut:
    station = stations.update(db, actor=actor, station_id=station_id, data=body)
    return _out(station, *stations.usage(db, [station.id]).get(station.id, (0, None)))
