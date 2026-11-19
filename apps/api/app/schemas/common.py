"""Shared schema building blocks."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.core.phone import InvalidPhoneError, normalize_phone


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class PageParams(BaseModel):
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
OptionalNotes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class PhoneMixin(BaseModel):
    @field_validator("phone", mode="before", check_fields=False)
    @classmethod
    def _normalise_phone(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                return normalize_phone(value)
            except InvalidPhoneError as exc:
                raise ValueError(str(exc)) from exc
        return value


class Message(BaseModel):
    message: str
