"""Security event dashboard (U36).

Built only from the audit log and settings. Shows failed-login spikes,
lockouts, two-factor and re-authentication failures, resets, permission
denials, accounts and addresses with the most failures, recent events, and
configuration warnings. Never shows passwords, tokens, two-factor secrets
or codes, or national IDs (none of them are in the audit log); unknown
phone numbers appear only masked, as the audit log stores them.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import UserRole
from app.core.time import utcnow
from app.models.audit import AuditLog
from app.models.user import User
from app.services import two_factor

LABELS = {
    "auth.login.failed": "دخول بكلمة مرور خاطئة",
    "auth.login.locked": "محاولة على حساب موقوف مؤقتًا",
    "auth.login.2fa_failed": "رمز تحقق خاطئ عند الدخول",
    "auth.login.inactive": "دخول بحساب غير مفعل",
    "auth.login.client_not_allowed": "دخول من تطبيق غير مسموح للحساب",
    "auth.reauth.failed": "فشل تأكيد الهوية",
    "auth.2fa.reset": "إعادة ضبط التحقق بخطوتين",
    "auth.2fa.disabled": "إيقاف التحقق بخطوتين",
    "auth.permission_denied": "محاولة إجراء بدون صلاحية",
    "auth.password_changed": "تغيير كلمة المرور",
    "user.password_reset": "تعيين كلمة مرور من الإدارة",
    "policy.updated": "تغيير سياسة المراجعة",
}
FAILURES = ("auth.login.failed", "auth.login.2fa_failed")
SPIKE_PER_HOUR = 20


@dataclass
class Counted:
    label: str
    count: int


@dataclass
class Event:
    at: datetime
    action: str
    label: str
    user: str | None
    ip: str | None


@dataclass
class Warning:
    code: str
    message: str


@dataclass
class Summary:
    hours: int
    counts: dict[str, int]
    hourly_failures: list[tuple[datetime, int]]
    spike: bool
    top_accounts: list[Counted]
    top_addresses: list[Counted]
    unknown_number_attempts: int
    recent: list[Event] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)


def _names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(ids))).all()}


def _warnings(db: Session) -> list[Warning]:
    s = get_settings()
    out: list[Warning] = []
    if s.app_env != "production":
        out.append(Warning("ENVIRONMENT", f"الخادم يعمل في بيئة {s.app_env} وليس production."))
    required = [r for r in UserRole if two_factor.required_for(r)]
    without = [
        u.full_name
        for u in db.scalars(
            select(User).where(User.role.in_(required), User.is_active.is_(True))
        ).all()
        if not u.twofa_enabled
    ]
    if without:
        out.append(
            Warning(
                "TWOFA_MISSING",
                f"{len(without)} حساب بصلاحية عالية بدون تحقق بخطوتين: {'، '.join(without[:5])}",
            )
        )
    if not s.twofa_enforce:
        out.append(
            Warning("TWOFA_NOT_ENFORCED", "التحقق بخطوتين غير إلزامي (TWOFA_ENFORCE=false).")
        )
    if s.redis_url is None:
        out.append(
            Warning("RATE_LIMIT_LOCAL", "حدود المحاولات لكل عملية على حدة (REDIS_URL غير مضبوط).")
        )
    if s.metrics_token is None:
        out.append(Warning("METRICS_OFF", "المراقبة غير مفعلة (METRICS_TOKEN غير مضبوط)."))
    if s.bootstrap_admin_password is not None:
        out.append(Warning("BOOTSTRAP_PASSWORD", "BOOTSTRAP_ADMIN_PASSWORD ما زال مضبوطًا؛ احذفه."))
    return out


def summary(db: Session, hours: int = 24) -> Summary:
    now = utcnow()
    since = now - timedelta(hours=hours)
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.occurred_at >= since, AuditLog.action.in_(list(LABELS)))
        .order_by(AuditLog.occurred_at.desc())
    ).all()

    counts = Counter(r.action for r in rows)
    failures = [r for r in rows if r.action in FAILURES]
    unknown = sum(1 for r in failures if (r.details or {}).get("unknown_account"))
    locked_now = sum(1 for r in failures if (r.details or {}).get("locked")) + counts.get(
        "auth.login.locked", 0
    )

    buckets: Counter[datetime] = Counter(
        r.occurred_at.replace(minute=0, second=0, microsecond=0) for r in failures
    )
    start = since.replace(minute=0, second=0, microsecond=0)
    hourly = [
        (start + timedelta(hours=i), buckets.get(start + timedelta(hours=i), 0))
        for i in range(hours + 1)
    ]

    by_user = Counter(
        uuid.UUID(r.entity_id) for r in failures if r.entity_type == "user" and r.entity_id
    )
    names = _names(db, set(by_user) | {r.actor_user_id for r in rows if r.actor_user_id})
    by_ip = Counter(r.ip_address for r in failures if r.ip_address)

    recent = []
    for r in rows[:30]:
        who = r.actor_user_id or (
            uuid.UUID(r.entity_id) if r.entity_type == "user" and r.entity_id else None
        )
        recent.append(
            Event(
                r.occurred_at,
                r.action,
                LABELS[r.action],
                names.get(who) if who else None,
                r.ip_address,
            )
        )
    return Summary(
        hours=hours,
        counts={
            "failed_logins": len(failures),
            "lockouts": locked_now,
            "twofa_failures": counts.get("auth.login.2fa_failed", 0),
            "reauth_failures": counts.get("auth.reauth.failed", 0),
            "twofa_resets": counts.get("auth.2fa.reset", 0) + counts.get("auth.2fa.disabled", 0),
            "permission_denied": counts.get("auth.permission_denied", 0),
            "password_resets": counts.get("user.password_reset", 0),
        },
        hourly_failures=hourly,
        spike=any(n >= SPIKE_PER_HOUR for _, n in hourly),
        top_accounts=[
            Counted(names.get(uid, "حساب محذوف"), n) for uid, n in by_user.most_common(5)
        ],
        top_addresses=[Counted(ip, n) for ip, n in by_ip.most_common(5)],
        unknown_number_attempts=unknown,
        recent=recent,
        warnings=_warnings(db),
    )


__all__ = ["LABELS", "Summary", "summary"]
