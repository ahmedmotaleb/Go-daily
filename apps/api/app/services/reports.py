"""Reports (Task 23): one shape for every report, JSON and CSV.

Each report lists source records as rows; totals are sums of those same
rows, so every total can be traced back to the records behind it.
Financial reports count approved records only (stated in the notes).
Nothing is estimated: missing readings stay empty.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import NotFoundError, PermissionDenied, ValidationFailed, field_error
from app.core.permissions import Permission, has_permission
from app.core.time import local_day_bounds_utc, to_local_date
from app.models.driver import Driver
from app.models.exceptions import OperationalException
from app.models.finance import (
    DriverLedgerEntry,
    Expense,
    FuelTransaction,
    LedgerEntryType,
    RecordStatus,
    RevenueEntry,
)
from app.models.fleet import Vehicle
from app.models.maintenance import MaintenanceRecord
from app.models.operations import RouteDefinition
from app.models.route_events import SchoolRun
from app.models.shift import OperationSession, SessionStatus, Shift, ShiftStatus
from app.models.user import User
from app.services import driver_ledger, profitability, ride_hailing, route_events, tracking
from app.services import finance_common as fc
from app.services import revenue as revenue_service
from app.services.exception_rules import RULE_INFO

ColumnType = Literal["text", "number", "money", "date", "datetime", "minutes", "km"]

MAX_DAYS = 366
MAX_ROWS = 20_000


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    type: ColumnType = "text"
    total: bool = False


@dataclass
class Table:
    columns: list[Column]
    rows: list[dict[str, Any]]

    def totals(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for c in self.columns:
            if not c.total:
                continue
            values: list[Any] = [r[c.key] for r in self.rows if r.get(c.key) is not None]
            if c.type == "money":
                out[c.key] = fc.money(sum((Decimal(v) for v in values), Decimal("0")))
            elif c.type == "km":
                out[c.key] = round(sum(float(v) for v in values), 2)
            else:
                out[c.key] = sum(values)
        return out


@dataclass
class ReportResult:
    table: Table
    summaries: list[tuple[str, Table]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Filters:
    date_from: date
    date_to: date
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None
    operation_type_id: uuid.UUID | None = None
    route_id: uuid.UUID | None = None
    fuel_type_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None

    @property
    def start(self) -> datetime:
        return local_day_bounds_utc(self.date_from)[0]

    @property
    def end(self) -> datetime:
        return local_day_bounds_utc(self.date_to)[1]


FilterName = Literal["vehicle", "driver", "operation_type", "route", "fuel_type", "category"]


@dataclass(frozen=True)
class ReportDef:
    code: str
    title: str
    description: str
    permissions: tuple[Permission, ...]
    filters: tuple[FilterName, ...]
    build: Callable[[Session, Filters], ReportResult]


APPROVED_ONLY = "يشمل السجلات المعتمدة فقط؛ السجلات بانتظار المراجعة لا تدخل في الإجماليات."

REVENUE_KIND_AR = {
    "FIXED_ROUTE_COLLECTION": "تحصيل خط ثابت",
    "CONTRACT_SERVICE": "عقد خدمة",
    "PRIVATE_TRIP": "رحلة خاصة",
    "RIDE_HAILING": "نقل ذكي",
    "OTHER": "أخرى",
}
PAID_BY_AR = {"COMPANY": "الشركة", "DRIVER": "السائق"}
UNIT_AR = {"LITER": "لتر", "CUBIC_METER": "م³", "KG": "كجم", "UNIT": "وحدة"}
SCHOOL_STATUS_AR = {
    "SCHEDULED": "مجدولة",
    "IN_PROGRESS": "جارية",
    "COMPLETED": "مكتملة",
    "COMPLETED_UNVERIFIED": "انتهت بدون دليل GPS",
    "MISSED": "فائتة",
    "CANCELLED": "ملغاة",
}
SHIFT_STATUS_AR = {"ACTIVE": "جارية", "COMPLETED": "منتهية"}
EXC_STATUS_AR = {
    "OPEN": "مفتوحة",
    "UNDER_REVIEW": "قيد المراجعة",
    "ESCALATED": "مُصعّدة",
    "EXPLAINED": "تم التوضيح",
    "CORRECTED": "تم التصحيح",
    "DISMISSED": "مستبعدة",
}
EXC_LABEL_AR = {"REVIEW_REQUIRED": "مراجعة مطلوبة", "UNUSUAL": "حالة غير معتادة"}
SEVERITY_AR = {"HIGH": "عالية", "MEDIUM": "متوسطة", "LOW": "منخفضة"}


def _minutes(a: datetime | None, b: datetime | None) -> int | None:
    if a is None or b is None:
        return None
    return max(0, int((b - a).total_seconds() // 60))


def _limit[T](rows: list[T]) -> list[T]:
    if len(rows) > MAX_ROWS:
        raise ValidationFailed("النتائج كثيرة جدًا؛ ضيّق الفترة أو أضف عوامل تصفية")
    return rows


# --- Operations ---------------------------------------------------------------


def _shifts(db: Session, f: Filters) -> list[Shift]:
    stmt = select(Shift).where(
        Shift.status.in_((ShiftStatus.ACTIVE, ShiftStatus.COMPLETED)),
        Shift.started_at >= f.start,
        Shift.started_at < f.end,
    )
    if f.vehicle_id:
        stmt = stmt.where(Shift.vehicle_id == f.vehicle_id)
    if f.driver_id:
        stmt = stmt.where(Shift.driver_id == f.driver_id)
    if f.operation_type_id:
        stmt = stmt.where(
            Shift.id.in_(
                select(OperationSession.shift_id).where(
                    OperationSession.operation_type_id == f.operation_type_id
                )
            )
        )
    return _limit(list(db.scalars(stmt.order_by(Shift.started_at)).all()))


def daily_operations(db: Session, f: Filters) -> ReportResult:
    shifts = _shifts(db, f)
    gps = tracking.gps_distance_km(db, [s.id for s in shifts])
    rows: list[dict[str, Any]] = []
    for s in shifts:
        if s.started_at is None:
            continue
        ops = sorted(
            {
                x.operation_type.name_ar + (f" — {x.route.name}" if x.route else "")
                for x in s.sessions
                if x.status is not SessionStatus.CANCELLED
            }
        )
        rows.append(
            {
                "day": to_local_date(s.started_at),
                "vehicle": s.vehicle.internal_code,
                "driver": s.driver.full_name,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "minutes": _minutes(s.started_at, s.ended_at),
                "operations": "، ".join(ops),
                "odometer_km": s.odometer_distance_km,
                "gps_km": round(gps.get(s.id, 0.0), 2),
                "status": SHIFT_STATUS_AR.get(s.status.value, s.status.value),
            }
        )
    return ReportResult(
        Table(
            [
                Column("day", "اليوم", "date"),
                Column("vehicle", "المركبة"),
                Column("driver", "السائق"),
                Column("started_at", "البداية", "datetime"),
                Column("ended_at", "النهاية", "datetime"),
                Column("minutes", "المدة (دقيقة)", "minutes", total=True),
                Column("operations", "التشغيل"),
                Column("odometer_km", "كم العداد", "km", total=True),
                Column("gps_km", "كم GPS", "km", total=True),
                Column("status", "الحالة"),
            ],
            rows,
        ),
        notes=[
            "المسافات كما سُجلت: الورديات الجارية أو بدون قراءة عداد نهائية تظهر فارغة ولا تُقدّر.",
            "مسافة GPS تجمع النقاط الصالحة المتتالية فقط ولا تسد فترات الانقطاع.",
        ],
    )


def route_loops(db: Session, f: Filters) -> ReportResult:
    stmt = (
        select(OperationSession)
        .join(Shift, Shift.id == OperationSession.shift_id)
        .where(
            OperationSession.route_id.is_not(None),
            OperationSession.status != SessionStatus.CANCELLED,
            OperationSession.started_at >= f.start,
            OperationSession.started_at < f.end,
        )
    )
    if f.vehicle_id:
        stmt = stmt.where(Shift.vehicle_id == f.vehicle_id)
    if f.driver_id:
        stmt = stmt.where(Shift.driver_id == f.driver_id)
    if f.route_id:
        stmt = stmt.where(OperationSession.route_id == f.route_id)
    if f.operation_type_id:
        stmt = stmt.where(OperationSession.operation_type_id == f.operation_type_id)
    sessions = _limit(list(db.scalars(stmt.order_by(OperationSession.started_at)).all()))
    counts = route_events.counts(db, [s.id for s in sessions])
    rows: list[dict[str, Any]] = []
    for s in sessions:
        if s.route is None:
            continue
        rows.append(
            {
                "day": to_local_date(s.started_at),
                "route": s.route.name,
                "operation": s.operation_type.name_ar,
                "vehicle": s.shift.vehicle.internal_code,
                "driver": s.shift.driver.full_name,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "minutes": _minutes(s.started_at, s.ended_at),
                "loops": counts[s.id]["loops"],
                "legs": counts[s.id]["legs"],
            }
        )
    by_route: dict[str, dict[str, Any]] = {}
    for r in rows:
        g = by_route.setdefault(r["route"], {"route": r["route"], "sessions": 0, "loops": 0})
        g["sessions"] += 1
        g["loops"] += r["loops"]
    return ReportResult(
        Table(
            [
                Column("day", "اليوم", "date"),
                Column("route", "المسار"),
                Column("operation", "التشغيل"),
                Column("vehicle", "المركبة"),
                Column("driver", "السائق"),
                Column("started_at", "البداية", "datetime"),
                Column("ended_at", "النهاية", "datetime"),
                Column("minutes", "المدة (دقيقة)", "minutes", total=True),
                Column("loops", "دورات مكتملة", "number", total=True),
                Column("legs", "اتجاهات مكتملة", "number", total=True),
            ],
            rows,
        ),
        summaries=[
            (
                "حسب المسار",
                Table(
                    [
                        Column("route", "المسار"),
                        Column("sessions", "مرات التشغيل", "number", total=True),
                        Column("loops", "دورات مكتملة", "number", total=True),
                    ],
                    sorted(by_route.values(), key=lambda g: g["route"]),
                ),
            )
        ],
        notes=["الدورات محسوبة من نقاط GPS عند نقاط المسار، مع التصحيحات اليدوية الموثقة."],
    )


def school_runs(db: Session, f: Filters) -> ReportResult:
    stmt = select(SchoolRun).where(
        SchoolRun.service_date >= f.date_from, SchoolRun.service_date <= f.date_to
    )
    if f.vehicle_id:
        stmt = stmt.where(SchoolRun.vehicle_id == f.vehicle_id)
    if f.driver_id:
        stmt = stmt.where(SchoolRun.driver_id == f.driver_id)
    if f.route_id:
        stmt = stmt.where(SchoolRun.route_id == f.route_id)
    runs = _limit(
        list(db.scalars(stmt.order_by(SchoolRun.service_date, SchoolRun.scheduled_start_at)).all())
    )
    vehicles = {v.id: v.internal_code for v in db.scalars(select(Vehicle)).all()}
    drivers = {d.id: d.full_name for d in db.scalars(select(Driver)).all()}
    routes = {r.id: r.name for r in db.scalars(select(RouteDefinition)).all()}
    rows: list[dict[str, Any]] = [
        {
            "day": r.service_date,
            "route": routes.get(r.route_id),
            "label": r.label,
            "vehicle": vehicles.get(r.vehicle_id),
            "driver": drivers.get(r.driver_id) if r.driver_id else None,
            "scheduled_start_at": r.scheduled_start_at,
            "actual_start_at": r.actual_start_at,
            "actual_end_at": r.actual_end_at,
            "status": SCHOOL_STATUS_AR.get(r.status.value, r.status.value),
        }
        for r in runs
    ]
    by_status: dict[str, int] = defaultdict(int)
    for r in rows:
        by_status[r["status"]] += 1
    return ReportResult(
        Table(
            [
                Column("day", "اليوم", "date"),
                Column("route", "المسار"),
                Column("label", "الدورة"),
                Column("vehicle", "المركبة"),
                Column("driver", "السائق"),
                Column("scheduled_start_at", "الموعد", "datetime"),
                Column("actual_start_at", "البداية الفعلية", "datetime"),
                Column("actual_end_at", "النهاية الفعلية", "datetime"),
                Column("status", "الحالة"),
            ],
            rows,
        ),
        summaries=[
            (
                "حسب الحالة",
                Table(
                    [Column("status", "الحالة"), Column("count", "العدد", "number", total=True)],
                    [{"status": k, "count": v} for k, v in sorted(by_status.items())],
                ),
            )
        ],
        notes=["الدورة تُعد مكتملة فقط بدليل GPS؛ غير ذلك يظهر كـ «انتهت بدون دليل GPS»."],
    )


def gps_odometer(db: Session, f: Filters) -> ReportResult:
    shifts = [s for s in _shifts(db, f) if s.status is ShiftStatus.COMPLETED]
    gps = tracking.gps_distance_km(db, [s.id for s in shifts])
    rows: list[dict[str, Any]] = []
    for s in shifts:
        if s.started_at is None:
            continue
        odo = s.odometer_distance_km
        g = round(gps.get(s.id, 0.0), 2)
        diff = round(odo - g, 2) if odo is not None else None
        rows.append(
            {
                "day": to_local_date(s.started_at),
                "vehicle": s.vehicle.internal_code,
                "driver": s.driver.full_name,
                "odometer_km": odo,
                "gps_km": g,
                "difference_km": diff,
                "difference_pct": round(100 * diff / odo, 1) if diff is not None and odo else None,
            }
        )
    return ReportResult(
        Table(
            [
                Column("day", "اليوم", "date"),
                Column("vehicle", "المركبة"),
                Column("driver", "السائق"),
                Column("odometer_km", "كم العداد", "km", total=True),
                Column("gps_km", "كم GPS", "km", total=True),
                Column("difference_km", "الفرق (كم)", "km", total=True),
                Column("difference_pct", "الفرق (%)", "number"),
            ],
            rows,
        ),
        notes=[
            "الفرق الموجب: العداد أكبر من GPS (غالبًا بسبب انقطاع بيانات الموقع أو قراءة خاطئة).",
            "الفروق الكبيرة تظهر كحالات للمراجعة عند توفر تغطية GPS كافية.",
        ],
    )


# --- Finance ------------------------------------------------------------------


def ride_hailing_report(db: Session, f: Filters) -> ReportResult:
    rows_, uncovered = ride_hailing.reconciliation(
        db, date_from=f.date_from, date_to=f.date_to, driver_id=f.driver_id, vehicle_id=f.vehicle_id
    )
    rows: list[dict[str, Any]] = []
    for r in _limit(rows_):
        st = r.statement
        if st is None:
            continue
        rows.append(
            {
                "period_start": r.period_start,
                "period_end": r.period_end,
                "platform": st.platform.name,
                "driver": r.driver.full_name,
                "vehicle": r.vehicle.internal_code,
                "status": "معتمد" if st.status is RecordStatus.APPROVED else "بانتظار المراجعة",
                "trips": st.trips_count,
                "gross": fc.money(st.gross_earnings),
                "fees": fc.money(st.platform_fees),
                "net": fc.money(st.net_earnings),
                "minutes": r.ride_hailing_minutes,
                "odometer_km": r.odometer_km,
                "net_per_hour": r.net_per_hour,
                "flags": "، ".join(text for _, text in r.flags),
            }
        )
    return ReportResult(
        Table(
            [
                Column("period_start", "من", "date"),
                Column("period_end", "إلى", "date"),
                Column("platform", "المنصة"),
                Column("driver", "السائق"),
                Column("vehicle", "المركبة"),
                Column("status", "الحالة"),
                Column("trips", "الرحلات", "number", total=True),
                Column("gross", "إجمالي الأرباح", "money", total=True),
                Column("fees", "عمولة المنصة", "money", total=True),
                Column("net", "الصافي", "money", total=True),
                Column("minutes", "دقائق التشغيل", "minutes", total=True),
                Column("odometer_km", "كم العداد", "km", total=True),
                Column("net_per_hour", "الصافي/ساعة", "money"),
                Column("flags", "ملاحظات المطابقة"),
            ],
            rows,
        ),
        summaries=[
            (
                "أيام نقل ذكي بدون كشف منصة",
                Table(
                    [
                        Column("driver", "السائق"),
                        Column("vehicle", "المركبة"),
                        Column("period_start", "من", "date"),
                        Column("period_end", "إلى", "date"),
                        Column("minutes", "دقائق التشغيل", "minutes", total=True),
                    ],
                    [
                        {
                            "driver": u.driver.full_name,
                            "vehicle": u.vehicle.internal_code,
                            "period_start": u.period_start,
                            "period_end": u.period_end,
                            "minutes": u.ride_hailing_minutes,
                        }
                        for u in uncovered
                    ],
                ),
            )
        ],
        notes=[
            "الكشوف تُدخل يدويًا من بيانات المنصة؛ لا يوجد ربط آلي.",
            "تشمل الكشوف المعتمدة وبانتظار المراجعة (الحالة في عمود منفصل).",
        ],
    )


def revenue_report(db: Session, f: Filters) -> ReportResult:
    stmt = (
        select(RevenueEntry)
        .options(selectinload(RevenueEntry.receipts))
        .where(
            RevenueEntry.status == RecordStatus.APPROVED,
            RevenueEntry.occurred_on >= f.date_from,
            RevenueEntry.occurred_on <= f.date_to,
        )
    )
    if f.vehicle_id:
        stmt = stmt.where(RevenueEntry.vehicle_id == f.vehicle_id)
    if f.driver_id:
        stmt = stmt.where(RevenueEntry.driver_id == f.driver_id)
    if f.operation_type_id:
        stmt = stmt.where(RevenueEntry.operation_type_id == f.operation_type_id)
    entries = _limit(list(db.scalars(stmt.order_by(RevenueEntry.occurred_on)).all()))
    rows: list[dict[str, Any]] = [
        {
            "day": e.occurred_on,
            "kind": REVENUE_KIND_AR.get(e.kind.value, e.kind.value),
            "vehicle": e.vehicle.internal_code,
            "driver": e.driver.full_name if e.driver else None,
            "amount": fc.money(e.amount),
            "fees": fc.money(e.fees_withheld),
            "net": fc.money(revenue_service.net_amount(e)),
            "received": fc.money(revenue_service.received(e)),
            "outstanding": fc.money(revenue_service.outstanding(e)),
            "reference": e.reference,
        }
        for e in entries
    ]
    return ReportResult(
        Table(
            [
                Column("day", "التاريخ", "date"),
                Column("kind", "النوع"),
                Column("vehicle", "المركبة"),
                Column("driver", "السائق"),
                Column("amount", "المبلغ", "money", total=True),
                Column("fees", "عمولة/خصم", "money", total=True),
                Column("net", "الصافي", "money", total=True),
                Column("received", "المستلم", "money", total=True),
                Column("outstanding", "المتبقي", "money", total=True),
                Column("reference", "المرجع"),
            ],
            rows,
        ),
        summaries=[("حسب النوع", _group(rows, "kind", "النوع", ["amount", "net", "received"]))],
        notes=[APPROVED_ONLY, "إيرادات النقل الذكي تأتي من كشوف المنصات المعتمدة فقط."],
    )


_GROUP_LABELS = {
    "amount": "المبلغ",
    "net": "الصافي",
    "received": "المستلم",
    "total": "الإجمالي",
    "quantity": "الكمية",
}


def _group(rows: list[dict[str, Any]], key: str, label: str, money: list[str]) -> Table:
    groups: dict[str, dict[str, Any]] = {}
    for r in rows:
        g = groups.setdefault(r[key], {key: r[key], "count": 0, **{m: Decimal("0") for m in money}})
        g["count"] += 1
        for m in money:
            g[m] += Decimal(r[m] or 0)
    for g in groups.values():
        for m in money:
            g[m] = fc.money(g[m])
    return Table(
        [
            Column(key, label),
            Column("count", "عدد السجلات", "number", total=True),
            *(Column(m, _GROUP_LABELS[m], "money", total=True) for m in money),
        ],
        sorted(groups.values(), key=lambda g: str(g[key])),
    )


def expenses_report(db: Session, f: Filters) -> ReportResult:
    stmt = select(Expense).where(
        Expense.status == RecordStatus.APPROVED,
        Expense.occurred_at >= f.start,
        Expense.occurred_at < f.end,
    )
    if f.vehicle_id:
        stmt = stmt.where(Expense.vehicle_id == f.vehicle_id)
    if f.driver_id:
        stmt = stmt.where(Expense.driver_id == f.driver_id)
    if f.category_id:
        stmt = stmt.where(Expense.category_id == f.category_id)
    items = _limit(list(db.scalars(stmt.order_by(Expense.occurred_at)).all()))
    rows: list[dict[str, Any]] = [
        {
            "occurred_at": e.occurred_at,
            "vehicle": e.vehicle.internal_code,
            "driver": e.driver.full_name if e.driver else None,
            "category": e.category.name_ar,
            "amount": fc.money(e.amount),
            "paid_by": PAID_BY_AR.get(e.paid_by.value, e.paid_by.value),
            "vendor": e.vendor,
        }
        for e in items
    ]
    return ReportResult(
        Table(
            [
                Column("occurred_at", "الوقت", "datetime"),
                Column("vehicle", "المركبة"),
                Column("driver", "السائق"),
                Column("category", "التصنيف"),
                Column("amount", "المبلغ", "money", total=True),
                Column("paid_by", "الدفع بواسطة"),
                Column("vendor", "المورد"),
            ],
            rows,
        ),
        summaries=[("حسب التصنيف", _group(rows, "category", "التصنيف", ["amount"]))],
        notes=[APPROVED_ONLY],
    )


def fuel_report(db: Session, f: Filters) -> ReportResult:
    stmt = select(FuelTransaction).where(
        FuelTransaction.status == RecordStatus.APPROVED,
        FuelTransaction.occurred_at >= f.start,
        FuelTransaction.occurred_at < f.end,
    )
    if f.vehicle_id:
        stmt = stmt.where(FuelTransaction.vehicle_id == f.vehicle_id)
    if f.driver_id:
        stmt = stmt.where(FuelTransaction.driver_id == f.driver_id)
    if f.fuel_type_id:
        stmt = stmt.where(FuelTransaction.fuel_type_id == f.fuel_type_id)
    items = _limit(list(db.scalars(stmt.order_by(FuelTransaction.occurred_at)).all()))
    rows: list[dict[str, Any]] = [
        {
            "occurred_at": t.occurred_at,
            "vehicle": t.vehicle.internal_code,
            "driver": t.driver.full_name if t.driver else None,
            "fuel_type": t.fuel_type.name_ar,
            "quantity": t.quantity,
            "unit": UNIT_AR.get(t.unit.value, t.unit.value),
            "unit_price": t.unit_price,
            "total": fc.money(t.total_amount),
            "odometer_km": t.odometer_km,
            "vendor": t.vendor,
        }
        for t in items
    ]
    by_type: dict[str, dict[str, Any]] = {}
    for r in rows:
        g = by_type.setdefault(
            r["fuel_type"],
            {
                "fuel_type": r["fuel_type"],
                "unit": r["unit"],
                "count": 0,
                "quantity": Decimal("0"),
                "total": Decimal("0"),
            },
        )
        g["count"] += 1
        g["quantity"] += r["quantity"]
        g["total"] += r["total"]
    for g in by_type.values():
        g["total"] = fc.money(g["total"])
    return ReportResult(
        Table(
            [
                Column("occurred_at", "الوقت", "datetime"),
                Column("vehicle", "المركبة"),
                Column("driver", "السائق"),
                Column("fuel_type", "النوع"),
                Column("quantity", "الكمية", "number"),
                Column("unit", "الوحدة"),
                Column("unit_price", "سعر الوحدة", "number"),
                Column("total", "الإجمالي", "money", total=True),
                Column("odometer_km", "العداد"),
                Column("vendor", "المحطة/المورد"),
            ],
            rows,
        ),
        summaries=[
            (
                "حسب النوع",
                Table(
                    [
                        Column("fuel_type", "النوع"),
                        Column("unit", "الوحدة"),
                        Column("count", "عدد السجلات", "number", total=True),
                        Column("quantity", "الكمية", "number"),
                        Column("total", "الإجمالي", "money", total=True),
                    ],
                    sorted(by_type.values(), key=lambda g: g["fuel_type"]),
                ),
            )
        ],
        notes=[
            APPROVED_ONLY,
            "الزيوت والمستهلكات أنواع مستقلة ولا تُجمع مع كميات الوقود (وحدات مختلفة).",
        ],
    )


_LEDGER_COLUMNS = [
    ("earnings", "المستحقات", (LedgerEntryType.EARNING, LedgerEntryType.BONUS)),
    ("reimbursements", "تعويض مصروفات", (LedgerEntryType.REIMBURSEMENT,)),
    ("cash_collected", "نقدية بحوزة السائق", (LedgerEntryType.CASH_COLLECTED,)),
    ("cash_handover", "نقدية مُسلّمة", (LedgerEntryType.CASH_HANDOVER,)),
    ("advances", "سلف وخصومات", (LedgerEntryType.ADVANCE, LedgerEntryType.DEDUCTION)),
    ("payments", "مدفوعات للسائق", (LedgerEntryType.PAYMENT,)),
    ("adjustments", "تسويات يدوية", (LedgerEntryType.ADJUSTMENT,)),
]


def driver_statements(db: Session, f: Filters) -> ReportResult:
    stmt = select(Driver).order_by(Driver.full_name)
    if f.driver_id:
        stmt = stmt.where(Driver.id == f.driver_id)
    with_entries = set(
        db.scalars(
            select(DriverLedgerEntry.driver_id).where(
                DriverLedgerEntry.occurred_on >= f.date_from,
                DriverLedgerEntry.occurred_on <= f.date_to,
            )
        ).all()
    )
    rows: list[dict[str, Any]] = []
    for d in _limit(list(db.scalars(stmt).all())):
        totals = driver_ledger.statement(db, d.id, f.date_from, f.date_to)
        if d.id not in with_entries and totals.opening == 0:
            continue
        row: dict[str, Any] = {"driver": d.full_name, "opening": fc.money(totals.opening)}
        for key, _, types in _LEDGER_COLUMNS:
            row[key] = fc.money(
                sum((totals.by_type.get(t, Decimal("0")) for t in types), Decimal("0"))
            )
        row["closing"] = fc.money(totals.closing)
        rows.append(row)
    return ReportResult(
        Table(
            [
                Column("driver", "السائق"),
                Column("opening", "الرصيد الافتتاحي", "money", total=True),
                *(Column(k, label, "money", total=True) for k, label, _ in _LEDGER_COLUMNS),
                Column("closing", "الرصيد الختامي", "money", total=True),
            ],
            rows,
        ),
        notes=[
            "الرصيد = ما تستحقه الشركة للسائق؛ السالب يعني أن على السائق مبلغًا للشركة.",
            "القيود الملغاة لا تدخل في الأرصدة. التفاصيل في كشف حساب كل سائق.",
        ],
    )


def vehicle_profitability(db: Session, f: Filters) -> ReportResult:
    results, totals = profitability.compute(db, f.date_from, f.date_to, f.vehicle_id)
    rows: list[dict[str, Any]] = [
        {
            "vehicle": r["vehicle"]["name"],
            "shifts": r["shifts_count"],
            "odometer_km": r["odometer_km"],
            "gross_revenue": r["gross_revenue"],
            "platform_fees": r["platform_fees"],
            "fuel_cost": r["fuel_cost"],
            "consumables_cost": r["consumables_cost"],
            "maintenance_cost": r["maintenance_cost"],
            "other_expenses": r["other_expenses"],
            "driver_cost": r["driver_cost"],
            "net_operating_profit": r["net_operating_profit"],
            "cost_per_km": r["cost_per_km"],
            "warnings": "، ".join(
                w["message"] for w in r["warnings"] if w["code"] != "MAINTENANCE_SOURCES"
            ),
        }
        for r in results
    ]
    notes = [
        APPROVED_ONLY,
        "المبالغ ذات الفترة (العقود، الكشوف، مستحقات السائقين) موزعة بالأيام؛ "
        "تكلفة السائق موزعة على المركبات بدقائق القيادة.",
        "الصيانة = سجلات الصيانة المعتمدة + مصروفات تصنيفات الصيانة.",
    ]
    unallocated = totals.get("unallocated_driver_cost") or Decimal("0")
    if unallocated:
        notes.append(f"تكلفة سائقين غير موزعة على مركبة (بدون ورديات مسجلة): {unallocated}")
    return ReportResult(
        Table(
            [
                Column("vehicle", "المركبة"),
                Column("shifts", "الورديات", "number", total=True),
                Column("odometer_km", "كم العداد", "km", total=True),
                Column("gross_revenue", "الإيراد", "money", total=True),
                Column("platform_fees", "عمولات", "money", total=True),
                Column("fuel_cost", "الوقود", "money", total=True),
                Column("consumables_cost", "زيوت ومستهلكات", "money", total=True),
                Column("maintenance_cost", "الصيانة", "money", total=True),
                Column("other_expenses", "مصروفات أخرى", "money", total=True),
                Column("driver_cost", "تكلفة السائق", "money", total=True),
                Column("net_operating_profit", "صافي الربح التشغيلي", "money", total=True),
                Column("cost_per_km", "التكلفة/كم", "money"),
                Column("warnings", "بيانات ناقصة"),
            ],
            rows,
        ),
        notes=notes,
    )


def maintenance_report(db: Session, f: Filters) -> ReportResult:
    stmt = select(MaintenanceRecord).where(
        MaintenanceRecord.status == RecordStatus.APPROVED,
        MaintenanceRecord.performed_on >= f.date_from,
        MaintenanceRecord.performed_on <= f.date_to,
    )
    if f.vehicle_id:
        stmt = stmt.where(MaintenanceRecord.vehicle_id == f.vehicle_id)
    items = _limit(list(db.scalars(stmt.order_by(MaintenanceRecord.performed_on)).all()))
    rows: list[dict[str, Any]] = []
    for m in items:
        hours = (
            round((m.downtime_end - m.downtime_start).total_seconds() / 3600, 1)
            if m.downtime_start and m.downtime_end
            else None
        )
        rows.append(
            {
                "day": m.performed_on,
                "vehicle": m.vehicle.internal_code,
                "type": m.type.name_ar,
                "odometer_km": m.odometer_km,
                "vendor": m.vendor,
                "parts": fc.money(m.parts_cost),
                "labor": fc.money(m.labor_cost),
                "other": fc.money(m.other_cost),
                "total": fc.money(m.total_cost),
                "downtime_hours": hours,
            }
        )
    return ReportResult(
        Table(
            [
                Column("day", "التاريخ", "date"),
                Column("vehicle", "المركبة"),
                Column("type", "النوع"),
                Column("odometer_km", "العداد"),
                Column("vendor", "الورشة"),
                Column("parts", "قطع الغيار", "money", total=True),
                Column("labor", "المصنعية", "money", total=True),
                Column("other", "أخرى", "money", total=True),
                Column("total", "الإجمالي", "money", total=True),
                Column("downtime_hours", "ساعات التوقف", "number", total=True),
            ],
            rows,
        ),
        summaries=[("حسب النوع", _group(rows, "type", "النوع", ["total"]))],
        notes=[APPROVED_ONLY, "شراء الزيت يظهر في تقرير الوقود؛ تغييره يظهر هنا."],
    )


def exceptions_report(db: Session, f: Filters) -> ReportResult:
    stmt = select(OperationalException).where(
        OperationalException.occurred_at >= f.start, OperationalException.occurred_at < f.end
    )
    if f.vehicle_id:
        stmt = stmt.where(OperationalException.vehicle_id == f.vehicle_id)
    if f.driver_id:
        stmt = stmt.where(OperationalException.driver_id == f.driver_id)
    items = _limit(list(db.scalars(stmt.order_by(OperationalException.occurred_at)).all()))
    rows: list[dict[str, Any]] = [
        {
            "occurred_at": e.occurred_at,
            "rule": RULE_INFO[e.rule_code].title_ar if e.rule_code in RULE_INFO else e.rule_code,
            "label": EXC_LABEL_AR[e.label.value],
            "severity": SEVERITY_AR[e.severity.value],
            "status": EXC_STATUS_AR[e.status.value],
            "vehicle": e.vehicle.internal_code if e.vehicle else None,
            "driver": e.driver.full_name if e.driver else None,
            "summary": e.summary,
            "resolution": e.resolution,
        }
        for e in items
    ]
    by_rule: dict[str, dict[str, Any]] = {}
    for r in rows:
        g = by_rule.setdefault(r["rule"], {"rule": r["rule"], "count": 0, "open": 0})
        g["count"] += 1
        if r["status"] in (
            EXC_STATUS_AR["OPEN"],
            EXC_STATUS_AR["UNDER_REVIEW"],
            EXC_STATUS_AR["ESCALATED"],
        ):
            g["open"] += 1
    return ReportResult(
        Table(
            [
                Column("occurred_at", "الوقت", "datetime"),
                Column("rule", "القاعدة"),
                Column("label", "التصنيف"),
                Column("severity", "الأهمية"),
                Column("status", "المتابعة"),
                Column("vehicle", "المركبة"),
                Column("driver", "السائق"),
                Column("summary", "الوصف"),
                Column("resolution", "نتيجة المراجعة"),
            ],
            rows,
        ),
        summaries=[
            (
                "حسب القاعدة",
                Table(
                    [
                        Column("rule", "القاعدة"),
                        Column("count", "الحالات", "number", total=True),
                        Column("open", "تحتاج متابعة", "number", total=True),
                    ],
                    sorted(by_rule.values(), key=lambda g: -g["count"]),
                ),
            )
        ],
        notes=["كل حالة إشارة من قاعدة واضحة للمراجعة، وليست حكمًا أو دليلًا على مخالفة."],
    )


P = Permission
REPORTS: list[ReportDef] = [
    ReportDef(
        "daily_operations",
        "التشغيل اليومي",
        "الورديات بالمدة والتشغيل والمسافة بالعداد وGPS.",
        (P.SHIFTS_READ,),
        ("vehicle", "driver", "operation_type"),
        daily_operations,
    ),
    ReportDef(
        "route_loops",
        "دورات الخطوط الثابتة",
        "الدورات والاتجاهات المكتملة لكل تشغيل على مسار.",
        (P.OPERATIONS_READ, P.SHIFTS_READ),
        ("vehicle", "driver", "route", "operation_type"),
        route_loops,
    ),
    ReportDef(
        "school_runs",
        "دورات المدارس",
        "الدورات المجدولة وحالتها والتوقيت الفعلي.",
        (P.OPERATIONS_READ,),
        ("vehicle", "driver", "route"),
        school_runs,
    ),
    ReportDef(
        "ride_hailing",
        "النقل الذكي",
        "كشوف المنصات مع مطابقتها بوقت ومسافة التشغيل المسجل.",
        (P.REVENUE_READ,),
        ("vehicle", "driver"),
        ride_hailing_report,
    ),
    ReportDef(
        "revenue",
        "الإيرادات",
        "الإيرادات المعتمدة والمستلم والمتبقي.",
        (P.REVENUE_READ,),
        ("vehicle", "driver", "operation_type"),
        revenue_report,
    ),
    ReportDef(
        "expenses",
        "المصروفات",
        "المصروفات المعتمدة حسب التصنيف.",
        (P.EXPENSES_READ,),
        ("vehicle", "driver", "category"),
        expenses_report,
    ),
    ReportDef(
        "fuel",
        "الغاز والبنزين والزيوت",
        "سجلات الوقود والزيوت المعتمدة حسب النوع.",
        (P.FUEL_READ,),
        ("vehicle", "driver", "fuel_type"),
        fuel_report,
    ),
    ReportDef(
        "driver_statements",
        "حسابات السائقين",
        "أرصدة وحركة حساب كل سائق في الفترة.",
        (P.SETTLEMENTS_READ,),
        ("driver",),
        driver_statements,
    ),
    ReportDef(
        "vehicle_profitability",
        "ربحية المركبات",
        "الإيراد والتكاليف وصافي الربح لكل مركبة.",
        (P.PROFITABILITY_READ,),
        ("vehicle",),
        vehicle_profitability,
    ),
    ReportDef(
        "gps_odometer",
        "فرق العداد وGPS",
        "مسافة العداد مقابل مسافة GPS لكل وردية منتهية.",
        (P.SHIFTS_READ, P.TRACKING_READ),
        ("vehicle", "driver"),
        gps_odometer,
    ),
    ReportDef(
        "exceptions",
        "حالات المراجعة",
        "الحالات المكتشفة ونتيجة مراجعتها.",
        (P.EXCEPTIONS_READ,),
        ("vehicle", "driver"),
        exceptions_report,
    ),
    ReportDef(
        "maintenance",
        "الصيانة",
        "سجلات الصيانة المعتمدة وتكاليفها والتوقف.",
        (P.MAINTENANCE_READ,),
        ("vehicle",),
        maintenance_report,
    ),
]
BY_CODE = {r.code: r for r in REPORTS}


def can_view(user: User, report: ReportDef) -> bool:
    return has_permission(user.role, P.REPORTS_READ) and all(
        has_permission(user.role, p) for p in report.permissions
    )


def available(user: User) -> list[ReportDef]:
    return [r for r in REPORTS if can_view(user, r)]


def run(db: Session, user: User, code: str, filters: Filters) -> tuple[ReportDef, ReportResult]:
    report = BY_CODE.get(code)
    if report is None:
        raise NotFoundError("التقرير غير موجود")
    # Backend check: the report needs the permissions of the data it shows.
    if not can_view(user, report):
        raise PermissionDenied()
    if filters.date_to < filters.date_from:
        raise field_error("date_to", "تاريخ النهاية قبل تاريخ البداية")
    if (filters.date_to - filters.date_from).days >= MAX_DAYS:
        raise field_error("date_to", "الفترة القصوى سنة واحدة")
    return report, report.build(db, filters)


# --- CSV ----------------------------------------------------------------------

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any, kind: ColumnType) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(get_settings().tz).strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(fc.money(value)) if kind == "money" else str(value)
    text = str(value)
    # Spreadsheet formula injection: text cells never start with a formula sign.
    if kind == "text" and text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def to_csv(report: ReportDef, result: ReportResult) -> str:
    buf = io.StringIO()
    # BOM so Excel opens Arabic text as UTF-8.
    buf.write("﻿")
    writer = csv.writer(buf)
    cols = result.table.columns
    writer.writerow([c.label for c in cols])
    for row in result.table.rows:
        writer.writerow([_cell(row.get(c.key), c.type) for c in cols])
    totals = result.table.totals()
    if totals:
        writer.writerow(
            ["الإجمالي" if i == 0 else _cell(totals.get(c.key), c.type) for i, c in enumerate(cols)]
        )
    return buf.getvalue()
