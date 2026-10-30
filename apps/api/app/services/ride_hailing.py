"""Ride-hailing statements and reconciliation (Task 14).

Platform earnings are entered manually from the platform's statement (no
scraping, no unofficial integration). Approving a statement generates its
revenue entry (gross income, platform fees withheld) and receipts:

- cash paid by riders to the driver: driver custody (capped at the net;
  any excess cash belongs to the platform and is shown as owed to it);
- the electronic payout: received by the driver or the company.

Voiding or correcting a statement voids everything it generated.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError, field_error
from app.core.time import local_day_bounds_utc, to_local_date, utcnow
from app.models.driver import Driver
from app.models.finance import (
    PaymentMethod,
    ReceivedBy,
    RecordStatus,
    RevenueEntry,
    RevenueKind,
    RideHailingPlatform,
    RideHailingStatement,
)
from app.models.fleet import Vehicle
from app.models.operations import OperationKind, OperationType
from app.models.shift import OperationSession, SessionStatus, Shift, ShiftStatus
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.finance import (
    PlatformCreate,
    PlatformUpdate,
    ReceiptIn,
    RevenueFields,
    StatementCorrection,
    StatementCreate,
    StatementFields,
)
from app.services import audit, revenue, tracking
from app.services import finance_common as fc
from app.services.common import apply_changes, paginate

ENTITY = "ride_hailing_statement"
AUDITED = (
    "platform_id",
    "driver_id",
    "vehicle_id",
    "period_start",
    "period_end",
    "trips_count",
    "gross_earnings",
    "platform_fees",
    "tips",
    "adjustments",
    "cash_collected",
    "payout_recipient",
    "statement_reference",
    "notes",
)
LIVE = (RecordStatus.SUBMITTED, RecordStatus.APPROVED)
ZERO = Decimal("0")


# --- Platforms ----------------------------------------------------------------------


def list_platforms(db: Session, *, include_inactive: bool = False) -> list[RideHailingPlatform]:
    stmt = select(RideHailingPlatform).order_by(RideHailingPlatform.name)
    if not include_inactive:
        stmt = stmt.where(RideHailingPlatform.is_active.is_(True))
    return list(db.scalars(stmt).all())


def create_platform(db: Session, *, actor: User, data: PlatformCreate) -> RideHailingPlatform:
    if db.scalar(select(RideHailingPlatform.id).where(RideHailingPlatform.name == data.name)):
        raise field_error("name", "المنصة موجودة بالفعل", code="duplicate_name")
    platform = RideHailingPlatform(name=data.name, notes=data.notes)
    db.add(platform)
    db.flush()
    audit.record(
        db,
        action="ride_hailing_platform.created",
        actor=actor,
        entity_type="ride_hailing_platform",
        entity_id=platform.id,
        details={"name": data.name},
    )
    db.commit()
    return platform


def update_platform(
    db: Session, *, actor: User, platform_id: uuid.UUID, data: PlatformUpdate
) -> RideHailingPlatform:
    platform = db.get(RideHailingPlatform, platform_id)
    if platform is None:
        raise NotFoundError("المنصة غير موجودة")
    fields = data.model_dump(exclude_unset=True)
    if fields.get("name") and fields["name"] != platform.name:
        exists = db.scalar(
            select(RideHailingPlatform.id).where(RideHailingPlatform.name == fields["name"])
        )
        if exists:
            raise field_error("name", "المنصة موجودة بالفعل", code="duplicate_name")
    changes = apply_changes(platform, fields, ("name", "is_active", "notes"))
    if changes:
        audit.record(
            db,
            action="ride_hailing_platform.updated",
            actor=actor,
            entity_type="ride_hailing_platform",
            entity_id=platform.id,
            changes=changes,
        )
    db.commit()
    return platform


# --- Statements -------------------------------------------------------------------------


def get(db: Session, statement_id: uuid.UUID) -> RideHailingStatement:
    statement = db.get(RideHailingStatement, statement_id)
    if statement is None:
        raise NotFoundError("الكشف غير موجود")
    return statement


def revenue_entry_for(db: Session, statement_id: uuid.UUID) -> RevenueEntry | None:
    return db.scalar(
        select(RevenueEntry)
        .options(selectinload(RevenueEntry.receipts))
        .where(
            RevenueEntry.statement_id == statement_id,
            RevenueEntry.status != RecordStatus.VOIDED,
        )
    )


def _check_overlap(db: Session, s: RideHailingStatement) -> None:
    clash = db.scalar(
        select(RideHailingStatement.id).where(
            RideHailingStatement.driver_id == s.driver_id,
            RideHailingStatement.platform_id == s.platform_id,
            RideHailingStatement.status.in_(LIVE),
            RideHailingStatement.period_start <= s.period_end,
            RideHailingStatement.period_end >= s.period_start,
            RideHailingStatement.id != s.id,
        )
    )
    if clash:
        raise field_error(
            "period_start",
            "يوجد كشف آخر لنفس السائق والمنصة يغطي جزءًا من هذه الفترة",
            code="overlapping_statement",
        )


def _validate(db: Session, s: RideHailingStatement) -> None:
    fc.check_day(s.period_end, "period_end")
    if s.period_end < s.period_start:
        raise field_error("period_end", "نهاية الفترة قبل بدايتها")
    if s.income < 0:
        raise field_error("adjustments", "إجمالي الدخل لا يمكن أن يكون سالبًا")
    if s.platform_fees > s.income:
        raise field_error("platform_fees", "عمولة المنصة أكبر من إجمالي الدخل")
    _check_overlap(db, s)


def _new(
    db: Session,
    *,
    actor: User,
    data: StatementFields,
    corrects: RideHailingStatement | None = None,
) -> RideHailingStatement:
    platform = db.get(RideHailingPlatform, data.platform_id)
    if platform is None or not platform.is_active:
        raise field_error("platform_id", "المنصة غير موجودة أو غير مفعلة")
    if db.get(Driver, data.driver_id) is None:
        raise field_error("driver_id", "السائق غير موجود")
    if db.get(Vehicle, data.vehicle_id) is None:
        raise field_error("vehicle_id", "المركبة غير موجودة")
    statement = RideHailingStatement(
        **data.model_dump(include=set(AUDITED) | {"attachment_id"}),
        status=RecordStatus.SUBMITTED,
        created_by_id=actor.id,
        corrects_id=corrects.id if corrects else None,
    )
    db.add(statement)
    db.flush()
    _validate(db, statement)
    return statement


def _receipt_time(day: date) -> datetime:
    end_of_day = local_day_bounds_utc(day)[1] - timedelta(seconds=1)
    return min(end_of_day, utcnow())


def _ride_hailing_type(db: Session) -> uuid.UUID | None:
    return db.scalar(
        select(OperationType.id)
        .where(OperationType.kind == OperationKind.RIDE_HAILING, OperationType.is_active.is_(True))
        .order_by(OperationType.sort_order)
        .limit(1)
    )


def _generate_revenue(db: Session, s: RideHailingStatement, actor: User) -> RevenueEntry:
    entry = revenue.create_system(
        db,
        actor=actor,
        data=RevenueFields(
            kind=RevenueKind.RIDE_HAILING,
            vehicle_id=s.vehicle_id,
            driver_id=s.driver_id,
            operation_type_id=_ride_hailing_type(db),
            occurred_on=s.period_end,
            period_start=s.period_start,
            period_end=s.period_end,
            amount=s.income,
            reference=s.statement_reference,
        ),
        fees_withheld=s.platform_fees,
        statement_id=s.id,
    )
    at = _receipt_time(s.period_end)
    cash = min(s.cash_collected, s.net_earnings)
    if cash > 0:
        revenue.add_receipt_to(
            db,
            entry,
            ReceiptIn(
                amount=cash,
                received_at=at,
                method=PaymentMethod.CASH,
                received_by=ReceivedBy.DRIVER,
                reference=s.statement_reference,
                notes="نقدي من الركاب (كشف منصة)",
            ),
            actor,
        )
    if s.platform_payout > 0:
        revenue.add_receipt_to(
            db,
            entry,
            ReceiptIn(
                amount=s.platform_payout,
                received_at=at,
                method=PaymentMethod.PLATFORM,
                received_by=s.payout_recipient,
                reference=s.statement_reference,
                notes="تحويل المنصة (كشف منصة)",
            ),
            actor,
        )
    return entry


def _approve(db: Session, s: RideHailingStatement, actor: User, note: str | None) -> None:
    fc.approve(s, actor, note)
    entry = _generate_revenue(db, s, actor)
    audit.record(
        db,
        action=f"{ENTITY}.approved",
        actor=actor,
        entity_type=ENTITY,
        entity_id=s.id,
        details={"revenue_entry_id": entry.id, **({"note": note} if note else {})},
    )


def create(
    db: Session, *, actor: User, data: StatementCreate, can_approve: bool = False
) -> RideHailingStatement:
    statement = _new(db, actor=actor, data=data)
    audit.record(
        db,
        action=f"{ENTITY}.created",
        actor=actor,
        entity_type=ENTITY,
        entity_id=statement.id,
        changes=audit.diff({}, audit.snapshot(statement, AUDITED)),
    )
    if data.approve_now and can_approve:
        _approve(db, statement, actor, note="اعتماد عند الإدخال")
    db.commit()
    return statement


def update(
    db: Session, *, actor: User, statement_id: uuid.UUID, data: StatementFields
) -> RideHailingStatement:
    statement = get(db, statement_id)
    fc.ensure_editable(statement)
    if db.get(RideHailingPlatform, data.platform_id) is None:
        raise field_error("platform_id", "المنصة غير موجودة")
    changes = apply_changes(
        statement, data.model_dump(include=set(AUDITED) | {"attachment_id"}), AUDITED
    )
    db.flush()
    _validate(db, statement)
    fc.resubmit_if_rejected(statement)
    if changes:
        audit.record(
            db,
            action=f"{ENTITY}.updated",
            actor=actor,
            entity_type=ENTITY,
            entity_id=statement.id,
            changes=changes,
        )
    db.commit()
    return statement


def approve(
    db: Session, *, actor: User, statement_id: uuid.UUID, note: str | None
) -> RideHailingStatement:
    statement = get(db, statement_id)
    _approve(db, statement, actor, note)
    db.commit()
    return statement


def reject(
    db: Session, *, actor: User, statement_id: uuid.UUID, reason: str
) -> RideHailingStatement:
    statement = get(db, statement_id)
    fc.reject(statement, actor, reason)
    audit.record(
        db,
        action=f"{ENTITY}.rejected",
        actor=actor,
        entity_type=ENTITY,
        entity_id=statement.id,
        reason=reason,
    )
    db.commit()
    return statement


def _void(db: Session, s: RideHailingStatement, actor: User, reason: str) -> None:
    previous = fc.void(s, actor, reason)
    if previous is RecordStatus.APPROVED:
        entry = revenue_entry_for(db, s.id)
        if entry is not None:
            revenue.void_with_receipts(db, entry, actor, reason)
    audit.record(
        db,
        action=f"{ENTITY}.voided",
        actor=actor,
        entity_type=ENTITY,
        entity_id=s.id,
        reason=reason,
    )


def void(db: Session, *, actor: User, statement_id: uuid.UUID, reason: str) -> RideHailingStatement:
    statement = get(db, statement_id)
    _void(db, statement, actor, reason)
    db.commit()
    return statement


def correct(
    db: Session,
    *,
    actor: User,
    statement_id: uuid.UUID,
    data: StatementCorrection,
    can_approve: bool,
) -> RideHailingStatement:
    original = get(db, statement_id)
    fc.ensure_correctable(original)
    _void(db, original, actor, f"تصحيح: {data.reason}")
    db.flush()
    replacement = _new(db, actor=actor, data=data, corrects=original)
    audit.record(
        db,
        action=f"{ENTITY}.corrected",
        actor=actor,
        entity_type=ENTITY,
        entity_id=replacement.id,
        reason=data.reason,
        changes=audit.diff(audit.snapshot(original, AUDITED), audit.snapshot(replacement, AUDITED)),
        details={"corrects_id": original.id},
    )
    if data.approve_now and can_approve:
        _approve(db, replacement, actor, note="اعتماد التصحيح")
    db.commit()
    return replacement


@dataclass(frozen=True)
class StatementFilters:
    platform_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None
    vehicle_id: uuid.UUID | None = None
    status: RecordStatus | None = None
    date_from: date | None = None
    date_to: date | None = None


def _filtered(f: StatementFilters) -> Select[RideHailingStatement]:
    stmt = select(RideHailingStatement)
    if f.platform_id:
        stmt = stmt.where(RideHailingStatement.platform_id == f.platform_id)
    if f.driver_id:
        stmt = stmt.where(RideHailingStatement.driver_id == f.driver_id)
    if f.vehicle_id:
        stmt = stmt.where(RideHailingStatement.vehicle_id == f.vehicle_id)
    if f.status:
        stmt = stmt.where(RideHailingStatement.status == f.status)
    if f.date_from:
        stmt = stmt.where(RideHailingStatement.period_end >= f.date_from)
    if f.date_to:
        stmt = stmt.where(RideHailingStatement.period_start <= f.date_to)
    return stmt


def list_statements(
    db: Session, params: PageParams, filters: StatementFilters
) -> tuple[list[RideHailingStatement], int]:
    stmt = _filtered(filters).order_by(
        RideHailingStatement.period_end.desc(), RideHailingStatement.created_at.desc()
    )
    return paginate(db, stmt, params)


def revenue_ids(db: Session, statement_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    if not statement_ids:
        return {}
    rows = db.execute(
        select(RevenueEntry.statement_id, RevenueEntry.id).where(
            RevenueEntry.statement_id.in_(statement_ids),
            RevenueEntry.status != RecordStatus.VOIDED,
        )
    ).all()
    return {sid: rid for sid, rid in rows if sid is not None}


# --- Reconciliation -------------------------------------------------------------------


@dataclass
class DayActivity:
    shift_ids: set[uuid.UUID]
    ride_minutes: int = 0


@dataclass
class ReconRow:
    statement: RideHailingStatement | None
    driver: Driver
    vehicle: Vehicle
    period_start: date
    period_end: date
    shifts_count: int
    ride_hailing_minutes: int
    odometer_km: int | None
    gps_km: float | None
    net_per_hour: Decimal | None
    net_per_km: Decimal | None
    flags: list[tuple[str, str]]


def _activity(
    db: Session,
    date_from: date,
    date_to: date,
    driver_id: uuid.UUID | None,
    vehicle_id: uuid.UUID | None,
) -> tuple[dict[tuple[uuid.UUID, uuid.UUID, date], DayActivity], dict[uuid.UUID, Shift]]:
    """Ride-hailing session minutes per (driver, vehicle, local day)."""
    start = local_day_bounds_utc(date_from)[0]
    end = local_day_bounds_utc(date_to)[1]
    stmt = (
        select(OperationSession, Shift)
        .join(Shift, Shift.id == OperationSession.shift_id)
        .join(OperationType, OperationType.id == OperationSession.operation_type_id)
        .where(
            OperationType.kind == OperationKind.RIDE_HAILING,
            Shift.status.in_((ShiftStatus.ACTIVE, ShiftStatus.COMPLETED)),
            OperationSession.started_at >= start,
            OperationSession.started_at < end,
        )
    )
    if driver_id:
        stmt = stmt.where(Shift.driver_id == driver_id)
    if vehicle_id:
        stmt = stmt.where(Shift.vehicle_id == vehicle_id)
    days: dict[tuple[uuid.UUID, uuid.UUID, date], DayActivity] = {}
    shifts: dict[uuid.UUID, Shift] = {}
    now = utcnow()
    for session, shift in db.execute(stmt).all():
        if session.status is SessionStatus.CANCELLED:
            continue
        key = (shift.driver_id, shift.vehicle_id, to_local_date(session.started_at))
        day = days.setdefault(key, DayActivity(shift_ids=set()))
        day.shift_ids.add(shift.id)
        ended = session.ended_at or now
        day.ride_minutes += max(0, int((ended - session.started_at).total_seconds() // 60))
        shifts[shift.id] = shift
    return days, shifts


def _ratio(amount: Decimal, divisor: float | int | None) -> Decimal | None:
    if not divisor:
        return None
    return fc.money(amount / Decimal(str(divisor)))


def reconciliation(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    driver_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
) -> tuple[list[ReconRow], list[ReconRow]]:
    statements = list(
        db.scalars(
            _filtered(
                StatementFilters(
                    driver_id=driver_id, vehicle_id=vehicle_id, date_from=date_from, date_to=date_to
                )
            )
            .where(RideHailingStatement.status.in_(LIVE))
            .order_by(RideHailingStatement.period_start)
        ).all()
    )
    span_from = min([date_from, *(s.period_start for s in statements)])
    span_to = max([date_to, *(s.period_end for s in statements)])
    days, shifts = _activity(db, span_from, span_to, driver_id, vehicle_id)
    gps = tracking.gps_distance_km(db, list(shifts))

    def summarise(keys: list[tuple[uuid.UUID, uuid.UUID, date]]) -> tuple[set[uuid.UUID], int]:
        shift_ids: set[uuid.UUID] = set()
        minutes = 0
        for key in keys:
            shift_ids |= days[key].shift_ids
            minutes += days[key].ride_minutes
        return shift_ids, minutes

    def distances(shift_ids: set[uuid.UUID]) -> tuple[int | None, float | None, bool]:
        if not shift_ids:
            return None, None, False
        odo = [shifts[s].odometer_distance_km for s in shift_ids]
        missing = any(v is None for v in odo)
        odometer = sum(v for v in odo if v is not None)
        return odometer, round(sum(gps.get(s, 0.0) for s in shift_ids), 2), missing

    covered: set[tuple[uuid.UUID, uuid.UUID, date]] = set()
    rows: list[ReconRow] = []
    for s in statements:
        keys = [
            k
            for k in days
            if k[0] == s.driver_id
            and k[1] == s.vehicle_id
            and s.period_start <= k[2] <= s.period_end
        ]
        covered.update(keys)
        shift_ids, minutes = summarise(keys)
        odometer, gps_km, missing_odo = distances(shift_ids)
        flags: list[tuple[str, str]] = []
        if s.status is RecordStatus.SUBMITTED:
            flags.append(("PENDING_REVIEW", "الكشف لم يُعتمد بعد"))
        if not shift_ids:
            flags.append(
                ("NO_SHIFTS", "لا توجد ورديات نقل ذكي مسجلة في فترة الكشف — مراجعة مطلوبة")
            )
        if missing_odo:
            flags.append(("MISSING_ODOMETER", "بعض الورديات بدون قراءة عداد نهائية"))
        if s.trips_count and minutes == 0:
            flags.append(
                ("TRIPS_WITHOUT_TIME", "رحلات في الكشف بدون وقت تشغيل مسجل — حالة غير معتادة")
            )
        if s.platform_payout < 0:
            flags.append(("OWED_TO_PLATFORM", f"مستحق للمنصة {fc.money(-s.platform_payout)}"))
        rows.append(
            ReconRow(
                statement=s,
                driver=s.driver,
                vehicle=s.vehicle,
                period_start=s.period_start,
                period_end=s.period_end,
                shifts_count=len(shift_ids),
                ride_hailing_minutes=minutes,
                odometer_km=odometer,
                gps_km=gps_km,
                net_per_hour=_ratio(s.net_earnings, minutes / 60 if minutes else None),
                net_per_km=_ratio(s.net_earnings, odometer),
                flags=flags,
            )
        )

    uncovered_groups: dict[tuple[uuid.UUID, uuid.UUID], list[date]] = defaultdict(list)
    for key in days:
        if key not in covered and date_from <= key[2] <= date_to:
            uncovered_groups[(key[0], key[1])].append(key[2])
    uncovered: list[ReconRow] = []
    for (d_id, v_id), day_list in uncovered_groups.items():
        day_list.sort()
        keys = [(d_id, v_id, d) for d in day_list]
        shift_ids, minutes = summarise(keys)
        odometer, gps_km, _ = distances(shift_ids)
        first_shift = shifts[next(iter(shift_ids))]
        uncovered.append(
            ReconRow(
                statement=None,
                driver=first_shift.driver,
                vehicle=first_shift.vehicle,
                period_start=day_list[0],
                period_end=day_list[-1],
                shifts_count=len(shift_ids),
                ride_hailing_minutes=minutes,
                odometer_km=odometer,
                gps_km=gps_km,
                net_per_hour=None,
                net_per_km=None,
                flags=[
                    (
                        "NO_STATEMENT",
                        f"{len(day_list)} يوم تشغيل نقل ذكي بدون كشف منصة — مراجعة مطلوبة",
                    )
                ],
            )
        )
    uncovered.sort(key=lambda r: (r.period_start, r.driver.full_name))
    return rows, uncovered


def uncovered_days(db: Session, *, date_from: date, date_to: date) -> dict[uuid.UUID, int]:
    """Per vehicle: ride-hailing work days with no live statement covering them."""
    days, _ = _activity(db, date_from, date_to, None, None)
    statements = db.execute(
        select(
            RideHailingStatement.driver_id,
            RideHailingStatement.vehicle_id,
            RideHailingStatement.period_start,
            RideHailingStatement.period_end,
        ).where(
            RideHailingStatement.status.in_(LIVE),
            RideHailingStatement.period_end >= date_from,
            RideHailingStatement.period_start <= date_to,
        )
    ).all()
    out: dict[uuid.UUID, int] = defaultdict(int)
    for driver_id, vehicle_id, day in days:
        covered = any(
            d == driver_id and v == vehicle_id and start <= day <= end
            for d, v, start, end in statements
        )
        if not covered:
            out[vehicle_id] += 1
    return dict(out)
