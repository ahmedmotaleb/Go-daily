"""Data quality (U49): records that are missing or unfinished.

This page is about *missing* data: things not recorded, not sent or not
finished. It never calls anything suspicious; suspicious patterns are review
cases (exception engine) and are only counted here, with a link, so the two
are not mixed up. Each check returns a count and up to 10 examples with a
link to fix them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.time import local_today, to_local_date, utcnow
from app.models.assignment import DriverVehicleAssignment
from app.models.attachment import Attachment, AttachmentKind, AttachmentOwner
from app.models.cash import ShiftCloseout
from app.models.driver import Driver, EmploymentStatus
from app.models.exceptions import OperationalException
from app.models.finance import Expense, FuelTransaction, RecordStatus, RevenueEntry
from app.models.fleet import Vehicle
from app.models.operations import RouteDefinition, RouteStop
from app.models.shift import Shift, ShiftStatus
from app.models.tracking import GpsPoint, GpsUploadBatch
from app.services.exception_rules import RULE_INFO
from app.services.exceptions import ACTIVE as ACTIVE_CASES

SAMPLE = 10
LOOKBACK = timedelta(days=30)


@dataclass
class Example:
    title: str
    link: str | None = None


@dataclass
class Check:
    code: str
    title: str
    why: str
    count: int = 0
    examples: list[Example] = field(default_factory=list)


@dataclass
class ReviewCount:
    rule_code: str
    title: str
    count: int


@dataclass
class Report:
    missing: list[Check]
    review: list[ReviewCount]
    generated_at: datetime


def _day(at: datetime | None) -> str:
    return str(to_local_date(at)) if at else "—"


def _closeouts_missing(db: Session, now: datetime) -> Check:
    c = Check(
        "CLOSEOUT_MISSING",
        "ورديات منتهية بدون تقفيل",
        "لا يظهر تحصيلها ومصروفاتها في حساب السائق حتى يُرسل التقفيل.",
    )
    has = exists().where(ShiftCloseout.shift_id == Shift.id, ShiftCloseout.voided_at.is_(None))
    stmt = select(Shift).where(
        Shift.status == ShiftStatus.COMPLETED,
        Shift.ended_at < now - timedelta(hours=12),
        Shift.ended_at >= now - LOOKBACK,
        ~has,
    )
    rows = db.scalars(stmt.order_by(Shift.ended_at.desc())).all()
    c.count = len(rows)
    c.examples = [
        Example(
            f"{s.vehicle.internal_code} — {s.driver.full_name} — {_day(s.ended_at)}",
            f"/shifts/{s.id}",
        )
        for s in rows[:SAMPLE]
    ]
    return c


def _fuel_without_odometer(db: Session, now: datetime) -> Check:
    c = Check(
        "FUEL_NO_ODOMETER",
        "وقود بدون قراءة عداد",
        "بدون العداد لا يمكن حساب الاستهلاك لكل كيلومتر.",
    )
    stmt = select(FuelTransaction).where(
        FuelTransaction.odometer_km.is_(None),
        FuelTransaction.status.in_((RecordStatus.SUBMITTED, RecordStatus.APPROVED)),
        FuelTransaction.occurred_at >= now - LOOKBACK,
    )
    rows = db.scalars(stmt.order_by(FuelTransaction.occurred_at.desc())).all()
    c.count = len(rows)
    c.examples = [
        Example(
            f"{t.vehicle.internal_code} — {t.fuel_type.name_ar} — {_day(t.occurred_at)}",
            f"/finance/fuel/{t.id}",
        )
        for t in rows[:SAMPLE]
    ]
    return c


def _revenue_unreviewed(db: Session, now: datetime) -> Check:
    c = Check(
        "REVENUE_UNRECONCILED",
        "إيرادات لم تُعتمد بعد ثلاثة أيام",
        "لا تدخل في المطابقة والربحية المعتمدة حتى تُراجع.",
    )
    stmt = select(RevenueEntry).where(
        RevenueEntry.status == RecordStatus.SUBMITTED,
        RevenueEntry.occurred_on <= (local_today() - timedelta(days=3)),
    )
    rows = db.scalars(stmt.order_by(RevenueEntry.occurred_on)).all()
    c.count = len(rows)
    c.examples = [
        Example(f"{r.vehicle.internal_code} — {r.occurred_on}", f"/finance/revenue/{r.id}")
        for r in rows[:SAMPLE]
    ]
    return c


def _stale_assignments(db: Session, today: date) -> Check:
    c = Check(
        "ASSIGNMENT_STALE",
        "تكليفات سارية لسيارة أو سائق غير متاح",
        "السيارة موقوفة، أو السائق لم يعد يعمل، أو رخصته منتهية.",
    )
    rows = db.execute(
        select(DriverVehicleAssignment, Vehicle, Driver)
        .join(Vehicle, Vehicle.id == DriverVehicleAssignment.vehicle_id)
        .join(Driver, Driver.id == DriverVehicleAssignment.driver_id)
        .where(
            DriverVehicleAssignment.ends_at.is_(None),
            or_(
                Vehicle.is_active.is_(False),
                Driver.employment_status != EmploymentStatus.ACTIVE,
                Driver.license_expiry < today,
            ),
        )
    ).all()
    c.count = len(rows)
    c.examples = [
        Example(f"{v.internal_code} — {d.full_name}", f"/vehicles/{v.id}")
        for _, v, d in rows[:SAMPLE]
    ]
    return c


def _routes_without_geofences(db: Session) -> Check:
    c = Check(
        "ROUTE_NO_GEOFENCE",
        "مسارات بدون محطات محددة على الخريطة",
        "لا يمكن اكتشاف الدورات والاتجاهات بدون محطتين على الأقل بإحداثيات.",
    )
    located = (
        select(func.count())
        .select_from(RouteStop)
        .where(
            RouteStop.route_id == RouteDefinition.id,
            RouteStop.latitude.is_not(None),
            RouteStop.longitude.is_not(None),
        )
        .scalar_subquery()
    )
    rows = db.scalars(
        select(RouteDefinition).where(RouteDefinition.is_active.is_(True), located < 2)
    ).all()
    c.count = len(rows)
    c.examples = [Example(r.name, f"/operations/routes/{r.id}") for r in rows[:SAMPLE]]
    return c


def _vehicle_documents(db: Session) -> Check:
    c = Check(
        "VEHICLE_DOCUMENTS",
        "سيارات بدون بيانات أو صور المستندات",
        "تاريخ انتهاء الرخصة أو التأمين غير مسجل، أو لا توجد صورة مستند.",
    )
    has_doc = exists().where(
        Attachment.owner_type == AttachmentOwner.VEHICLE,
        Attachment.owner_id == Vehicle.id,
        Attachment.kind == AttachmentKind.VEHICLE_DOCUMENT,
        Attachment.deleted_at.is_(None),
    )
    rows = db.scalars(
        select(Vehicle).where(
            Vehicle.is_active.is_(True),
            or_(Vehicle.license_expiry.is_(None), Vehicle.insurance_expiry.is_(None), ~has_doc),
        )
    ).all()
    c.count = len(rows)
    c.examples = [Example(v.internal_code, f"/vehicles/{v.id}") for v in rows[:SAMPLE]]
    return c


def _gps_unsynced(db: Session, now: datetime) -> Check:
    c = Check(
        "GPS_UNSYNCED",
        "ورديات منتهية بدون مسار كامل",
        "لم تصل نقاط موقع، أو الهاتف أبلغ عن نقاط لم تُرسل بعد.",
    )
    latest = aliased(GpsUploadBatch)
    newest_pending = (
        select(latest.pending_points)
        .where(latest.shift_id == Shift.id)
        .order_by(latest.received_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    no_points = ~exists().where(GpsPoint.shift_id == Shift.id)
    rows = db.scalars(
        select(Shift).where(
            Shift.status == ShiftStatus.COMPLETED,
            Shift.ended_at >= now - timedelta(days=7),
            or_(no_points, and_(newest_pending.is_not(None), newest_pending > 0)),
        )
    ).all()
    c.count = len(rows)
    c.examples = [
        Example(
            f"{s.vehicle.internal_code} — {s.driver.full_name} — {_day(s.ended_at)}",
            f"/shifts/{s.id}",
        )
        for s in rows[:SAMPLE]
    ]
    return c


def _corrections_unresolved(db: Session, now: datetime) -> Check:
    c = Check(
        "CORRECTION_UNRESOLVED",
        "قيود أُعيدت للتعديل ولم تُصحح",
        "قيود رفضتها المراجعة منذ أكثر من يومين ولم يُدخل تصحيحها.",
    )
    cutoff = now - timedelta(days=2)
    examples: list[Example] = []
    total = 0
    models: tuple[tuple[Any, str, str], ...] = (
        (FuelTransaction, "/finance/fuel", "وقود"),
        (Expense, "/finance/expenses", "مصروف"),
        (RevenueEntry, "/finance/revenue", "إيراد"),
    )
    for model, path, label in models:
        newer = aliased(model)
        fixed = exists().where(newer.corrects_id == model.id)
        rows = db.scalars(
            select(model).where(
                model.status == RecordStatus.REJECTED, model.updated_at < cutoff, ~fixed
            )
        ).all()
        total += len(rows)
        examples += [
            Example(f"{label} — {r.vehicle.internal_code}", f"{path}/{r.id}") for r in rows
        ]
    c.count = total
    c.examples = examples[:SAMPLE]
    return c


def _review_counts(db: Session) -> list[ReviewCount]:
    rows = db.execute(
        select(OperationalException.rule_code, func.count())
        .where(OperationalException.status.in_(ACTIVE_CASES))
        .group_by(OperationalException.rule_code)
        .order_by(func.count().desc())
    ).all()
    return [
        ReviewCount(code, RULE_INFO[code].title_ar if code in RULE_INFO else code, n)
        for code, n in rows
    ]


def report(db: Session) -> Report:
    now = utcnow()
    checks = [
        _closeouts_missing(db, now),
        _gps_unsynced(db, now),
        _fuel_without_odometer(db, now),
        _revenue_unreviewed(db, now),
        _corrections_unresolved(db, now),
        _stale_assignments(db, local_today()),
        _routes_without_geofences(db),
        _vehicle_documents(db),
    ]
    return Report(missing=checks, review=_review_counts(db), generated_at=now)


__all__ = ["Check", "Example", "Report", "ReviewCount", "report"]
