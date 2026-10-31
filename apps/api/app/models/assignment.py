"""Driver <-> vehicle assignment history.

Assignments describe who is responsible for a vehicle over a period. They
are never deleted; a new assignment ends the previous one. Overlapping
PRIMARY assignments for the same vehicle or the same driver are rejected
by an exclusion constraint (see migration 0003). RELIEF assignments (a
backup/second-shift driver) may overlap.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column_type
from app.models.driver import Driver
from app.models.fleet import Vehicle


class AssignmentRole(StrEnum):
    PRIMARY = "PRIMARY"  # السائق الأساسي
    RELIEF = "RELIEF"  # سائق بديل / وردية ثانية


class DriverVehicleAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "driver_vehicle_assignments"

    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    role: Mapped[AssignmentRole] = mapped_column(
        enum_column_type(AssignmentRole, "assignment_role"), default=AssignmentRole.PRIMARY
    )
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime | None]
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ended_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    driver: Mapped[Driver] = relationship(lazy="joined")
    vehicle: Mapped[Vehicle] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="ends_after_start"),
        # No two overlapping PRIMARY assignments per vehicle or per driver.
        ExcludeConstraint(
            ("vehicle_id", "="),
            (func.tstzrange(text("starts_at"), text("ends_at")), "&&"),
            name="ex_assignments_vehicle_primary_overlap",
            using="gist",
            where=text("role = 'PRIMARY'"),
        ),
        ExcludeConstraint(
            ("driver_id", "="),
            (func.tstzrange(text("starts_at"), text("ends_at")), "&&"),
            name="ex_assignments_driver_primary_overlap",
            using="gist",
            where=text("role = 'PRIMARY'"),
        ),
        Index("ix_assignments_driver", "driver_id", "starts_at"),
        Index("ix_assignments_vehicle", "vehicle_id", "starts_at"),
    )

    def is_active_at(self, at: datetime) -> bool:
        return self.starts_at <= at and (self.ends_at is None or self.ends_at > at)
