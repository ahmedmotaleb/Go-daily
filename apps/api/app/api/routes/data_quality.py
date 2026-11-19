"""Data quality dashboard (U49)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import DbSession, require_permissions
from app.core.permissions import Permission
from app.models.user import User
from app.services import data_quality

router = APIRouter(prefix="/data-quality", tags=["data-quality"])

Reader = Annotated[User, Depends(require_permissions(Permission.REPORTS_READ))]


class ExampleOut(BaseModel):
    title: str
    link: str | None


class CheckOut(BaseModel):
    code: str
    title: str
    why: str
    count: int
    examples: list[ExampleOut]


class ReviewCountOut(BaseModel):
    rule_code: str
    title: str
    count: int


class DataQualityOut(BaseModel):
    missing: list[CheckOut]
    review: list[ReviewCountOut]
    generated_at: datetime


@router.get("", response_model=DataQualityOut)
def get_data_quality(_: Reader, db: DbSession) -> DataQualityOut:
    r = data_quality.report(db)
    return DataQualityOut(
        missing=[
            CheckOut(
                code=c.code,
                title=c.title,
                why=c.why,
                count=c.count,
                examples=[ExampleOut(title=e.title, link=e.link) for e in c.examples],
            )
            for c in r.missing
        ],
        review=[
            ReviewCountOut(rule_code=x.rule_code, title=x.title, count=x.count) for x in r.review
        ],
        generated_at=r.generated_at,
    )
