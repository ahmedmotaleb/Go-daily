"""Versioned company policies (U47).

The review thresholds used by the exception engine, the refuelling checks
and the report notes can be changed by staff with `settings:manage`, without
a deployment. Each change creates a new immutable version (who, when, why,
what changed) and is audited. Values not set in a version fall back to the
environment defaults (`app/core/config.py`).

Thresholds are review hints, not verdicts: changing them changes which
situations are shown for review («مراجعة مطلوبة»), never anyone's records.
Each review case keeps the thresholds it was judged with, so older cases
remain explainable after a change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ValidationFailed, field_error
from app.models.policy import PolicyVersion
from app.models.user import User
from app.services import audit


@dataclass(frozen=True)
class PolicyKey:
    key: str
    group: str
    title: str
    unit: str
    minimum: float
    maximum: float
    integer: bool = True


GPS = "التتبع"
ROUTE = "المسارات"
ODOMETER = "العداد"
FUEL = "الوقود"
REVENUE = "الإيرادات والنقدية"
SEVERITY = "الأهمية والتصعيد"

CATALOG: tuple[PolicyKey, ...] = (
    PolicyKey("exception_gps_disabled_minutes", GPS, "إيقاف الموقع أثناء الوردية", "دقيقة", 1, 240),
    PolicyKey("exception_gps_gap_minutes", GPS, "انقطاع بيانات الموقع", "دقيقة", 1, 240),
    PolicyKey("exception_tracking_interrupted_minutes", GPS, "توقف التتبع", "دقيقة", 1, 240),
    PolicyKey("exception_late_upload_hours", GPS, "تأخر رفع النقاط", "ساعة", 1, 168),
    PolicyKey("exception_clock_skew_minutes", GPS, "اختلاف ساعة الهاتف", "دقيقة", 1, 240),
    PolicyKey("exception_long_stop_minutes", GPS, "توقف طويل", "دقيقة", 5, 600),
    PolicyKey("exception_outside_area_minutes", GPS, "خارج نطاق التشغيل", "دقيقة", 1, 240),
    PolicyKey("exception_moved_between_shifts_km", GPS, "حركة بين الورديات", "كم", 1, 500),
    PolicyKey("exception_route_corridor_m", ROUTE, "عرض ممر المسار", "متر", 100, 20000, False),
    PolicyKey("exception_route_min_minutes", ROUTE, "الخروج عن المسار", "دقيقة", 1, 240),
    PolicyKey("exception_incomplete_legs", ROUTE, "اتجاهات غير مكتملة في التشغيل", "اتجاه", 1, 50),
    PolicyKey(
        "exception_odometer_tolerance_pct", ODOMETER, "فرق العداد وGPS (نسبة)", "%", 1, 200, False
    ),
    PolicyKey(
        "exception_odometer_tolerance_km", ODOMETER, "فرق العداد وGPS (مسافة)", "كم", 1, 500, False
    ),
    PolicyKey(
        "exception_max_avg_speed_kmh", ODOMETER, "أقصى متوسط سرعة مفترض", "كم/س", 20, 300, False
    ),
    PolicyKey("exception_fuel_ratio", FUEL, "استهلاك أعلى من المعتاد (مضاعف)", "×", 1.1, 10, False),
    PolicyKey(
        "fuel_quantity_ratio", FUEL, "كمية تموين أعلى من المعتاد (مضاعف)", "×", 1.1, 10, False
    ),
    PolicyKey("fuel_repeat_hours", FUEL, "تموين متكرر خلال", "ساعة", 1, 72),
    PolicyKey(
        "exception_fuel_distance_m", FUEL, "بعد مكان التموين عن السيارة", "متر", 100, 50000, False
    ),
    PolicyKey(
        "exception_fuel_outside_shift_minutes", FUEL, "تموين خارج الوردية بأكثر من", "دقيقة", 0, 720
    ),
    PolicyKey("exception_duplicate_window_minutes", FUEL, "نافذة السجل المكرر", "دقيقة", 1, 1440),
    PolicyKey(
        "exception_revenue_ratio", REVENUE, "دخل بعيد عن المعتاد (مضاعف)", "×", 1.1, 10, False
    ),
    PolicyKey("cash_handover_days", REVENUE, "مهلة تسليم نقدية التقفيل", "يوم", 1, 30),
    PolicyKey("severity_info_amount", SEVERITY, "أقل من هذا المبلغ: للعلم", "ج.م", 0, 1000, False),
    PolicyKey("severity_medium_amount", SEVERITY, "أهمية متوسطة من مبلغ", "ج.م", 1, 100000, False),
    PolicyKey("severity_high_amount", SEVERITY, "أهمية عالية من مبلغ", "ج.م", 1, 1000000, False),
    PolicyKey(
        "severity_long_minutes", SEVERITY, "أهمية متوسطة إذا استمرت الحالة", "دقيقة", 10, 1440
    ),
    PolicyKey(
        "escalation_hours", SEVERITY, "تنبيه للحالات العالية غير المراجعة بعد", "ساعة", 1, 168
    ),
)
BY_KEY = {k.key: k for k in CATALOG}


def current(db: Session) -> PolicyVersion | None:
    return db.scalar(select(PolicyVersion).order_by(PolicyVersion.version.desc()).limit(1))


def effective_settings(db: Session) -> Settings:
    """Environment settings with the current policy's values applied."""
    base = get_settings()
    latest = current(db)
    if latest is None or not latest.values:
        return base
    known = {k: v for k, v in latest.values.items() if k in BY_KEY}
    return base.model_copy(update=known)


