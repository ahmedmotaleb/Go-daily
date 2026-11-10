"""Severity from current evidence (U27).

Each rule proposes a severity. This adjusts it with what the current case
shows, never with the past:

- money involved (the largest amount in the evidence, in EGP): at least
  MEDIUM from SEVERITY_MEDIUM_AMOUNT, HIGH from SEVERITY_HIGH_AMOUNT; a case
  about a very small amount (under SEVERITY_INFO_AMOUNT) proposed as LOW
  becomes INFO;
- operational impact (how long the situation lasted): at least MEDIUM from
  SEVERITY_LONG_MINUTES.

Earlier cases for the same driver or vehicle never raise severity: a
history is context for the reviewer, not evidence about this case. The
basis is stored with the case so the reviewer sees why it got its level.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.config import Settings
from app.models.exceptions import ExceptionSeverity as Sev

ORDER = [Sev.INFO, Sev.LOW, Sev.MEDIUM, Sev.HIGH]
# Evidence keys that hold amounts of money for the current case.
MONEY_KEYS = (
    "amount",
    "total_amount",
    "outstanding",
    "difference",
    "shortfall",
    "missing_amount",
    "gap_amount",
)


def _money(evidence: dict[str, Any]) -> Decimal | None:
    found: list[Decimal] = []
    for key, value in evidence.items():
        if key in MONEY_KEYS or key.endswith("_amount"):
            try:
                found.append(abs(Decimal(str(value))))
            except (InvalidOperation, ValueError):
                continue
    return max(found) if found else None


def assess(
    proposed: Sev,
    evidence: dict[str, Any],
    occurred_at: datetime,
    occurred_until: datetime | None,
    settings: Settings,
) -> tuple[Sev, dict[str, Any]]:
    level = ORDER.index(proposed)
    reasons: list[str] = []
    money = _money(evidence)
    if money is not None:
        if money >= settings.severity_high_amount and level < ORDER.index(Sev.HIGH):
            level = ORDER.index(Sev.HIGH)
            reasons.append("المبلغ المعني كبير")
        elif money >= settings.severity_medium_amount and level < ORDER.index(Sev.MEDIUM):
            level = ORDER.index(Sev.MEDIUM)
            reasons.append("المبلغ المعني متوسط")
        elif money < settings.severity_info_amount and proposed is Sev.LOW:
            level = ORDER.index(Sev.INFO)
            reasons.append("المبلغ المعني صغير")
    minutes = None
    if occurred_until is not None:
        minutes = round((occurred_until - occurred_at).total_seconds() / 60)
        if minutes >= settings.severity_long_minutes and level < ORDER.index(Sev.MEDIUM):
            level = ORDER.index(Sev.MEDIUM)
            reasons.append("استمرت الحالة مدة طويلة")
    final = ORDER[level]
    basis: dict[str, Any] = {
        "rule_severity": proposed.value,
        "final_severity": final.value,
        "money": str(money) if money is not None else None,
        "duration_minutes": minutes,
        "reasons": reasons or ["حسب القاعدة"],
        "history_used": False,
    }
    return final, basis


__all__ = ["assess"]
