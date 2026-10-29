"""Declarative base and shared column mixins."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, Numeric, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.time import utcnow

# Deterministic constraint names keep Alembic autogenerate diffs stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Money is always stored as fixed-point decimal; never binary floating point.
Money = Numeric(14, 2)
Quantity = Numeric(14, 3)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        uuid.UUID: UUID(as_uuid=True),
        Decimal: Money,
    }


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow, server_default=func.now(), onupdate=utcnow, nullable=False
    )
