"""Leg evidence and incomplete/rejected legs on route events (U09).

Revision ID: 0014_route_leg_evidence
Revises: 0013_original_odometer
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_route_leg_evidence"
down_revision: str | None = "0013_original_odometer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = (
    "ENTERED",
    "EXITED",
    "REACHED_ORIGIN",
    "REACHED_DESTINATION",
    "LEG_COMPLETED",
    "LOOP_COMPLETED",
)
NEW = (*OLD, "LEG_INCOMPLETE", "LEG_REJECTED")


def _check(values: tuple[str, ...]) -> str:
    return "event_type IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "route_events",
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.drop_constraint(op.f("ck_route_events_route_event_type"), "route_events", type_="check")
    op.create_check_constraint(
        op.f("ck_route_events_route_event_type"), "route_events", _check(NEW)
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Evidence-only rows have no meaning for the old schema.
    op.execute("DELETE FROM route_events WHERE event_type IN ('LEG_INCOMPLETE', 'LEG_REJECTED')")
    op.drop_constraint(op.f("ck_route_events_route_event_type"), "route_events", type_="check")
    op.create_check_constraint(
        op.f("ck_route_events_route_event_type"), "route_events", _check(OLD)
    )
    op.drop_column("route_events", "details")
