"""Alert rules (U37) stay in step with /metrics and the runbook."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import UserRole
from tests.factories import login_as

ROOT = Path(__file__).resolve().parents[3]
RULES = ROOT / "ops" / "monitoring" / "alerts.yml"
RUNBOOK = ROOT / "docs" / "OPERATIONS.md"
# Provided by Prometheus itself or derived from a histogram, not by /metrics.
BUILTIN = {"up", "godaily_http_request_duration_seconds_bucket"}


def _rules() -> list[dict[str, Any]]:
    data = yaml.safe_load(RULES.read_text())
    return [r for g in data["groups"] for r in g["rules"]]


def _anchors() -> set[str]:
    out = set()
    for line in RUNBOOK.read_text().splitlines():
        if line.startswith("#"):
            title = line.lstrip("#").strip().lower()
            out.add(re.sub(r"[^a-z0-9 -]", "", title).replace(" ", "-"))
    return out


def test_every_alert_is_actionable() -> None:
    anchors = _anchors()
    names = set()
    for rule in _rules():
        assert rule["alert"] not in names
        names.add(rule["alert"])
        assert rule["labels"]["severity"] in {"critical", "warning"}, rule["alert"]
        assert rule["annotations"]["summary"]
        link = rule["annotations"]["runbook"]
        assert link.startswith("docs/OPERATIONS.md#")
        assert link.split("#", 1)[1] in anchors, f"{rule['alert']}: missing runbook section"


def test_alerts_use_metrics_the_api_exposes(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The detection-run gauges appear once a run has finished.
    _, admin = login_as(client, db, UserRole.ADMIN)
    assert client.post("/api/v1/exceptions/run", json={"days": 1}, headers=admin).status_code in (
        200,
        201,
    )
    monkeypatch.setattr(get_settings(), "metrics_token", SecretStr("t"))
    body = client.get("/metrics", headers={"Authorization": "Bearer t"}).text
    exposed = set(re.findall(r"^# TYPE (\w+)", body, re.MULTILINE))
    for rule in _rules():
        for metric in set(re.findall(r"\b(godaily_\w+|up)\b", rule["expr"])):
            if metric in BUILTIN:
                continue
            assert metric in exposed, f"{rule['alert']} uses {metric}, not exposed"
