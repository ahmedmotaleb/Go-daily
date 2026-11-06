"""Plausibility checks for one fuel purchase (U15).

Each check states what was compared, the observed value and the
threshold, and ends as pass, fail or "cannot check" when the data is
missing (nothing is assumed). Some checks already have their own review
rule (location, driver-paid outside shift, duplicates); they are shown
here for the full picture and marked with that rule, so the plausibility
rule does not raise the same thing twice.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.geo import haversine_m
from app.models.assignment import DriverVehicleAssignment
from app.models.finance import FuelTransaction, PaidBy, QuantityUnit, RecordStatus
from app.models.shift import Shift, ShiftStatus
from app.models.tracking import GpsPoint, PointQuality
from app.services import fuel as fuel_service

LIVE = (RecordStatus.SUBMITTED, RecordStatus.APPROVED)


class CheckResult(StrEnum):
    PASS = "PASS"  # noqa: S105 - a check result, not a password
    FAIL = "FAIL"
    NOT_CHECKABLE = "NOT_CHECKABLE"


@dataclass
class Check:
    code: str
    result: CheckResult
    observed: Any = None
    threshold: Any = None
    note: str | None = None
    # Another review rule already raises this failure.
    covered_by: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def _max_quantity(unit: QuantityUnit, s: Settings) -> Decimal | None:
    return {
        QuantityUnit.LITER: s.fuel_max_quantity_liter,
        QuantityUnit.CUBIC_METER: s.fuel_max_quantity_cubic_meter,
        QuantityUnit.KG: s.fuel_max_quantity_kg,
    }.get(unit)


def _covering_shift(db: Session, tx: FuelTransaction, grace: timedelta) -> Shift | None:
    return db.scalars(
        select(Shift)
        .where(
            Shift.vehicle_id == tx.vehicle_id,
            Shift.status.in_((ShiftStatus.ACTIVE, ShiftStatus.COMPLETED)),
            Shift.started_at <= tx.occurred_at + grace,
            or_(Shift.ended_at.is_(None), Shift.ended_at >= tx.occurred_at - grace),
        )
        .order_by(Shift.started_at)
        .limit(1)
    ).first()


def _assignment(db: Session, tx: FuelTransaction, shift: Shift | None) -> Check:
    if tx.driver_id is None:
        return Check("ASSIGNMENT", CheckResult.NOT_CHECKABLE, note="no_driver")
    if shift is not None and shift.driver_id == tx.driver_id:
        return Check("ASSIGNMENT", CheckResult.PASS, observed="driving_in_shift")
    assigned = db.scalar(
        select(DriverVehicleAssignment.id).where(
            DriverVehicleAssignment.driver_id == tx.driver_id,
            DriverVehicleAssignment.vehicle_id == tx.vehicle_id,
            DriverVehicleAssignment.starts_at <= tx.occurred_at,
            or_(
                DriverVehicleAssignment.ends_at.is_(None),
                DriverVehicleAssignment.ends_at >= tx.occurred_at,
            ),
        )
    )
    if assigned is not None:
        return Check("ASSIGNMENT", CheckResult.PASS, observed="assigned")
    return Check(
        "ASSIGNMENT",
        CheckResult.FAIL,
        observed="not_assigned_not_driving",
        note="السائق غير مسند للمركبة ولا يقودها في وردية وقت الشراء",
    )


def _shift_time(tx: FuelTransaction, shift: Shift | None, s: Settings) -> Check:
    if shift is not None:
        return Check("SHIFT_TIME", CheckResult.PASS, observed="inside_shift")
    return Check(
        "SHIFT_TIME",
        CheckResult.FAIL,
        observed="no_shift",
        threshold=s.exception_fuel_outside_shift_minutes,
        note="لا توجد وردية للمركبة وقت الشراء",
        covered_by="FUEL_OUTSIDE_SHIFT" if tx.paid_by is PaidBy.DRIVER else None,
    )


def _odometer(db: Session, tx: FuelTransaction, shift: Shift | None, s: Settings) -> Check:
    if tx.odometer_km is None:
        return Check("ODOMETER", CheckResult.NOT_CHECKABLE, note="no_reading")
    tolerance = s.fuel_odometer_tolerance_km
    previous = db.scalars(
        select(FuelTransaction)
        .where(
            FuelTransaction.vehicle_id == tx.vehicle_id,
            FuelTransaction.id != tx.id,
            FuelTransaction.status.in_(LIVE),
            FuelTransaction.odometer_km.is_not(None),
            FuelTransaction.occurred_at < tx.occurred_at,
        )
        .order_by(FuelTransaction.occurred_at.desc())
        .limit(1)
    ).first()
    details: dict[str, Any] = {"reading_km": tx.odometer_km}
    if previous is not None and previous.odometer_km is not None:
        details["previous_reading_km"] = previous.odometer_km
        if tx.odometer_km < previous.odometer_km:
            return Check(
                "ODOMETER",
                CheckResult.FAIL,
                observed=tx.odometer_km,
                threshold=previous.odometer_km,
                note="قراءة العداد أقل من قراءة عملية الوقود السابقة",
                details=details,
            )
    if shift is not None and shift.start_odometer_km is not None:
        low = shift.start_odometer_km - tolerance
        high = (
            shift.end_odometer_km or shift.vehicle.current_odometer_km or tx.odometer_km
        ) + tolerance
        details.update(shift_start_km=shift.start_odometer_km, shift_end_km=shift.end_odometer_km)
        if not low <= tx.odometer_km <= high:
            return Check(
                "ODOMETER",
                CheckResult.FAIL,
                observed=tx.odometer_km,
                threshold=f"{low}-{high}",
                note="قراءة العداد خارج قراءات الوردية",
                details=details,
            )
    return Check("ODOMETER", CheckResult.PASS, observed=tx.odometer_km, details=details)


def _location(db: Session, tx: FuelTransaction, s: Settings) -> Check:
    if tx.latitude is None or tx.longitude is None:
        return Check("LOCATION", CheckResult.NOT_CHECKABLE, note="no_purchase_location")
    window = timedelta(minutes=10)
    near = db.scalars(
        select(GpsPoint)
        .where(
            GpsPoint.vehicle_id == tx.vehicle_id,
            GpsPoint.quality == PointQuality.VALID,
            GpsPoint.recorded_at >= tx.occurred_at - window,
            GpsPoint.recorded_at <= tx.occurred_at + window,
        )
        .order_by(GpsPoint.recorded_at)
    ).all()
    if not near:
        return Check("LOCATION", CheckResult.NOT_CHECKABLE, note="no_vehicle_gps")
    closest = min(near, key=lambda p: abs((p.recorded_at - tx.occurred_at).total_seconds()))
    distance = round(haversine_m(tx.latitude, tx.longitude, closest.latitude, closest.longitude))
    ok = distance <= s.exception_fuel_distance_m
    return Check(
        "LOCATION",
        CheckResult.PASS if ok else CheckResult.FAIL,
        observed=distance,
        threshold=s.exception_fuel_distance_m,
        note=None if ok else "موقع الشراء بعيد عن موقع المركبة في نفس الوقت",
        covered_by=None if ok else "FUEL_FAR",
    )


def _quantity(db: Session, tx: FuelTransaction, s: Settings) -> Check:
    limit = _max_quantity(tx.unit, s)
    details: dict[str, Any] = {"unit": tx.unit.value, "max_per_purchase": limit}
    if limit is not None and tx.quantity > limit:
        return Check(
            "QUANTITY",
            CheckResult.FAIL,
            observed=tx.quantity,
            threshold=limit,
            note="الكمية أكبر من الحد المعقول لعملية واحدة",
            details=details,
        )
    history = list(
        db.scalars(
            select(FuelTransaction.quantity)
            .where(
                FuelTransaction.vehicle_id == tx.vehicle_id,
                FuelTransaction.fuel_type_id == tx.fuel_type_id,
                FuelTransaction.unit == tx.unit,
                FuelTransaction.id != tx.id,
                FuelTransaction.status.in_(LIVE),
                FuelTransaction.occurred_at < tx.occurred_at,
            )
            .order_by(FuelTransaction.occurred_at.desc())
            .limit(20)
        ).all()
    )
    if len(history) >= s.fuel_quantity_min_history:
        median = Decimal(str(statistics.median(history)))
        details.update(vehicle_median=median, purchases_compared=len(history))
        ratio = Decimal(str(s.fuel_quantity_ratio))
        if median > 0 and tx.quantity > median * ratio:
            return Check(
                "QUANTITY",
                CheckResult.FAIL,
                observed=tx.quantity,
                threshold=(median * ratio).quantize(Decimal("0.001")),
                note="الكمية أكبر بكثير من المعتاد لهذه المركبة",
                details=details,
            )
    return Check(
        "QUANTITY", CheckResult.PASS, observed=tx.quantity, threshold=limit, details=details
    )


def _rapid_repeat(db: Session, tx: FuelTransaction, s: Settings) -> Check:
    window = timedelta(hours=s.fuel_repeat_hours)
    previous = db.scalars(
        select(FuelTransaction)
        .where(
            FuelTransaction.vehicle_id == tx.vehicle_id,
            FuelTransaction.fuel_type_id == tx.fuel_type_id,
            FuelTransaction.id != tx.id,
            FuelTransaction.status.in_(LIVE),
            FuelTransaction.occurred_at < tx.occurred_at,
            FuelTransaction.occurred_at >= tx.occurred_at - window,
        )
        .order_by(FuelTransaction.occurred_at.desc())
        .limit(1)
    ).first()
    if previous is None:
        return Check("RAPID_REPEAT", CheckResult.PASS, threshold=s.fuel_repeat_hours)
    minutes = int((tx.occurred_at - previous.occurred_at).total_seconds() // 60)
    km = (
        tx.odometer_km - previous.odometer_km
        if tx.odometer_km is not None and previous.odometer_km is not None
        else None
    )
    details = {"previous_id": str(previous.id), "minutes_since": minutes, "km_since": km}
    too_soon = minutes < s.fuel_repeat_min_minutes
    too_little = km is not None and km < s.fuel_repeat_min_km
    if too_soon or too_little:
        return Check(
            "RAPID_REPEAT",
            CheckResult.FAIL,
            observed=minutes,
            threshold={"minutes": s.fuel_repeat_min_minutes, "km": s.fuel_repeat_min_km},
            note="عملية وقود أخرى لنفس النوع قبل وقت قصير"
            + ("" if km is None else f" وبعد {km} كم فقط"),
            details=details,
        )
    return Check("RAPID_REPEAT", CheckResult.PASS, observed=minutes, details=details)


def _duplicate(db: Session, tx: FuelTransaction, s: Settings) -> Check:
    window = timedelta(minutes=s.exception_duplicate_window_minutes)
    twin = db.scalar(
        select(FuelTransaction.id).where(
            FuelTransaction.vehicle_id == tx.vehicle_id,
            FuelTransaction.fuel_type_id == tx.fuel_type_id,
            FuelTransaction.id != tx.id,
            FuelTransaction.status.in_(LIVE),
            FuelTransaction.total_amount == tx.total_amount,
            and_(
                FuelTransaction.occurred_at >= tx.occurred_at - window,
                FuelTransaction.occurred_at <= tx.occurred_at + window,
            ),
        )
    )
    if twin is None:
        return Check("DUPLICATE", CheckResult.PASS)
    return Check(
        "DUPLICATE",
        CheckResult.FAIL,
        observed=str(twin),
        threshold=s.exception_duplicate_window_minutes,
        note="سجل آخر بنفس المبلغ والنوع في وقت متقارب",
        covered_by="DUPLICATE_TRANSACTION",
    )


def check(db: Session, tx: FuelTransaction) -> list[Check]:
    s = get_settings()
    grace = timedelta(minutes=s.exception_fuel_outside_shift_minutes)
    shift = _covering_shift(db, tx, grace)
    repeat, duplicate = _rapid_repeat(db, tx, s), _duplicate(db, tx, s)
    if repeat.result is CheckResult.FAIL and duplicate.result is CheckResult.FAIL:
        # The same pair of records: one review case (the duplicate rule) is enough.
        repeat.covered_by = duplicate.covered_by
    return [
        _assignment(db, tx, shift),
        _shift_time(tx, shift, s),
        _odometer(db, tx, shift, s),
        _location(db, tx, s),
        _quantity(db, tx, s),
        repeat,
        duplicate,
    ]


def get_checks(db: Session, tx_id: uuid.UUID) -> list[Check]:
    return check(db, fuel_service.get(db, tx_id))
