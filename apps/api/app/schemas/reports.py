"""Report schemas (Task 23)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel


class ReportInfo(BaseModel):
    code: str
    title: str
    description: str
    filters: list[str]


class ColumnOut(BaseModel):
    key: str
    label: str
    type: str
    total: bool


class TableOut(BaseModel):
    columns: list[ColumnOut]
    rows: list[dict[str, Any]]
    totals: dict[str, Any]


class SummaryOut(TableOut):
    title: str


class ReportOut(TableOut):
    code: str
    title: str
    date_from: date
    date_to: date
    summaries: list[SummaryOut]
    notes: list[str]
