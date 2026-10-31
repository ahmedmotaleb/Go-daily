"""Exception engine: runs the rules, stores what they find, handles reviews (Task 20).

The same situation found again updates its existing row (dedupe key), so
re-running is safe and never piles up duplicates. Closed exceptions are not
reopened or rewritten by later runs: what the reviewer saw stays as it was.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core import monitoring
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, field_error
from app.core.time import local_day_bounds_utc, utcnow
from app.models.exceptions import (
    ExceptionLabel,
    ExceptionRun,
    ExceptionSeverity,
    ExceptionStatus,
    OperationalException,
)
from app.models.user import User
from app.schemas.common import PageParams
from app.services import audit
from app.services.common import paginate
from app.services.exception_rules import RULES, Context, RuleInfo, RuleResult, is_enabled

logger = logging.getLogger(__name__)

S = ExceptionStatus
ACTIVE = (S.OPEN, S.UNDER_REVIEW, S.ESCALATED)
CLOSED = (S.EXPLAINED, S.CORRECTED, S.DISMISSED)

TRANSITIONS: dict[ExceptionStatus, frozenset[ExceptionStatus]] = {
    S.OPEN: frozenset({S.UNDER_REVIEW, S.EXPLAINED, S.CORRECTED, S.DISMISSED, S.ESCALATED}),
    S.UNDER_REVIEW: frozenset({S.OPEN, S.EXPLAINED, S.CORRECTED, S.DISMISSED, S.ESCALATED}),
    S.ESCALATED: frozenset({S.UNDER_REVIEW, S.EXPLAINED, S.CORRECTED, S.DISMISSED}),
    # Reopening is the only way back from a decision, and needs a note.
    S.EXPLAINED: frozenset({S.OPEN}),
    S.CORRECTED: frozenset({S.OPEN}),
    S.DISMISSED: frozenset({S.OPEN}),
}

# Advisory lock id: one detection run at a time.
_RUN_LOCK = 2020_1030


def run_detection(
    db: Session, *, actor: User | None, trigger: str, days: int | None = None
) -> ExceptionRun:
    settings = get_settings()
    end = utcnow()
    start = end - timedelta(days=days or settings.exception_lookback_days)
    if not db.scalar(select(func.pg_try_advisory_xact_lock(_RUN_LOCK))):
        raise ConflictError("يوجد فحص آخر قيد التشغيل؛ حاول بعد قليل")
    run = ExceptionRun(
        window_start=start,
        window_end=end,
        triggered_by_id=actor.id if actor else None,
        trigger=trigger,
        results={},
        errors={},
    )
    db.add(run)
    db.flush()
    ctx = Context(db, settings, start, end)
    results: dict[str, Any] = {}
    errors: dict[str, Any] = {}
    for info, rule in RULES:
        if not is_enabled(info.code, settings):
            results[info.code] = {"skipped": "disabled"}
            continue
        try:
            with db.begin_nested():
                outcome = rule(ctx)
                new = _store(db, info, outcome)
            results[info.code] = {"found": len(outcome.candidates), "new": new}
        except Exception as exc:
            # One broken rule must not stop the others; the run records it.
            logger.exception("exception_rule_failed", extra={"rule": info.code})
            monitoring.capture_exception(exc, component="exception_rule", name=info.code)
            errors[info.code] = type(exc).__name__
    run.results = results
    run.errors = errors
    run.finished_at = utcnow()
    db.commit()
    return run


def _store(db: Session, info: RuleInfo, outcome: RuleResult) -> int:
    now = utcnow()
    produced: set[str] = set()
    new = 0
    for c in outcome.candidates:
        produced.add(c.dedupe_key)
        evidence = audit.to_jsonable(c.evidence)
        values: dict[str, Any] = {
            "rule_code": c.rule_code,
            "severity": c.severity,
            "label": info.label,
            "summary": c.summary[:300],
            "evidence": evidence,
            "occurred_at": c.occurred_at,
            "occurred_until": c.occurred_until,
            "detected_at": now,
            "last_detected_at": now,
            "vehicle_id": c.vehicle_id,
            "driver_id": c.driver_id,
            "shift_id": c.shift_id,
            "subject_type": c.subject_type,
            "subject_id": c.subject_id,
            "dedupe_key": c.dedupe_key,
            "status": S.OPEN,
        }
        inserted = db.execute(
            pg_insert(OperationalException)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
            .returning(OperationalException.id)
        ).scalar()
        if inserted is not None:
            new += 1
            continue
        existing = db.scalars(
            select(OperationalException)
            .where(OperationalException.dedupe_key == c.dedupe_key)
            .with_for_update(of=OperationalException)
        ).one()
        existing.last_detected_at = now
        existing.cleared_at = None
        if existing.status in ACTIVE:
            existing.summary = values["summary"]
            existing.evidence = evidence
            existing.severity = c.severity
            existing.occurred_at = c.occurred_at
            existing.occurred_until = c.occurred_until
    stale = outcome.scopes - produced
    if stale:
        db.execute(
            update(OperationalException)
            .where(
                OperationalException.rule_code == info.code,
                OperationalException.dedupe_key.in_(stale),
                OperationalException.status.in_(ACTIVE),
                OperationalException.cleared_at.is_(None),
            )
            .values(cleared_at=now)
        )
    db.flush()
    return new


_COORDINATE_KEYS = frozenset({"lat", "lng", "latitude", "longitude"})


def _without_coordinates(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_coordinates(v) for k, v in value.items() if k not in _COORDINATE_KEYS}
    if isinstance(value, list):
        return [_without_coordinates(v) for v in value]
    return value


def redact_old_evidence(db: Session, *, older_than_days: int) -> int:
    """Remove coordinates from the evidence of closed cases past GPS retention.

    Raw points are deleted after the retention period; closed cases must not
    keep the same locations indefinitely. Times, durations and distances stay,
    so the review record remains readable. Open cases keep their evidence.
    """
    cutoff = utcnow() - timedelta(days=older_than_days)
    cases = db.scalars(
        select(OperationalException).where(
            OperationalException.status.in_(CLOSED),
            OperationalException.occurred_at < cutoff,
        )
    ).all()
    changed = 0
    for case in cases:
        cleaned = _without_coordinates(case.evidence)
        if cleaned != case.evidence:
            case.evidence = {**cleaned, "coordinates_removed": True}
            changed += 1
    db.commit()
    return changed


def last_run(db: Session) -> ExceptionRun | None:
    return db.scalars(
        select(ExceptionRun).order_by(ExceptionRun.started_at.desc()).limit(1)
    ).first()


# --- Queries ----------------------------------------------------------------


@dataclass
class ExceptionFilters:
    # "ACTIVE" = open, under review or escalated.
    status: str | None = None
    severity: ExceptionSeverity | None = None
    label: ExceptionLabel | None = None
    rule_code: str | None = None
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None
    shift_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None


def _filtered(f: ExceptionFilters) -> Select[OperationalException]:
    stmt = select(OperationalException)
    if f.status == "ACTIVE":
        stmt = stmt.where(OperationalException.status.in_(ACTIVE))
    elif f.status:
        stmt = stmt.where(OperationalException.status == ExceptionStatus(f.status))
    if f.severity:
        stmt = stmt.where(OperationalException.severity == f.severity)
    if f.label:
        stmt = stmt.where(OperationalException.label == f.label)
    if f.rule_code:
        stmt = stmt.where(OperationalException.rule_code == f.rule_code)
    if f.vehicle_id:
        stmt = stmt.where(OperationalException.vehicle_id == f.vehicle_id)
    if f.driver_id:
        stmt = stmt.where(OperationalException.driver_id == f.driver_id)
    if f.shift_id:
        stmt = stmt.where(OperationalException.shift_id == f.shift_id)
    if f.date_from:
        stmt = stmt.where(OperationalException.occurred_at >= local_day_bounds_utc(f.date_from)[0])
    if f.date_to:
        stmt = stmt.where(OperationalException.occurred_at < local_day_bounds_utc(f.date_to)[1])
    return stmt


def list_exceptions(
    db: Session, params: PageParams, filters: ExceptionFilters
) -> tuple[list[OperationalException], int]:
    stmt = _filtered(filters).order_by(
        OperationalException.occurred_at.desc(), OperationalException.id
    )
    return paginate(db, stmt, params)


def get(db: Session, exception_id: uuid.UUID) -> OperationalException:
    exc = db.get(OperationalException, exception_id)
    if exc is None:
        raise NotFoundError("الحالة غير موجودة")
    return exc


def summary(db: Session) -> dict[str, Any]:
    """Counts of exceptions still needing attention."""
    rows = db.execute(
        select(
            OperationalException.status,
            OperationalException.severity,
            OperationalException.rule_code,
            func.count(),
        )
        .where(OperationalException.status.in_(ACTIVE))
        .group_by(
            OperationalException.status,
            OperationalException.severity,
            OperationalException.rule_code,
        )
    ).all()
    by_status: dict[str, int] = {s.value: 0 for s in ACTIVE}
    by_severity: dict[str, int] = {s.value: 0 for s in ExceptionSeverity}
    by_rule: dict[str, int] = {}
    for status, severity, rule_code, count in rows:
        by_status[status.value] += count
        by_severity[severity.value] += count
        by_rule[rule_code] = by_rule.get(rule_code, 0) + count
    return {
        "active": sum(by_status.values()),
        "by_status": by_status,
        "by_severity": by_severity,
        "by_rule": by_rule,
    }


# --- Review -----------------------------------------------------------------


def review(
    db: Session,
    *,
    actor: User,
    exception_id: uuid.UUID,
    status: ExceptionStatus,
    notes: str | None,
    resolution: str | None,
) -> OperationalException:
    exc = db.scalars(
        select(OperationalException)
        .where(OperationalException.id == exception_id)
        .with_for_update(of=OperationalException)
    ).first()
    if exc is None:
        raise NotFoundError("الحالة غير موجودة")
    if status not in TRANSITIONS[exc.status]:
        raise ConflictError("لا يمكن نقل الحالة إلى هذه الخطوة من وضعها الحالي")
    notes = (notes or "").strip() or None
    resolution = (resolution or "").strip() or None
    if status in CLOSED and not resolution:
        raise field_error("resolution", "اكتب نتيجة المراجعة")
    if (status is S.ESCALATED or exc.status in CLOSED) and not notes:
        raise field_error("notes", "اكتب سبب التصعيد أو إعادة الفتح")
    before = {"status": exc.status.value, "resolution": exc.resolution}
    exc.status = status
    exc.reviewer = actor
    exc.reviewed_at = utcnow()
    if notes:
        exc.review_notes = notes
    if status in CLOSED:
        exc.resolution = resolution
    elif status is S.OPEN:
        exc.resolution = None
    audit.record(
        db,
        action="operational_exception.reviewed",
        actor=actor,
        entity_type="operational_exception",
        entity_id=exc.id,
        changes=audit.diff(before, {"status": exc.status.value, "resolution": exc.resolution}),
        details={"rule_code": exc.rule_code},
        reason=notes,
    )
    db.commit()
    return exc
