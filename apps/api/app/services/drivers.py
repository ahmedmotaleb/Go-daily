"""Driver use cases: profiles, sensitive identity data, app accounts,
employment status and compensation plans."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.permissions import UserRole
from app.core.security import hash_password
from app.core.text import to_latin_digits
from app.core.time import local_today, utcnow
from app.models.driver import (
    CompensationMethod,
    Driver,
    DriverCompensationPlan,
    EmploymentStatus,
)
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.driver import CompensationPlanCreate, DriverCreate, DriverUpdate
from app.schemas.user import UserCreate
from app.services import audit
from app.services import auth as auth_service
from app.services import users as users_service
from app.services.assignments import end_open_assignments_for_driver
from app.services.common import apply_changes, like_pattern, paginate
from app.services.expiry import warning_cutoff

NID_PURPOSE = "national_id"
DRIVER_AUDITED = (
    "full_name",
    "phone",
    "national_id",  # redacted by the audit helper; only "changed" is recorded
    "license_number",
    "license_expiry",
    "employment_status",
    "hire_date",
    "end_date",
    "notes",
)
INACTIVE_STATUSES = {EmploymentStatus.SUSPENDED, EmploymentStatus.TERMINATED}

LicenseFilter = Literal["expired", "expiring", "attention"]


def masked_national_id(driver: Driver) -> str | None:
    return f"**********{driver.national_id_last4}" if driver.national_id_last4 else None


def _snapshot(driver: Driver) -> dict[str, Any]:
    snap = audit.snapshot(driver, [f for f in DRIVER_AUDITED if f != "national_id"])
    # Compare by blind index so the audit diff shows "changed" without the value.
    snap["national_id"] = driver.national_id_hash
    return snap


def get_driver(db: Session, driver_id: uuid.UUID, *, for_update: bool = False) -> Driver:
    stmt = select(Driver).where(Driver.id == driver_id)
    if for_update:
        stmt = stmt.with_for_update(of=Driver).execution_options(populate_existing=True)
    driver = db.scalar(stmt)
    if driver is None:
        raise NotFoundError("السائق غير موجود")
    return driver


def get_driver_by_user(db: Session, user_id: uuid.UUID) -> Driver | None:
    return db.scalar(select(Driver).where(Driver.user_id == user_id))


def list_drivers(
    db: Session,
    params: PageParams,
    *,
    q: str | None = None,
    employment_status: EmploymentStatus | None = None,
    license: LicenseFilter | None = None,
    has_account: bool | None = None,
) -> tuple[list[Driver], int]:
    stmt = select(Driver)
    if q and q.strip():
        pattern = like_pattern(to_latin_digits(q))
        stmt = stmt.where(
            or_(
                Driver.full_name.ilike(pattern),
                Driver.phone.ilike(pattern),
                Driver.license_number.ilike(pattern),
            )
        )
    if employment_status:
        stmt = stmt.where(Driver.employment_status == employment_status)
    if license:
        today = local_today()
        cutoff = warning_cutoff(today)
        if license == "expired":
            stmt = stmt.where(Driver.license_expiry < today)
        elif license == "expiring":
            stmt = stmt.where(Driver.license_expiry.between(today, cutoff))
        else:
            stmt = stmt.where(Driver.license_expiry <= cutoff)
    if has_account is not None:
        stmt = stmt.where(Driver.user_id.is_not(None) if has_account else Driver.user_id.is_(None))
    return paginate(db, stmt.order_by(Driver.full_name, Driver.id), params)


def _set_national_id(driver: Driver, national_id: str | None) -> None:
    if national_id is None:
        driver.national_id_encrypted = None
        driver.national_id_hash = None
        driver.national_id_last4 = None
        return
    driver.national_id_encrypted = crypto.encrypt(national_id)
    driver.national_id_hash = crypto.blind_index(national_id, purpose=NID_PURPOSE)
    driver.national_id_last4 = national_id[-4:]


def _ensure_unique(
    db: Session,
    *,
    phone: str | None,
    national_id: str | None,
    exclude: uuid.UUID | None = None,
) -> None:
    if phone:
        stmt = select(Driver.id).where(Driver.phone == phone)
        if exclude:
            stmt = stmt.where(Driver.id != exclude)
        if db.scalar(stmt):
            raise ConflictError("رقم الهاتف مسجل لسائق آخر", code="driver_phone_taken")
    if national_id:
        h = crypto.blind_index(national_id, purpose=NID_PURPOSE)
        stmt = select(Driver.id).where(Driver.national_id_hash == h)
        if exclude:
            stmt = stmt.where(Driver.id != exclude)
        if db.scalar(stmt):
            raise ConflictError("الرقم القومي مسجل لسائق آخر", code="driver_national_id_taken")


def create_driver(db: Session, *, actor: User, data: DriverCreate) -> Driver:
    _ensure_unique(db, phone=data.phone, national_id=data.national_id)
    fields = data.model_dump(exclude={"national_id"})
    driver = Driver(**fields)
    _set_national_id(driver, data.national_id)
    db.add(driver)
    db.flush()
    audit.record(
        db,
        action="driver.created",
        actor=actor,
        entity_type="driver",
        entity_id=driver.id,
        changes=audit.diff({}, _snapshot(driver)),
    )
    db.commit()
    return driver


def update_driver(db: Session, *, actor: User, driver_id: uuid.UUID, data: DriverUpdate) -> Driver:
    driver = get_driver(db, driver_id, for_update=True)
    fields: dict[str, Any] = data.model_dump(exclude_unset=True)
    for key in ("full_name", "phone", "employment_status"):
        if key in fields and fields[key] is None:
            fields.pop(key)
    _ensure_unique(
        db,
        phone=fields.get("phone") if fields.get("phone") != driver.phone else None,
        national_id=fields.get("national_id"),
        exclude=driver.id,
    )

    before = _snapshot(driver)
    old_status = driver.employment_status
    if "national_id" in fields:
        _set_national_id(driver, fields.pop("national_id"))
    new_status = fields.get("employment_status", old_status)
    if new_status is EmploymentStatus.TERMINATED and old_status is not EmploymentStatus.TERMINATED:
        fields.setdefault("end_date", fields.get("end_date") or local_today())
    apply_changes(driver, fields, ())
    changes = audit.diff(before, _snapshot(driver))
    if not changes:
        return driver

    details: dict[str, Any] = {}
    if new_status is not old_status:
        if new_status in INACTIVE_STATUSES and driver.user is not None and driver.user.is_active:
            # A suspended/terminated driver must not keep using the driver app.
            driver.user.is_active = False
            details["sessions_revoked"] = auth_service.revoke_user_sessions(
                db, driver.user.id, reason=f"driver_{new_status.value.lower()}"
            )
            details["app_account_deactivated"] = True
        if new_status is EmploymentStatus.TERMINATED:
            details["assignments_ended"] = end_open_assignments_for_driver(
                db, actor=actor, driver_id=driver.id, note="driver_terminated"
            )
    # Keep the linked app account's name/phone in sync with the driver profile.
    if driver.user is not None:
        if "full_name" in changes:
            driver.user.full_name = driver.full_name
        if "phone" in changes:
            users_service.ensure_phone_available(db, driver.phone, exclude=driver.user.id)
            driver.user.phone = driver.phone

    audit.record(
        db,
        action="driver.updated",
        actor=actor,
        entity_type="driver",
        entity_id=driver.id,
        changes=changes,
        details=details or None,
    )
    db.commit()
    return driver


def read_national_id(db: Session, *, actor: User, driver_id: uuid.UUID) -> str | None:
    """Decrypt for an authorised viewer; every access is audited."""
    driver = get_driver(db, driver_id)
    value = crypto.decrypt(driver.national_id_encrypted) if driver.national_id_encrypted else None
    audit.record(
        db,
        action="driver.sensitive_viewed",
        actor=actor,
        entity_type="driver",
        entity_id=driver.id,
        details={"fields": ["national_id"]},
    )
    db.commit()
    return value


# ------------------------------------------------------------------ app account


def create_app_account(db: Session, *, actor: User, driver_id: uuid.UUID, password: str) -> Driver:
    driver = get_driver(db, driver_id, for_update=True)
    if driver.user_id is not None:
        raise ConflictError("لدى السائق حساب تطبيق بالفعل", code="driver_has_account")
    if driver.employment_status is not EmploymentStatus.ACTIVE:
        raise ValidationFailed("لا يمكن إنشاء حساب لسائق غير نشط", code="driver_not_active")
    existing = db.scalar(select(User).where(User.phone == driver.phone))
    if existing is not None:
        raise ConflictError("رقم هاتف السائق مستخدم لحساب آخر في النظام", code="phone_taken")
    # Drivers' accounts are always role DRIVER, so drivers:write is sufficient.
    user = users_service.create_user(
        db,
        actor=actor,
        enforce_role_policy=False,
        data=UserCreate(
            full_name=driver.full_name,
            phone=driver.phone,
            role=UserRole.DRIVER,
            password=password,
        ),
        commit=False,
    )
    driver.user_id = user.id
    audit.record(
        db,
        action="driver.app_account_created",
        actor=actor,
        entity_type="driver",
        entity_id=driver.id,
        details={"user_id": user.id},
    )
    db.commit()
    db.refresh(driver)
    return driver


def reset_app_password(db: Session, *, actor: User, driver_id: uuid.UUID, password: str) -> None:
    driver = get_driver(db, driver_id)
    if driver.user is None:
        raise NotFoundError("لا يوجد حساب تطبيق لهذا السائق", code="driver_has_no_account")
    auth_service.validate_new_password(password, phone=driver.phone)
    driver.user.password_hash = hash_password(password)
    driver.user.password_changed_at = utcnow()
    driver.user.failed_login_count = 0
    driver.user.locked_until = None
    revoked = auth_service.revoke_user_sessions(db, driver.user.id, reason="password_reset")
    audit.record(
        db,
        action="user.password_reset",
        actor=actor,
        entity_type="user",
        entity_id=driver.user.id,
        details={"sessions_revoked": revoked, "via": "driver"},
    )
    db.commit()


def set_app_account_active(
    db: Session, *, actor: User, driver_id: uuid.UUID, active: bool
) -> Driver:
    driver = get_driver(db, driver_id)
    if driver.user is None:
        raise NotFoundError("لا يوجد حساب تطبيق لهذا السائق", code="driver_has_no_account")
    if active and driver.employment_status is not EmploymentStatus.ACTIVE:
        raise ValidationFailed("لا يمكن تفعيل حساب سائق غير نشط", code="driver_not_active")
    if driver.user.is_active == active:
        return driver
    driver.user.is_active = active
    revoked = (
        0 if active else auth_service.revoke_user_sessions(db, driver.user.id, reason="deactivated")
    )
    audit.record(
        db,
        action="user.activated" if active else "user.deactivated",
        actor=actor,
        entity_type="user",
        entity_id=driver.user.id,
        changes={"is_active": {"old": not active, "new": active}},
        details={"via": "driver", "sessions_revoked": revoked},
    )
    db.commit()
    return driver


# ------------------------------------------------------------------ compensation


def list_compensation_plans(db: Session, driver_id: uuid.UUID) -> list[DriverCompensationPlan]:
    get_driver(db, driver_id)
    return list(
        db.scalars(
            select(DriverCompensationPlan)
            .where(DriverCompensationPlan.driver_id == driver_id)
            .order_by(DriverCompensationPlan.effective_from.desc())
        ).all()
    )


def plan_for_date(db: Session, driver_id: uuid.UUID, day: Any) -> DriverCompensationPlan | None:
    return db.scalar(
        select(DriverCompensationPlan).where(
            DriverCompensationPlan.driver_id == driver_id,
            DriverCompensationPlan.effective_from <= day,
            or_(
                DriverCompensationPlan.effective_to.is_(None),
                DriverCompensationPlan.effective_to >= day,
            ),
        )
    )


def add_compensation_plan(
    db: Session, *, actor: User, driver_id: uuid.UUID, data: CompensationPlanCreate
) -> DriverCompensationPlan:
    """Start a new plan. The open plan is closed the day before; history is never edited."""
    get_driver(db, driver_id, for_update=True)
    latest = db.scalar(
        select(DriverCompensationPlan)
        .where(DriverCompensationPlan.driver_id == driver_id)
        .order_by(DriverCompensationPlan.effective_from.desc())
        .limit(1)
        .with_for_update()
    )
    if latest is not None:
        if data.effective_from <= latest.effective_from:
            raise ConflictError(
                "تاريخ بداية الخطة الجديدة يجب أن يكون بعد بداية الخطة الحالية",
                code="plan_effective_date_conflict",
            )
        if latest.effective_to is None or latest.effective_to >= data.effective_from:
            old_to = latest.effective_to
            latest.effective_to = data.effective_from - timedelta(days=1)
            audit.record(
                db,
                action="compensation_plan.closed",
                actor=actor,
                entity_type="compensation_plan",
                entity_id=latest.id,
                changes={
                    "effective_to": {
                        "old": audit.to_jsonable(old_to),
                        "new": latest.effective_to.isoformat(),
                    }
                },
            )
    plan = DriverCompensationPlan(driver_id=driver_id, created_by_id=actor.id, **data.model_dump())
    if (
        plan.method is CompensationMethod.FIXED_PLUS_INCENTIVE
        and plan.incentive_threshold_amount is None
    ):
        plan.incentive_threshold_amount = Decimal("0.00")
    db.add(plan)
    db.flush()
    audit.record(
        db,
        action="compensation_plan.created",
        actor=actor,
        entity_type="compensation_plan",
        entity_id=plan.id,
        changes=audit.diff(
            {},
            audit.snapshot(
                plan,
                (
                    "driver_id",
                    "method",
                    "fixed_monthly_amount",
                    "daily_wage_amount",
                    "revenue_percentage",
                    "incentive_percentage",
                    "incentive_threshold_amount",
                    "effective_from",
                ),
            ),
        ),
    )
    db.commit()
    return plan
