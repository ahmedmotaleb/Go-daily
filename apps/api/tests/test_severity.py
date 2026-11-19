"""Severity from current evidence, and escalation reminders (U27)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import utcnow
from app.models.exceptions import (
    ExceptionLabel,
    ExceptionSeverity,
    ExceptionStatus,
    OperationalException,
)
from app.services import notifications, severity
from app.services.exception_rules import RULE_INFO, Candidate, RuleResult
from app.services.exceptions import _store

S = ExceptionSeverity
NOW = utcnow()


def _assess(
    proposed: ExceptionSeverity, evidence: dict[str, object], minutes: int | None = None
) -> tuple[ExceptionSeverity, dict[str, Any]]:
    until = NOW + timedelta(minutes=minutes) if minutes is not None else None
    return severity.assess(proposed, evidence, NOW, until, get_settings())


def test_money_and_duration_raise_severity() -> None:
    assert _assess(S.LOW, {"amount": "3000"})[0] is S.HIGH
    assert _assess(S.LOW, {"outstanding": "800"})[0] is S.MEDIUM
    assert _assess(S.LOW, {"gas_amount": "20"})[0] is S.INFO
    assert _assess(S.MEDIUM, {"amount": "20"})[0] is S.MEDIUM  # never lowered below the rule
    assert _assess(S.LOW, {}, minutes=180)[0] is S.MEDIUM
    assert _assess(S.HIGH, {}, minutes=5)[0] is S.HIGH


def test_history_never_raises_severity() -> None:
    level, basis = _assess(S.LOW, {"previous_cases": 12, "repeat_count": 30, "history_weeks": 8})
    assert level is S.LOW
    assert basis["history_used"] is False
    assert basis["reasons"] == ["حسب القاعدة"]


def test_basis_is_stored_with_the_case(db: Session) -> None:
    info = RULE_INFO["FUEL_PLAUSIBILITY"]
    key = f"TEST:{uuid.uuid4()}"
    outcome = RuleResult(
        candidates=[
            Candidate(
                rule_code=info.code,
                severity=S.LOW,
                summary="اختبار",
                evidence={"amount": "2500"},
                occurred_at=NOW - timedelta(hours=1),
                dedupe_key=key,
            )
        ]
    )
    _store(db, info, outcome, get_settings())
    case = db.scalars(
        select(OperationalException).where(OperationalException.dedupe_key == key)
    ).one()
    assert case.severity is S.HIGH
    assert case.evidence["severity_basis"]["rule_severity"] == "LOW"
    assert case.evidence["severity_basis"]["money"] == "2500"


def test_unreviewed_high_cases_remind_reviewers(db: Session) -> None:
    old = OperationalException(
        rule_code="CASH_NOT_HANDED_OVER",
        severity=S.HIGH,
        label=ExceptionLabel.REVIEW_REQUIRED,
        summary="نقدية لم تُسلّم — مراجعة مطلوبة",
        evidence={},
        occurred_at=NOW - timedelta(days=3),
        detected_at=NOW - timedelta(hours=30),
        status=ExceptionStatus.OPEN,
        dedupe_key=f"TEST:{uuid.uuid4()}",
    )
    fresh = OperationalException(
        rule_code="CASH_NOT_HANDED_OVER",
        severity=S.HIGH,
        label=ExceptionLabel.REVIEW_REQUIRED,
        summary="حديثة",
        evidence={},
        occurred_at=NOW,
        detected_at=NOW,
        status=ExceptionStatus.OPEN,
        dedupe_key=f"TEST:{uuid.uuid4()}",
    )
    db.add_all([old, fresh])
    db.commit()
    drafts = notifications.escalations(db)
    keys = {d.dedupe_key for d in drafts}
    assert f"ESCALATION:{old.id}" in keys and f"ESCALATION:{fresh.id}" not in keys
    assert all(d.permission.value == "exceptions:review" for d in drafts)
    # Once a reviewer starts, the reminder stops.
    old.status = ExceptionStatus.UNDER_REVIEW
    db.commit()
    assert f"ESCALATION:{old.id}" not in {d.dedupe_key for d in notifications.escalations(db)}
