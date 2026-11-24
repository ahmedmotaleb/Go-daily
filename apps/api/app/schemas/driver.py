"""Driver and compensation plan schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.core.text import normalize_national_id
from app.models.driver import CompensationMethod, EmploymentStatus
from app.schemas.common import ORMModel, PhoneMixin, ShortText
from app.schemas.fleet import AssignmentSummary
from app.services.expiry import ExpiryStatus

Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
LicenseNo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
Amount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Percent = Annotated[Decimal, Field(gt=0, le=100, max_digits=5, decimal_places=2)]


class _DriverFields(PhoneMixin):
    @field_validator("national_id", mode="before", check_fields=False)
    @classmethod
    def _nid(cls, v: object) -> object:
        if isinstance(v, str):
            if not v.strip():
                return None
            return normalize_national_id(v)
        return v

    @field_validator("license_number", "notes", mode="before", check_fields=False)
    @classmethod
    def _blank(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v


class DriverCreate(_DriverFields):
    full_name: ShortText
    phone: str
    national_id: str | None = None
    license_number: LicenseNo | None = None
    license_expiry: date | None = None
    employment_status: EmploymentStatus = EmploymentStatus.ACTIVE
    hire_date: date | None = None
    notes: Notes | None = None


class DriverUpdate(_DriverFields):
    full_name: ShortText | None = None
    phone: str | None = None
    national_id: str | None = None
    license_number: LicenseNo | None = None
    license_expiry: date | None = None
    employment_status: EmploymentStatus | None = None
    hire_date: date | None = None
    end_date: date | None = None
    notes: Notes | None = None


class DriverOut(ORMModel):
    id: uuid.UUID
    full_name: str
    phone: str
    national_id_masked: str | None
    license_number: str | None
    license_expiry: date | None
    license_status: ExpiryStatus
    employment_status: EmploymentStatus
    hire_date: date | None
    end_date: date | None
    notes: str | None
    user_id: uuid.UUID | None
    app_account_active: bool | None
    current_assignments: list[AssignmentSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DriverSensitiveOut(BaseModel):
    national_id: str | None


class DriverAccountCreate(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class CompensationPlanCreate(BaseModel):
    method: CompensationMethod
    fixed_monthly_amount: Amount | None = None
    daily_wage_amount: Amount | None = None
    revenue_percentage: Percent | None = None
    incentive_percentage: Percent | None = None
    incentive_threshold_amount: (
        Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)] | None
    ) = None
    effective_from: date
    notes: Notes | None = None

    @model_validator(mode="after")
    def _fields_match_method(self) -> Self:
        m = self.method
        required: dict[CompensationMethod, tuple[str, ...]] = {
            CompensationMethod.FIXED_MONTHLY: ("fixed_monthly_amount",),
            CompensationMethod.DAILY_WAGE: ("daily_wage_amount",),
            CompensationMethod.REVENUE_PERCENTAGE: ("revenue_percentage",),
            CompensationMethod.FIXED_PLUS_INCENTIVE: (
                "fixed_monthly_amount",
                "incentive_percentage",
            ),
        }
        allowed = set(required[m]) | (
            {"incentive_threshold_amount"}
            if m is CompensationMethod.FIXED_PLUS_INCENTIVE
            else set()
        )
        amount_fields = {
            "fixed_monthly_amount",
            "daily_wage_amount",
            "revenue_percentage",
            "incentive_percentage",
            "incentive_threshold_amount",
        }
        missing = [f for f in required[m] if getattr(self, f) is None]
        if missing:
            raise ValueError(f"حقول مطلوبة لطريقة الاحتساب: {', '.join(missing)}")
        extra = [f for f in amount_fields - allowed if getattr(self, f) is not None]
        if extra:
            raise ValueError(f"حقول غير مستخدمة مع طريقة الاحتساب: {', '.join(extra)}")
        return self


class CompensationPlanOut(ORMModel):
    id: uuid.UUID
    driver_id: uuid.UUID
    method: CompensationMethod
    fixed_monthly_amount: Decimal | None
    daily_wage_amount: Decimal | None
    revenue_percentage: Decimal | None
    incentive_percentage: Decimal | None
    incentive_threshold_amount: Decimal | None
    effective_from: date
    effective_to: date | None
    notes: str | None
    created_at: datetime
