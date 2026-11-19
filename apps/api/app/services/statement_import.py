"""Ride-hailing statement CSV import (U19).

The platform's own statement export (CSV) is read with a column mapping the
staff choose, checked row by row, previewed, then imported as ordinary
SUBMITTED statements that still go through the usual review. Nothing is
scraped and nothing calls a platform: a direct integration needs an approved
API.

- Mapping: which CSV column holds each field. The last mapping used for a
  platform is remembered.
- Validation: driver (by phone), vehicle (by internal code or plate, else the
  driver's assignment at the start of the period), dates, decimal-safe
  amounts, and the statement rules (fees not above income, ...).
- Duplicates: the same file already imported for the platform, the same row
  twice in the file, a statement reference already recorded, or a period
  already covered by another statement for the driver.
- Reconciliation: rows with no ride-hailing shift recorded for the driver in
  the period are imported but flagged («مراجعة مطلوبة»); the reconciliation
  page then shows them next to the recorded shifts.
- Rollback: voiding a batch voids every statement it created (and their
  revenue, if approved). Nothing is deleted.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailed, field_error
from app.core.phone import InvalidPhoneError, normalize_phone
from app.core.text import plate_key, to_latin_digits
from app.core.time import local_day_bounds_utc, local_today, utcnow
from app.models.assignment import DriverVehicleAssignment
from app.models.driver import Driver
from app.models.finance import (
    ImportBatchStatus,
    RecordStatus,
    RideHailingImportBatch,
    RideHailingPlatform,
    RideHailingStatement,
)
from app.models.fleet import Vehicle
from app.models.user import User
from app.schemas.finance import StatementFields
from app.services import audit, ride_hailing

ENTITY = "ride_hailing_import"
MAX_CHARS = 1_000_000
MAX_ROWS = 2000
LIVE = (RecordStatus.SUBMITTED, RecordStatus.APPROVED)

# field -> (Arabic label, required)
FIELDS: dict[str, tuple[str, bool]] = {
    "driver_phone": ("هاتف السائق", True),
    "vehicle": ("السيارة (الكود أو اللوحة)", False),
    "period_start": ("بداية الفترة", True),
    "period_end": ("نهاية الفترة", False),
    "trips_count": ("عدد الرحلات", False),
    "gross_earnings": ("إجمالي الأجرة", True),
    "platform_fees": ("عمولة المنصة", True),
    "tips": ("البقشيش", False),
    "adjustments": ("حوافز أو تسويات", False),
    "cash_collected": ("نقدية مع السائق", False),
    "statement_reference": ("رقم الكشف", False),
}
MONEY_FIELDS = ("gross_earnings", "platform_fees", "tips", "adjustments", "cash_collected")
# Common header names, so a first import often needs no mapping at all.
GUESSES: dict[str, tuple[str, ...]] = {
    "driver_phone": ("phone", "driver phone", "mobile", "هاتف", "هاتف السائق", "رقم الهاتف"),
    "vehicle": ("vehicle", "car", "plate", "السيارة", "اللوحة", "كود السيارة"),
    "period_start": ("date", "start", "from", "period start", "التاريخ", "من"),
    "period_end": ("end", "to", "period end", "إلى", "الى"),
    "trips_count": ("trips", "trip count", "الرحلات", "عدد الرحلات"),
    "gross_earnings": ("gross", "fares", "gross earnings", "الإجمالي", "إجمالي الأجرة"),
    "platform_fees": ("fees", "commission", "service fee", "العمولة", "عمولة المنصة"),
    "tips": ("tips", "tip", "البقشيش"),
    "adjustments": ("adjustments", "bonus", "incentives", "حوافز", "تسويات"),
    "cash_collected": ("cash", "cash collected", "نقدي", "نقدية"),
    "statement_reference": ("reference", "ref", "statement", "id", "رقم الكشف", "المرجع"),
}


@dataclass
class Row:
    row: int  # 1-based data row number (the header is row 0)
    status: str  # OK | ERROR | DUPLICATE
    messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    driver: str | None = None
    vehicle: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    gross_earnings: Decimal | None = None
    platform_fees: Decimal | None = None
    net_earnings: Decimal | None = None
    statement_reference: str | None = None
    data: StatementFields | None = None


@dataclass
class Preview:
    platform_id: uuid.UUID
    file_name: str
    file_sha256: str
    headers: list[str]
    mapping: dict[str, str]
    rows: list[Row]
    already_imported: bool
    counts: dict[str, int]


# --- Parsing ------------------------------------------------------------------------


def _read(content: str) -> tuple[list[str], list[dict[str, str]]]:
    if len(content) > MAX_CHARS:
        raise field_error("content", "الملف أكبر من 1 ميجابايت؛ قسّمه إلى ملفات أصغر")
    text = content.lstrip("﻿")
    if not text.strip():
        raise field_error("content", "الملف فارغ")
    try:
        dialect: Any = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [h.strip() for h in (reader.fieldnames or []) if h and h.strip()]
    if not headers:
        raise field_error("content", "لم يتم العثور على صف العناوين")
    rows: list[dict[str, str]] = []
    for raw in reader:
        if len(rows) >= MAX_ROWS:
            raise field_error("content", f"الملف فيه أكثر من {MAX_ROWS} صف؛ قسّمه")
        cleaned = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k}
        if any(cleaned.values()):
            rows.append(cleaned)
    return headers, rows


def _norm(header: str) -> str:
    return re.sub(r"[\s_\-]+", " ", header.strip().lower())


def guess_mapping(headers: list[str], saved: dict[str, Any] | None) -> dict[str, str]:
    present = {_norm(h): h for h in headers}
    mapping: dict[str, str] = {}
    for key in FIELDS:
        if saved and isinstance(saved.get(key), str) and _norm(saved[key]) in present:
            mapping[key] = present[_norm(saved[key])]
            continue
        for guess in GUESSES.get(key, ()):
            if _norm(guess) in present:
                mapping[key] = present[_norm(guess)]
                break
    return mapping


def _check_mapping(mapping: dict[str, str], headers: list[str]) -> None:
    unknown = sorted(set(mapping) - set(FIELDS))
    if unknown:
        raise ValidationFailed(
            "حقل غير معروف في الربط", code="unknown_field", details={"fields": unknown}
        )
    missing_columns = sorted(k for k, col in mapping.items() if col and col not in headers)
    if missing_columns:
        raise ValidationFailed(
            "عمود غير موجود في الملف", code="unknown_column", details={"fields": missing_columns}
        )
    required = [label for key, (label, req) in FIELDS.items() if req and not mapping.get(key)]
    if required:
        raise ValidationFailed(f"حدد أعمدة: {'، '.join(required)}", code="mapping_incomplete")


def parse_money(raw: str) -> Decimal | None:
    """Decimal-safe amount: Arabic digits, currency words and thousands commas allowed."""
    value = to_latin_digits(raw).replace("٫", ".").replace("٬", ",")
    value = re.sub(r"(ج\.?م\.?|جنيه|EGP|LE)", "", value, flags=re.IGNORECASE)
    value = value.replace(",", "").replace(" ", "").strip()
    if value in ("", "-"):
        return None
    negative = value.startswith("(") and value.endswith(")")
    value = value.strip("()")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"مبلغ غير صحيح: {raw}") from exc
    if not amount.is_finite() or amount.as_tuple().exponent < -2:  # type: ignore[operator]
        raise ValueError(f"مبلغ بأكثر من قرشين: {raw}")
    return -amount if negative else amount


DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")


def parse_date(raw: str) -> date:
    value = to_latin_digits(raw).strip().split(" ")[0].split("T")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"تاريخ غير مفهوم: {raw} (استخدم 2026-11-01 أو 01/11/2026)")


# --- Row checks ---------------------------------------------------------------------


def _vehicle(db: Session, raw: str, driver: Driver, start: date) -> Vehicle | None:
    if raw:
        by_code = db.scalar(select(Vehicle).where(Vehicle.internal_code == raw.strip().upper()))
        if by_code is None:
            by_code = db.scalar(select(Vehicle).where(Vehicle.internal_code == raw.strip()))
        return by_code or db.scalar(select(Vehicle).where(Vehicle.plate_key == plate_key(raw)))
    at = local_day_bounds_utc(start)[1]
    assignment = db.scalar(
        select(DriverVehicleAssignment)
        .where(
            DriverVehicleAssignment.driver_id == driver.id,
            DriverVehicleAssignment.starts_at < at,
            or_(
                DriverVehicleAssignment.ends_at.is_(None),
                DriverVehicleAssignment.ends_at > local_day_bounds_utc(start)[0],
            ),
        )
        .order_by(DriverVehicleAssignment.role, DriverVehicleAssignment.starts_at.desc())
    )
    return assignment.vehicle if assignment else None


def _amounts(cells: dict[str, str], mapping: dict[str, str], row: Row) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in MONEY_FIELDS:
        column = mapping.get(key)
        if not column:
            continue
        try:
            amount = parse_money(cells.get(column, ""))
        except ValueError as exc:
            row.messages.append(str(exc))
            continue
        if amount is not None:
            values[key] = amount
    trips = mapping.get("trips_count")
    if trips and cells.get(trips):
        try:
            values["trips_count"] = int(to_latin_digits(cells[trips]).replace(",", ""))
        except ValueError:
            row.messages.append(f"عدد رحلات غير صحيح: {cells[trips]}")
    return values


def _check_row(
    db: Session,
    platform: RideHailingPlatform,
    n: int,
    cells: dict[str, str],
    mapping: dict[str, str],
) -> Row:
    row = Row(row=n, status="OK")

    def cell(key: str) -> str:
        column = mapping.get(key)
        return cells.get(column, "") if column else ""

    driver = None
    try:
        driver = db.scalar(
            select(Driver).where(Driver.phone == normalize_phone(cell("driver_phone")))
        )
        if driver is None:
            row.messages.append("لا يوجد سائق بهذا الهاتف")
    except InvalidPhoneError:
        row.messages.append(f"هاتف غير صحيح: {cell('driver_phone') or '—'}")
    try:
        row.period_start = parse_date(cell("period_start"))
        row.period_end = parse_date(cell("period_end")) if cell("period_end") else row.period_start
    except ValueError as exc:
        row.messages.append(str(exc))
    values = _amounts(cells, mapping, row)
    row.statement_reference = cell("statement_reference") or None
    vehicle = None
    if driver is not None:
        row.driver = driver.full_name
        if row.period_start is not None:
            vehicle = _vehicle(db, cell("vehicle"), driver, row.period_start)
            if vehicle is None:
                row.messages.append(
                    "السيارة غير موجودة"
                    if cell("vehicle")
                    else "لا توجد سيارة مكلف بها السائق في الفترة"
                )
            else:
                row.vehicle = vehicle.internal_code
    row.gross_earnings = values.get("gross_earnings")
    row.platform_fees = values.get("platform_fees")
    if row.messages or driver is None or vehicle is None or row.period_start is None:
        row.status = "ERROR"
        return row
    assert row.period_end is not None  # noqa: S101
    try:
        row.data = StatementFields(
            platform_id=platform.id,
            driver_id=driver.id,
            vehicle_id=vehicle.id,
            period_start=row.period_start,
            period_end=row.period_end,
            statement_reference=row.statement_reference,
            gross_earnings=values.get("gross_earnings", Decimal(0)),
            platform_fees=values.get("platform_fees", Decimal(0)),
            **{k: v for k, v in values.items() if k not in ("gross_earnings", "platform_fees")},
        )
    except ValidationError as exc:
        row.status = "ERROR"
        row.messages += [str(e["msg"]).removeprefix("Value error, ") for e in exc.errors()]
        return row
    income = row.data.gross_earnings + row.data.tips + row.data.adjustments
    row.net_earnings = income - row.data.platform_fees
    if row.period_end > local_today():
        row.status = "ERROR"
        row.messages.append("الفترة في المستقبل")
    return row


def _duplicates(db: Session, platform: RideHailingPlatform, rows: list[Row]) -> None:
    seen_periods: dict[uuid.UUID, list[tuple[date, date]]] = {}
    seen_refs: set[str] = set()
    for row in rows:
        if row.status != "OK" or row.data is None:
            continue
        d = row.data
        earlier = seen_periods.setdefault(d.driver_id, [])
        overlaps = any(a <= d.period_end and b >= d.period_start for a, b in earlier)
        if overlaps or (d.statement_reference and d.statement_reference in seen_refs):
            row.status = "DUPLICATE"
            row.messages.append("مكرر أو متداخل مع صف آخر في الملف")
            continue
        earlier.append((d.period_start, d.period_end))
        if d.statement_reference:
            seen_refs.add(d.statement_reference)
            if db.scalar(
                select(RideHailingStatement.id).where(
                    RideHailingStatement.platform_id == platform.id,
                    RideHailingStatement.statement_reference == d.statement_reference,
                    RideHailingStatement.status.in_(LIVE),
                )
            ):
                row.status = "DUPLICATE"
                row.messages.append("رقم الكشف مسجل من قبل")
                continue
        if db.scalar(
            select(RideHailingStatement.id).where(
                RideHailingStatement.platform_id == platform.id,
                RideHailingStatement.driver_id == d.driver_id,
                RideHailingStatement.status.in_(LIVE),
                RideHailingStatement.period_start <= d.period_end,
                RideHailingStatement.period_end >= d.period_start,
            )
        ):
            row.status = "DUPLICATE"
            row.messages.append("يوجد كشف آخر للسائق يغطي هذه الفترة")


def _shift_warnings(db: Session, rows: list[Row]) -> None:
    for row in rows:
        if row.status != "OK" or row.data is None:
            continue
        days, _ = ride_hailing._activity(
            db, row.data.period_start, row.data.period_end, row.data.driver_id, None
        )
        if not days:
            row.warnings.append("لا توجد وردية نقل ذكي مسجلة للسائق في الفترة — مراجعة مطلوبة")


def _platform(db: Session, platform_id: uuid.UUID) -> RideHailingPlatform:
    platform = db.get(RideHailingPlatform, platform_id)
    if platform is None or not platform.is_active:
        raise field_error("platform_id", "المنصة غير موجودة أو غير مفعلة")
    return platform


def _sha(content: str) -> str:
    return hashlib.sha256(content.lstrip("﻿").encode()).hexdigest()


def preview(
    db: Session,
    *,
    platform_id: uuid.UUID,
    file_name: str,
    content: str,
    mapping: dict[str, str] | None,
) -> Preview:
    platform = _platform(db, platform_id)
    headers, cells = _read(content)
    used = (
        {k: v for k, v in mapping.items() if v}
        if mapping
        else guess_mapping(headers, platform.import_mapping)
    )
    _check_mapping(used, headers)
    rows = [_check_row(db, platform, i + 1, c, used) for i, c in enumerate(cells)]
    _duplicates(db, platform, rows)
    _shift_warnings(db, rows)
    sha = _sha(content)
    already = (
        db.scalar(
            select(RideHailingImportBatch.id).where(
                RideHailingImportBatch.platform_id == platform.id,
                RideHailingImportBatch.file_sha256 == sha,
                RideHailingImportBatch.status == ImportBatchStatus.IMPORTED,
            )
        )
        is not None
    )
    counts = {s: sum(1 for r in rows if r.status == s) for s in ("OK", "ERROR", "DUPLICATE")}
    counts["warnings"] = sum(1 for r in rows if r.warnings)
    return Preview(platform.id, file_name, sha, headers, used, rows, already, counts)


def commit(
    db: Session,
    *,
    actor: User,
    platform_id: uuid.UUID,
    file_name: str,
    content: str,
    mapping: dict[str, str] | None,
) -> RideHailingImportBatch:
    """Import the valid rows as SUBMITTED statements; the rest are listed as skipped."""
    result = preview(
        db, platform_id=platform_id, file_name=file_name, content=content, mapping=mapping
    )
    if result.already_imported:
        raise ConflictError(
            "هذا الملف مستورد من قبل لهذه المنصة؛ ألغِ الاستيراد السابق أولًا",
            code="file_already_imported",
        )
    good = [r for r in result.rows if r.status == "OK" and r.data is not None]
    if not good:
        raise ValidationFailed("لا توجد صفوف صالحة للاستيراد", code="nothing_to_import")
    platform = _platform(db, platform_id)
    batch = RideHailingImportBatch(
        platform_id=platform.id,
        file_name=file_name[:200],
        file_sha256=result.file_sha256,
        mapping=result.mapping,
        rows_total=len(result.rows),
        rows_imported=len(good),
        skipped=[
            {"row": r.row, "status": r.status, "messages": r.messages}
            for r in result.rows
            if r.status != "OK"
        ],
        created_by_id=actor.id,
    )
    db.add(batch)
    db.flush()
    for r in good:
        assert r.data is not None  # noqa: S101
        statement = ride_hailing._new(db, actor=actor, data=r.data)
        statement.import_batch_id = batch.id
        statement.import_row = r.row
        if r.warnings:
            statement.notes = "؛ ".join(r.warnings)
        audit.record(
            db,
            action=f"{ride_hailing.ENTITY}.created",
            actor=actor,
            entity_type=ride_hailing.ENTITY,
            entity_id=statement.id,
            changes=audit.diff({}, audit.snapshot(statement, ride_hailing.AUDITED)),
            details={"import_batch_id": batch.id, "row": r.row},
        )
    platform.import_mapping = result.mapping
    audit.record(
        db,
        action=f"{ENTITY}.created",
        actor=actor,
        entity_type=ENTITY,
        entity_id=batch.id,
        details={
            "platform": platform.name,
            "file_name": batch.file_name,
            "rows_total": batch.rows_total,
            "rows_imported": batch.rows_imported,
        },
    )
    db.commit()
    return batch


def get(db: Session, batch_id: uuid.UUID) -> RideHailingImportBatch:
    batch = db.get(RideHailingImportBatch, batch_id)
    if batch is None:
        raise NotFoundError("الاستيراد غير موجود")
    return batch


def statements(db: Session, batch_id: uuid.UUID) -> list[RideHailingStatement]:
    return list(
        db.scalars(
            select(RideHailingStatement)
            .where(RideHailingStatement.import_batch_id == batch_id)
            .order_by(RideHailingStatement.import_row)
        ).all()
    )


def list_batches(db: Session, limit: int = 50) -> list[RideHailingImportBatch]:
    return list(
        db.scalars(
            select(RideHailingImportBatch)
            .order_by(RideHailingImportBatch.created_at.desc())
            .limit(limit)
        ).all()
    )


def void(db: Session, *, actor: User, batch_id: uuid.UUID, reason: str) -> RideHailingImportBatch:
    """Roll back a whole file: void every statement it created that is still live."""
    batch = db.scalar(
        select(RideHailingImportBatch)
        .where(RideHailingImportBatch.id == batch_id)
        .with_for_update(of=RideHailingImportBatch)
    )
    if batch is None:
        raise NotFoundError("الاستيراد غير موجود")
    if batch.status is ImportBatchStatus.VOIDED:
        raise ConflictError("الاستيراد ملغي بالفعل", code="already_voided")
    voided = 0
    for s in statements(db, batch.id):
        if s.status is RecordStatus.VOIDED:
            continue
        ride_hailing._void(db, s, actor, f"إلغاء استيراد: {reason}")
        voided += 1
    batch.status = ImportBatchStatus.VOIDED
    batch.voided_by_id = actor.id
    batch.voided_at = utcnow()
    batch.void_reason = reason
    audit.record(
        db,
        action=f"{ENTITY}.voided",
        actor=actor,
        entity_type=ENTITY,
        entity_id=batch.id,
        reason=reason,
        details={"statements_voided": voided},
    )
    db.commit()
    return batch


__all__ = ["FIELDS", "Preview", "Row", "commit", "guess_mapping", "list_batches", "preview", "void"]
