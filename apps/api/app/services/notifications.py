"""Notification generation, inbox queries and read state (Task 22).

Generators look at the current state and return drafts. Each draft goes to
every active staff user holding its permission. Spam control:
- (user, dedupe_key) is unique, so a condition notifies a user once;
- keys change only when the situation changes (e.g. "expiring" becomes
  "expired", tracking stops again after recovering);
- low-importance exception cases are not notified at all (they are on the
  exceptions page), and pending reviews come as one daily summary.
A notification whose condition is gone is marked cleared, never deleted.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Select, func, select, true, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core import monitoring
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.permissions import ROLE_PERMISSIONS, Permission, UserRole
from app.core.time import local_today, utcnow
from app.models.driver import Driver, EmploymentStatus
from app.models.exceptions import ExceptionSeverity, OperationalException
from app.models.finance import Expense, FuelTransaction, RecordStatus, RideHailingStatement
from app.models.fleet import Vehicle
from app.models.maintenance import MaintenanceRecord
from app.models.notifications import Notification, NotificationSeverity
from app.models.shift import Shift, ShiftStatus
from app.models.user import User
from app.schemas.common import PageParams
from app.services import maintenance as maintenance_service
from app.services import tracking
from app.services.common import paginate
from app.services.exception_rules import RULE_INFO
from app.services.exceptions import ACTIVE as ACTIVE_EXCEPTIONS
from app.services.expiry import ExpiryStatus, expiry_status, warning_cutoff
from app.services.notification_channels import configured

logger = logging.getLogger(__name__)

N = NotificationSeverity
_SEVERITY_RANK = {N.INFO: 0, N.WARNING: 1, N.CRITICAL: 2}


@dataclass
class Draft:
    permission: Permission
    severity: NotificationSeverity
    title: str
    dedupe_key: str
    body: str | None = None
    link: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None


def _date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


# --- Generators ---------------------------------------------------------------


def vehicle_documents(db: Session) -> list[Draft]:
    cutoff = warning_cutoff()
    drafts: list[Draft] = []
    vehicles = db.scalars(
        select(Vehicle).where(
            Vehicle.is_active.is_(True),
            (Vehicle.license_expiry <= cutoff) | (Vehicle.insurance_expiry <= cutoff),
        )
    ).all()
    for v in vehicles:
        for field, name, expires in (
            ("license", "رخصة", v.license_expiry),
            ("insurance", "تأمين", v.insurance_expiry),
        ):
            state = expiry_status(expires)
            if expires is None or state not in (ExpiryStatus.EXPIRED, ExpiryStatus.EXPIRING_SOON):
                continue
            expired = state is ExpiryStatus.EXPIRED
            drafts.append(
                Draft(
                    permission=Permission.VEHICLES_READ,
                    severity=N.CRITICAL if expired else N.WARNING,
                    title=(
                        f"انتهت {name} المركبة {v.internal_code} في {_date(expires)}"
                        if expired
                        else f"{name} المركبة {v.internal_code} تنتهي في {_date(expires)}"
                    ),
                    dedupe_key=f"VEHICLE_{field.upper()}:{v.id}:{expires.isoformat()}:{state.value}",
                    link=f"/vehicles/{v.id}",
                    entity_type="vehicle",
                    entity_id=v.id,
                )
            )
    return drafts


def driver_licenses(db: Session) -> list[Draft]:
    drafts: list[Draft] = []
    drivers = db.scalars(
        select(Driver).where(
            Driver.employment_status == EmploymentStatus.ACTIVE,
            Driver.license_expiry <= warning_cutoff(),
        )
    ).all()
    for d in drivers:
        if d.license_expiry is None:
            continue
        state = expiry_status(d.license_expiry)
        expired = state is ExpiryStatus.EXPIRED
        drafts.append(
            Draft(
                permission=Permission.DRIVERS_READ,
                severity=N.CRITICAL if expired else N.WARNING,
                title=(
                    f"انتهت رخصة قيادة {d.full_name} في {_date(d.license_expiry)}"
                    if expired
                    else f"رخصة قيادة {d.full_name} تنتهي في {_date(d.license_expiry)}"
                ),
                dedupe_key=f"DRIVER_LICENSE:{d.id}:{d.license_expiry.isoformat()}:{state.value}",
                link=f"/drivers/{d.id}",
                entity_type="driver",
                entity_id=d.id,
            )
        )
    return drafts


def maintenance_due(db: Session) -> list[Draft]:
    drafts: list[Draft] = []
    for row in maintenance_service.due_status(db):
        if row.state not in ("OVERDUE", "DUE_SOON"):
            continue
        s = row.schedule
        overdue = row.state == "OVERDUE"
        left = []
        if row.km_left is not None:
            left.append(
                f"متجاوزة {-row.km_left} كم" if row.km_left < 0 else f"متبقي {row.km_left} كم"
            )
        if row.days_left is not None:
            left.append(
                f"متأخرة {-row.days_left} يوم"
                if row.days_left < 0
                else f"متبقي {row.days_left} يوم"
            )
        drafts.append(
            Draft(
                permission=Permission.MAINTENANCE_READ,
                severity=N.WARNING if overdue else N.INFO,
                title=(
                    f"{'صيانة متأخرة' if overdue else 'صيانة قريبة'}: {s.type.name_ar} — "
                    f"{s.vehicle.internal_code}"
                ),
                body=" · ".join(left) or None,
                dedupe_key=(
                    f"MAINTENANCE:{s.id}:{row.state}:{row.next_due_km}:{row.next_due_date}"
                ),
                link=f"/vehicles/{s.vehicle_id}",
                entity_type="vehicle",
                entity_id=s.vehicle_id,
            )
        )
    return drafts


def tracking_interrupted(db: Session) -> list[Draft]:
    settings = get_settings()
    now = utcnow()
    grace = timedelta(seconds=settings.tracking_stale_seconds)
    started = {
        s.id: s.started_at
        for s in db.scalars(select(Shift).where(Shift.status == ShiftStatus.ACTIVE)).all()
    }
    drafts: list[Draft] = []
    for pos in tracking.live_positions(db):
        if pos.state != "OFFLINE":
            continue
        began = started.get(pos.shift_id)
        # A shift that has just started has had no time to send points yet.
        if began is None or now - began < grace:
            continue
        since = pos.last_received_at
        last = (
            f"آخر بيانات وصلت {since.astimezone(settings.tz).strftime('%H:%M %d/%m')}"
            if since
            else "لم تصل أي بيانات منذ بدء الوردية"
        )
        drafts.append(
            Draft(
                permission=Permission.TRACKING_READ,
                severity=N.WARNING,
                title=f"توقف وصول بيانات الموقع من {pos.vehicle_code}",
                body=f"{last} · السائق {pos.driver_name} في وردية نشطة",
                # A new interruption after recovery has a different key.
                dedupe_key=f"TRACKING:{pos.shift_id}:{since.isoformat() if since else 'none'}",
                link=f"/shifts/{pos.shift_id}",
                entity_type="shift",
                entity_id=pos.shift_id,
            )
        )
    return drafts


_EXCEPTION_SEVERITY = {ExceptionSeverity.HIGH: N.CRITICAL, ExceptionSeverity.MEDIUM: N.WARNING}
_LABEL_AR = {"REVIEW_REQUIRED": "مراجعة مطلوبة", "UNUSUAL": "حالة غير معتادة"}


def open_exceptions(db: Session) -> list[Draft]:
    cases = db.scalars(
        select(OperationalException).where(
            OperationalException.status.in_(ACTIVE_EXCEPTIONS),
            OperationalException.severity.in_(tuple(_EXCEPTION_SEVERITY)),
            OperationalException.detected_at >= utcnow() - timedelta(days=14),
        )
    ).all()
    drafts: list[Draft] = []
    for c in cases:
        info = RULE_INFO.get(c.rule_code)
        drafts.append(
            Draft(
                permission=Permission.EXCEPTIONS_READ,
                severity=_EXCEPTION_SEVERITY[c.severity],
                title=f"{_LABEL_AR[c.label.value]}: {info.title_ar if info else c.rule_code}",
                body=c.summary,
                dedupe_key=f"EXCEPTION:{c.id}",
                link=f"/exceptions/{c.id}",
                entity_type="operational_exception",
                entity_id=c.id,
            )
        )
    return drafts


def pending_reviews(db: Session) -> list[Draft]:
    cutoff = utcnow() - timedelta(hours=get_settings().notification_pending_review_hours)
    counts: list[tuple[str, str, int]] = []
    for label, path, model in (
        ("وقود", "/finance/fuel", FuelTransaction),
        ("مصروفات", "/finance/expenses", Expense),
        ("صيانة", "/maintenance", MaintenanceRecord),
        ("كشوف منصات", "/finance/ride-hailing", RideHailingStatement),
    ):
        n = db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.status == RecordStatus.SUBMITTED, model.created_at < cutoff)
        )
        if n:
            counts.append((label, path, int(n)))
    if not counts:
        return []
    total = sum(n for _, _, n in counts)
    return [
        Draft(
            permission=Permission.EXPENSES_APPROVE,
            severity=N.INFO,
            title=f"{total} سجل مالي بانتظار المراجعة",
            body=" · ".join(f"{label}: {n}" for label, _, n in counts),
            # One summary per day at most.
            dedupe_key=f"PENDING_REVIEW:{local_today().isoformat()}",
            link=f"{counts[0][1]}?status=SUBMITTED",
        )
    ]


Generator = Callable[[Session], list[Draft]]

GENERATORS: list[tuple[str, Generator]] = [
    ("VEHICLE_DOCUMENT", vehicle_documents),
    ("DRIVER_LICENSE", driver_licenses),
    ("MAINTENANCE_DUE", maintenance_due),
    ("TRACKING_INTERRUPTED", tracking_interrupted),
    ("EXCEPTION", open_exceptions),
    ("PENDING_REVIEW", pending_reviews),
]


def recipients(db: Session, permission: Permission) -> list[User]:
    roles = [
        role
        for role, perms in ROLE_PERMISSIONS.items()
        if permission in perms and role is not UserRole.DRIVER
    ]
    return list(
        db.scalars(select(User).where(User.is_active.is_(True), User.role.in_(roles))).all()
    )


def generate(db: Session) -> dict[str, Any]:
    """Run every generator; returns per-kind counts and errors."""
    settings = get_settings()
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    created: list[uuid.UUID] = []
    audience: dict[Permission, list[User]] = {}
    now = utcnow()
    for kind, generator in GENERATORS:
        try:
            with db.begin_nested():
                drafts = generator(db)
                keys: set[str] = set()
                new = 0
                for d in drafts:
                    keys.add(d.dedupe_key)
                    users = audience.setdefault(d.permission, recipients(db, d.permission))
                    for user in users:
                        row_id = db.execute(
                            pg_insert(Notification)
                            .values(
                                user_id=user.id,
                                kind=kind,
                                severity=d.severity,
                                title=d.title[:200],
                                body=d.body,
                                link=d.link,
                                entity_type=d.entity_type,
                                entity_id=d.entity_id,
                                dedupe_key=d.dedupe_key,
                                created_at=now,
                            )
                            .on_conflict_do_nothing(constraint="uq_notifications_user_dedupe")
                            .returning(Notification.id)
                        ).scalar()
                        if row_id is not None:
                            new += 1
                            created.append(row_id)
                cleared = db.execute(
                    update(Notification)
                    .where(
                        Notification.kind == kind,
                        Notification.cleared_at.is_(None),
                        Notification.dedupe_key.not_in(keys) if keys else true(),
                    )
                    .values(cleared_at=now)
                ).rowcount  # type: ignore[attr-defined]
                # A condition that came back (e.g. same expiry, renewed then
                # unrenewed) is active again.
                if keys:
                    db.execute(
                        update(Notification)
                        .where(
                            Notification.kind == kind,
                            Notification.dedupe_key.in_(keys),
                            Notification.cleared_at.is_not(None),
                        )
                        .values(cleared_at=None)
                    )
            results[kind] = {"conditions": len(drafts), "new": new, "cleared": int(cleared or 0)}
        except Exception as exc:
            logger.exception("notification_generator_failed", extra={"kind": kind})
            monitoring.capture_exception(exc, component="notification_generator", name=kind)
            errors[kind] = type(exc).__name__
    db.commit()
    _deliver(
        db, created, settings.notification_channels, settings.notification_channel_min_severity
    )
    return {"results": results, "errors": errors}


def _deliver(db: Session, ids: list[uuid.UUID], channel_names: str, min_severity: str) -> None:
    channels = configured(channel_names)
    if not channels or not ids:
        return
    floor = _SEVERITY_RANK[NotificationSeverity(min_severity)]
    rows = db.execute(
        select(Notification, User)
        .join(User, User.id == Notification.user_id)
        .where(Notification.id.in_(ids))
    ).all()
    for notification, user in rows:
        if _SEVERITY_RANK[notification.severity] < floor:
            continue
        for channel in channels:
            try:
                channel.deliver(notification, user)
            except Exception:
                logger.exception(
                    "notification_delivery_failed",
                    extra={"channel": channel.name, "notification_id": str(notification.id)},
                )


# --- Inbox --------------------------------------------------------------------


def _inbox(user: User, *, unread_only: bool, include_cleared: bool) -> Select[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    if not include_cleared:
        stmt = stmt.where(Notification.cleared_at.is_(None))
    return stmt


def list_for(
    db: Session, user: User, params: PageParams, *, unread_only: bool, include_cleared: bool
) -> tuple[list[Notification], int]:
    stmt = _inbox(user, unread_only=unread_only, include_cleared=include_cleared).order_by(
        Notification.created_at.desc(), Notification.id
    )
    return paginate(db, stmt, params)


def unread_counts(db: Session, user: User) -> dict[str, int]:
    rows = db.execute(
        select(Notification.severity, func.count())
        .where(
            Notification.user_id == user.id,
            Notification.read_at.is_(None),
            Notification.cleared_at.is_(None),
        )
        .group_by(Notification.severity)
    ).all()
    by = {severity.value: int(n) for severity, n in rows}
    return {"unread": sum(by.values()), "critical": by.get("CRITICAL", 0)}


def mark_read(db: Session, user: User, notification_id: uuid.UUID) -> Notification:
    n = db.get(Notification, notification_id)
    # Another user's notification is reported as missing, not forbidden.
    if n is None or n.user_id != user.id:
        raise NotFoundError("التنبيه غير موجود")
    if n.read_at is None:
        n.read_at = utcnow()
        db.commit()
    return n


def mark_all_read(db: Session, user: User) -> int:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