def _value(key: PolicyKey, raw: Any) -> float | int:
    try:
        number = float(raw)
    except (TypeError, ValueError) as exc:
        raise field_error(key.key, "أدخل رقمًا") from exc
    if key.integer and number != int(number):
        raise field_error(key.key, "أدخل رقمًا صحيحًا")
    if not key.minimum <= number <= key.maximum:
        raise field_error(key.key, f"القيمة بين {key.minimum:g} و{key.maximum:g}")
    return int(number) if key.integer else number


def update(db: Session, *, actor: User, changes: dict[str, Any], reason: str) -> PolicyVersion:
    """New version = the current values with `changes` applied (null = back to default)."""
    unknown = sorted(set(changes) - set(BY_KEY))
    if unknown:
        raise ValidationFailed(
            "إعداد غير معروف", code="unknown_policy_key", details={"keys": unknown}
        )
    if not reason.strip():
        raise field_error("reason", "اكتب سبب التغيير")
    latest = current(db)
    values: dict[str, Any] = dict(latest.values) if latest else {}
    diff: dict[str, list[Any]] = {}
    defaults = get_settings()
    for key, raw in changes.items():
        before = values.get(key, getattr(defaults, key))
        if raw is None:
            values.pop(key, None)
            after = getattr(defaults, key)
        else:
            after = _value(BY_KEY[key], raw)
            values[key] = after
        if before != after:
            diff[key] = [before, after]
    if not diff:
        raise ValidationFailed("لا يوجد تغيير عن السياسة الحالية", code="no_policy_change")
    number = (db.scalar(select(func.max(PolicyVersion.version))) or 0) + 1
    version = PolicyVersion(
        version=number, values=values, reason=reason.strip(), created_by_id=actor.id
    )
    db.add(version)
    db.flush()
    audit.record(
        db,
        action="policy.updated",
        actor=actor,
        entity_type="policy_version",
        entity_id=version.id,
        changes=diff,
        details={"version": number},
        reason=reason.strip(),
    )
    db.commit()
    return version


def history(db: Session, limit: int = 50) -> list[PolicyVersion]:
    return list(
        db.scalars(select(PolicyVersion).order_by(PolicyVersion.version.desc()).limit(limit)).all()
    )


__all__ = ["BY_KEY", "CATALOG", "PolicyKey", "current", "effective_settings", "history", "update"]
