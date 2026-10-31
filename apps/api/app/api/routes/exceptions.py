"""Operational exceptions: list, review, run detection (Task 20)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_permissions
from app.core.config import get_settings
from app.core.permissions import Permission
from app.models.exceptions import (
    ExceptionLabel,
    ExceptionRun,
    ExceptionSeverity,
    ExceptionStatus,
    OperationalException,
)
from app.models.user import User
from app.schemas.common import Page, PageParams, page_params
from app.schemas.exceptions import (
    ExceptionOut,
    ReviewIn,
    RuleOut,
    RulesOut,
    RunIn,
    RunOut,
    SummaryOut,
)
from app.schemas.finance import Ref, UserRef
from app.services import exception_rules
from app.services import exceptions as exception_service

router = APIRouter(prefix="/exceptions", tags=["exceptions"])

Reader = Annotated[User, Depends(require_permissions(Permission.EXCEPTIONS_READ))]
Reviewer = Annotated[User, Depends(require_permissions(Permission.EXCEPTIONS_REVIEW))]


def _out(e: OperationalException) -> ExceptionOut:
    info = exception_rules.RULE_INFO.get(e.rule_code)
    return ExceptionOut(
        id=e.id,
        rule_code=e.rule_code,
        rule_title=info.title_ar if info else e.rule_code,
        severity=e.severity,
        label=e.label,
        summary=e.summary,
        evidence=e.evidence,
        occurred_at=e.occurred_at,
        occurred_until=e.occurred_until,
        detected_at=e.detected_at,
        last_detected_at=e.last_detected_at,
        cleared_at=e.cleared_at,
        vehicle=Ref(id=e.vehicle.id, name=e.vehicle.internal_code) if e.vehicle else None,
        driver=Ref(id=e.driver.id, name=e.driver.full_name) if e.driver else None,
        shift_id=e.shift_id,
        subject_type=e.subject_type,
        subject_id=e.subject_id,
        status=e.status,
        reviewer=UserRef(id=e.reviewer.id, full_name=e.reviewer.full_name) if e.reviewer else None,
        reviewed_at=e.reviewed_at,
        review_notes=e.review_notes,
        resolution=e.resolution,
        allowed_transitions=sorted(exception_service.TRANSITIONS[e.status]),
        updated_at=e.updated_at,
    )


def _run_out(run: ExceptionRun) -> RunOut:
    return RunOut(
        id=run.id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        window_start=run.window_start,
        window_end=run.window_end,
        trigger=run.trigger,
        results=run.results,
        errors=run.errors,
    )


@router.get("", response_model=Page[ExceptionOut])
def list_exceptions(
    _: Reader,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    status: ExceptionStatus | Literal["ACTIVE"] | None = None,
    severity: ExceptionSeverity | None = None,
    label: ExceptionLabel | None = None,
    rule_code: str | None = None,
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    shift_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page[ExceptionOut]:
    rows, total = exception_service.list_exceptions(
        db,
        params,
        exception_service.ExceptionFilters(
            status=status,
            severity=severity,
            label=label,
            rule_code=rule_code,
            vehicle_id=vehicle_id,
            driver_id=driver_id,
            shift_id=shift_id,
            date_from=date_from,
            date_to=date_to,
        ),
    )
    return Page(
        items=[_out(e) for e in rows], total=total, page=params.page, page_size=params.page_size
    )


@router.get("/summary", response_model=SummaryOut)
def summary(_: Reader, db: DbSession) -> SummaryOut:
    return SummaryOut(**exception_service.summary(db))


@router.get("/rules", response_model=RulesOut)
def rules(_: Reader, db: DbSession) -> RulesOut:
    settings = get_settings()
    run = exception_service.last_run(db)
    return RulesOut(
        rules=[
            RuleOut(
                code=info.code,
                title_ar=info.title_ar,
                description_ar=info.description_ar,
                label=info.label,
                enabled=exception_rules.is_enabled(info.code, settings),
            )
            for info, _ in exception_rules.RULES
        ],
        thresholds={
            name.removeprefix("exception_"): value
            for name, value in settings.model_dump().items()
            if name.startswith("exception_")
        },
        last_run=_run_out(run) if run else None,
    )


@router.post("/run", response_model=RunOut)
def run(body: RunIn, actor: Reviewer, db: DbSession) -> RunOut:
    return _run_out(exception_service.run_detection(db, actor=actor, trigger="api", days=body.days))


@router.get("/{exception_id}", response_model=ExceptionOut)
def get_exception(exception_id: uuid.UUID, _: Reader, db: DbSession) -> ExceptionOut:
    return _out(exception_service.get(db, exception_id))


@router.post("/{exception_id}/review", response_model=ExceptionOut)
def review(exception_id: uuid.UUID, body: ReviewIn, actor: Reviewer, db: DbSession) -> ExceptionOut:
    return _out(
        exception_service.review(
            db,
            actor=actor,
            exception_id=exception_id,
            status=body.status,
            notes=body.notes,
            resolution=body.resolution,
        )
    )
