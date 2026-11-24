"""Pilot command center and daily close (U50/U51).

For each vehicle marked as part of the pilot, one day at a time: who drove,
the shifts, tracking and GPS quality, distance (GPS and odometer), loops and
operations, fuel, expenses, revenue, the close-out and cash handed over, and
open review cases; then a daily close that checks each of those and gives
one verdict: اليوم مكتمل / بيانات ناقصة / يحتاج مراجعة.

Everything comes from recorded data; a check that cannot be made says so.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.time import local_day_bounds_utc, local_today
from app.models.assignment import DriverVehicleAssignment
from app.models.cash import DriverDayOff
from app.models.exceptions import ExceptionStatus, OperationalException
from app.models.finance import Expense, FuelTransaction, RecordStatus, RevenueEntry
from app.models.fleet import Vehicle
from app.models.shift import SessionStatus, Shift, ShiftStatus
from app.services import cash, route_events, tracking
from app.services import finance_common as fc
from app.services.gps_quality import QualityGrade
from app.services.odometer_reconciliation import ReconciliationStatus

ZERO = Decimal("0")
LIVE = (RecordStatus.SUBMITTED, RecordStatus.APPROVED)
OPEN_CASES = (ExceptionStatus.OPEN, ExceptionStatus.UNDER_REVIEW, ExceptionStatus.ESCALATED)


class CheckState(StrEnum):
    OK = "OK"
    MISSING = "MISSING"  # بيانات ناقصة
    REVIEW = "REVIEW"  # يحتاج مراجعة
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Verdict(StrEnum):
    COMPLETE = "COMPLETE"  # اليوم مكتمل
    INCOMPLETE = "INCOMPLETE"  # بيانات ناقصة
    NEEDS_REVIEW = "NEEDS_REVIEW"  # يحتاج مراجعة


VERDICT_AR = {
    Verdict.COMPLETE: "اليوم مكتمل",
    Verdict.INCOMPLETE: "بيانات ناقصة",
    Verdict.NEEDS_REVIEW: "يحتاج مراجعة",
}


@dataclass
class Check:
    code: str
    label: str
    state: CheckState
    detail: str


@dataclass
class ShiftLine:
    shift_id: uuid.UUID
    driver_name: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    operations: list[str]
    gps_km: float
    odometer_km: int | None
    gps_grade: str
    odometer_status: str
    loops: int = 0
    legs: int = 0


@dataclass
class PilotDay:
    vehicle_id: uuid.UUID
    vehicle_code: str
    plate_number: str
    day: date
    drivers: list[str]
    day_off: bool
    shifts: list[ShiftLine]
    tracking_state: str | None
    last_received_at: datetime | None
    fuel: Decimal
    expenses: Decimal
    revenue: Decimal
    closeout_net: Decimal
    collected: Decimal
    remaining: Decimal
    open_cases: list[tuple[uuid.UUID, str]]
    checks: list[Check] = field(default_factory=list)
    verdict: Verdict = Verdict.COMPLETE

    @property
    def verdict_ar(self) -> str:
        return VERDICT_AR[self.verdict]


def pilot_vehicles(db: Session) -> list[Vehicle]:
    return list(
        db.scalars(
            select(Vehicle).where(Vehicle.pilot.is_(True)).order_by(Vehicle.internal_code)
        ).all()
    )


def _drivers(db: Session, vehicle_id: uuid.UUID, start: datetime, end: datetime) -> list[uuid.UUID]:
    rows = db.scalars(
        select(DriverVehicleAssignment).where(
            DriverVehicleAssignment.vehicle_id == vehicle_id,
            DriverVehicleAssignment.starts_at < end,
            or_(
                DriverVehicleAssignment.ends_at.is_(None),
                DriverVehicleAssignment.ends_at >= start,
            ),
        )
    ).all()
    return [a.driver_id for a in rows]


def _shifts(db: Session, vehicle_id: uuid.UUID, start: datetime, end: datetime) -> list[Shift]:
    return list(
        db.scalars(
            select(Shift)
            .where(
                Shift.vehicle_id == vehicle_id,
                Shift.status.in_((ShiftStatus.ACTIVE, ShiftStatus.COMPLETED)),
                Shift.started_at >= start,
                Shift.started_at < end,
            )
            .order_by(Shift.started_at)
        ).all()
    )


def _shift_line(db: Session, shift: Shift) -> ShiftLine:
    track = tracking.shift_track(db, shift.id)
    sessions = [s for s in shift.sessions if s.status is not SessionStatus.CANCELLED]
    counts = route_events.counts(db, [s.id for s in sessions])
    line = ShiftLine(
        shift_id=shift.id,
        driver_name=shift.driver.full_name,
        status=shift.status.value,
        started_at=shift.started_at,
        ended_at=shift.ended_at,
        operations=[
            s.operation_type.name_ar + (f" — {s.route.name}" if s.route else "") for s in sessions
        ],
        gps_km=round(track.gps_distance_km, 1),
        odometer_km=track.odometer_distance_km,
        gps_grade=track.quality.grade.value,
        odometer_status=track.odometer_reconciliation.status.value,
    )
    for s in sessions:
        line.loops += counts.get(s.id, {}).get("loops", 0)
        line.legs += counts.get(s.id, {}).get("legs", 0)
    return line


def _sum(
    db: Session, column: InstrumentedAttribute[Decimal], *where: ColumnElement[bool]
) -> Decimal:
    total = db.scalar(select(func.coalesce(func.sum(column), 0)).where(*where))
    return fc.money(Decimal(total or 0))


def _pending(
    db: Session, model: type[FuelTransaction] | type[Expense], *where: ColumnElement[bool]
) -> int:
    stmt = select(func.count()).select_from(model).where(model.status == RecordStatus.SUBMITTED)
    return int(db.scalar(stmt.where(*where)) or 0)


# ------------------------------------------------------------------ checks


def _check_shifts(d: PilotDay) -> Check:
    label = "الوردية"
    if not d.shifts:
        if d.day_off:
            return Check("SHIFT", label, CheckState.OK, "يوم إجازة مسجل")
        return Check("SHIFT", label, CheckState.MISSING, "لا توجد وردية ولا إجازة مسجلة لهذا اليوم")
    running = [s for s in d.shifts if s.status == ShiftStatus.ACTIVE.value]
    if running:
        return Check("SHIFT", label, CheckState.MISSING, "الوردية لم تنتهِ بعد")
    return Check("SHIFT", label, CheckState.OK, f"{len(d.shifts)} وردية منتهية")


def _check_gps(d: PilotDay) -> Check:
    label = "مزامنة GPS وجودته"
    done = [s for s in d.shifts if s.status == ShiftStatus.COMPLETED.value]
    if not done:
        return Check("GPS", label, CheckState.NOT_APPLICABLE, "لا توجد وردية منتهية")
    if any(s.gps_km == 0 and s.gps_grade == QualityGrade.INSUFFICIENT.value for s in done):
        return Check("GPS", label, CheckState.MISSING, "وردية بلا نقاط GPS كافية — قد لم تُرفع بعد")
    weak = [
        s for s in done if s.gps_grade in (QualityGrade.NEEDS_REVIEW, QualityGrade.INSUFFICIENT)
    ]
    if weak:
        return Check("GPS", label, CheckState.REVIEW, "جودة بيانات الموقع تحتاج مراجعة")
    return Check("GPS", label, CheckState.OK, "بيانات الموقع كاملة")


def _check_odometer(d: PilotDay) -> Check:
    label = "عداد النهاية ومطابقته مع GPS"
    done = [s for s in d.shifts if s.status == ShiftStatus.COMPLETED.value]
    if not done:
        return Check("ODOMETER", label, CheckState.NOT_APPLICABLE, "لا توجد وردية منتهية")
    statuses = {s.odometer_status for s in done}
    if ReconciliationStatus.MISSING_ODOMETER.value in statuses:
        return Check("ODOMETER", label, CheckState.MISSING, "قراءة العداد ناقصة")
    if statuses & {ReconciliationStatus.REVIEW.value, ReconciliationStatus.INSUFFICIENT_GPS.value}:
        return Check("ODOMETER", label, CheckState.REVIEW, "فرق بين العداد وGPS أو تغطية غير كافية")
    km = sum(s.odometer_km or 0 for s in done)
    return Check("ODOMETER", label, CheckState.OK, f"{km} كم ضمن الحد المسموح")


def _check_operations(d: PilotDay, routed: bool) -> Check:
    label = "التشغيل والدورات"
    if not d.shifts:
        return Check("OPERATIONS", label, CheckState.NOT_APPLICABLE, "لا توجد وردية")
    if not any(s.operations for s in d.shifts):
        return Check("OPERATIONS", label, CheckState.MISSING, "لم يُسجل نوع التشغيل")
    if routed and not any(s.loops or s.legs for s in d.shifts):
        return Check("OPERATIONS", label, CheckState.REVIEW, "خط ثابت بلا دورات أو اتجاهات مكتشفة")
    loops = sum(s.loops for s in d.shifts)
    legs = sum(s.legs for s in d.shifts)
    return Check("OPERATIONS", label, CheckState.OK, f"{loops} دورة · {legs} اتجاه")


def _check_records(code: str, label: str, pending: int, total: Decimal) -> Check:
    if pending:
        return Check(code, label, CheckState.REVIEW, f"{pending} قيد بانتظار الاعتماد")
    return Check(code, label, CheckState.OK, f"{total} ج.م" if total else "لا توجد قيود")


def _check_closeout(d: PilotDay, missing_closeouts: int, pending_revenue: int) -> Check:
    label = "الإيراد والتقفيل"
    done = [s for s in d.shifts if s.status == ShiftStatus.COMPLETED.value]
    if not done:
        return Check("REVENUE", label, CheckState.NOT_APPLICABLE, "لا توجد وردية منتهية")
    if missing_closeouts:
        return Check("REVENUE", label, CheckState.MISSING, "تقفيل الوردية لم يُرسل")
    if pending_revenue:
        return Check(
            "REVENUE", label, CheckState.REVIEW, f"{pending_revenue} إيراد بانتظار الاعتماد"
        )
    return Check("REVENUE", label, CheckState.OK, f"{d.revenue} ج.م")


def _check_cash(d: PilotDay, closeouts: int) -> Check:
    label = "تسليم النقدية"
    if not closeouts:
        return Check("CASH", label, CheckState.NOT_APPLICABLE, "لا يوجد تقفيل")
    if d.remaining > 0:
        return Check("CASH", label, CheckState.MISSING, f"متبقي {d.remaining} ج.م لم يُسلّم")
    return Check("CASH", label, CheckState.OK, f"تم تسليم {d.collected} ج.م")


def _check_cases(d: PilotDay) -> Check:
    label = "حالات المراجعة"
    if d.open_cases:
        return Check("REVIEW", label, CheckState.REVIEW, f"{len(d.open_cases)} حالة مفتوحة")
    return Check("REVIEW", label, CheckState.OK, "لا توجد حالات مفتوحة")


def _verdict(checks: list[Check]) -> Verdict:
    states = {c.state for c in checks}
    if CheckState.MISSING in states:
        return Verdict.INCOMPLETE
    if CheckState.REVIEW in states:
        return Verdict.NEEDS_REVIEW
    return Verdict.COMPLETE


# ------------------------------------------------------------------ day


def _cash(db: Session, d: PilotDay, shifts: list[Shift]) -> tuple[int, int]:
    """Fills close-out figures; returns (close-outs, completed shifts without one)."""
    closeouts = [c for s in shifts if (c := cash.live_closeout(db, s.id)) is not None]
    missing = sum(
        1
        for s in shifts
        if s.status is ShiftStatus.COMPLETED and cash.live_closeout(db, s.id) is None
    )
    if closeouts:
        views = cash.driver_views(db, {c.driver_id for c in closeouts})
        for c in closeouts:
            view = views[c.driver_id]
            figures = view.figures.get(c.id)
            position = view.positions.get(c.id)
            if figures is not None:
                d.closeout_net += figures.net
            if position is not None:
                d.collected += position.collected
                d.remaining += position.remaining
        # Collections recorded without naming a close-out still settle the
        # driver's balance: what is left for the day is at most what is owed.
        owed = sum((v.outstanding for v in views.values()), ZERO)
        d.remaining = max(ZERO, min(d.remaining, owed))
    return len(closeouts), missing


def day(db: Session, vehicle: Vehicle, on: date) -> PilotDay:
    start, end = local_day_bounds_utc(on)
    shifts = _shifts(db, vehicle.id, start, end)
    driver_ids = _drivers(db, vehicle.id, start, end) or [s.driver_id for s in shifts]
    off = db.scalar(
        select(func.count())
        .select_from(DriverDayOff)
        .where(
            DriverDayOff.driver_id.in_(driver_ids),
            DriverDayOff.day == on,
            DriverDayOff.cancelled_at.is_(None),
        )
    )
    # The live state belongs to today only; a past day shows none.
    live = (
        next((p for p in tracking.live_positions(db) if p.vehicle_id == vehicle.id), None)
        if on == local_today()
        else None
    )
    in_day_fuel = (
        FuelTransaction.vehicle_id == vehicle.id,
        FuelTransaction.occurred_at >= start,
        FuelTransaction.occurred_at < end,
    )
    in_day_expense = (
        Expense.vehicle_id == vehicle.id,
        Expense.occurred_at >= start,
        Expense.occurred_at < end,
    )
    in_day_revenue = (RevenueEntry.vehicle_id == vehicle.id, RevenueEntry.occurred_on == on)
    d = PilotDay(
        vehicle_id=vehicle.id,
        vehicle_code=vehicle.internal_code,
        plate_number=vehicle.plate_number,
        day=on,
        drivers=sorted({s.driver.full_name for s in shifts}),
        day_off=bool(off),
        shifts=[_shift_line(db, s) for s in shifts],
        tracking_state=live.state if live else None,
        last_received_at=live.last_received_at if live else None,
        fuel=_sum(db, FuelTransaction.total_amount, FuelTransaction.status.in_(LIVE), *in_day_fuel),
        expenses=_sum(db, Expense.amount, Expense.status.in_(LIVE), *in_day_expense),
        revenue=_sum(db, RevenueEntry.amount, RevenueEntry.status.in_(LIVE), *in_day_revenue),
        closeout_net=ZERO,
        collected=ZERO,
        remaining=ZERO,
        open_cases=[
            (c.id, c.summary)
            for c in db.scalars(
                select(OperationalException).where(
                    OperationalException.vehicle_id == vehicle.id,
                    OperationalException.status.in_(OPEN_CASES),
                    OperationalException.occurred_at >= start,
                    OperationalException.occurred_at < end,
                )
            ).all()
        ],
    )
    closeouts, missing_closeouts = _cash(db, d, shifts)
    pending_revenue = int(
        db.scalar(
            select(func.count())
            .select_from(RevenueEntry)
            .where(RevenueEntry.status == RecordStatus.SUBMITTED, *in_day_revenue)
        )
        or 0
    )
    routed = any(x.route_id for s in shifts for x in s.sessions)
    d.checks = [
        _check_shifts(d),
        _check_gps(d),
        _check_odometer(d),
        _check_operations(d, routed),
        _check_records("FUEL", "الوقود", _pending(db, FuelTransaction, *in_day_fuel), d.fuel),
        _check_records("EXPENSES", "المصروفات", _pending(db, Expense, *in_day_expense), d.expenses),
        _check_closeout(d, missing_closeouts, pending_revenue),
        _check_cash(d, closeouts),
        _check_cases(d),
    ]
    d.verdict = _verdict(d.checks)
    return d


__all__ = ["Check", "CheckState", "PilotDay", "Verdict", "day", "pilot_vehicles"]
