"""School run verification: late/incomplete outcomes and evidence (U12).

Revision ID: 0016_school_run_verification
Revises: 0015_route_revenue_rates
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_school_run_verification"
down_revision: str | None = "0015_route_revenue_rates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = ("SCHEDULED", "IN_PROGRESS", "COMPLETED", "COMPLETED_UNVERIFIED", "MISSED", "CANCELLED")
NEW = (*OLD, "COMPLETED_LATE", "INCOMPLETE")
NAME = "ck_school_runs_school_run_status"


def _check(values: tuple[str, ...]) -> str:
    return "status IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "school_runs",
        sa.Column("verification", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.drop_constraint(op.f(NAME), "school_runs", type_="check")
    op.create_check_constraint(op.f(NAME), "school_runs", _check(NEW))


def downgrade() -> None:
    """Downgrade schema."""
    # The old schema has no late/incomplete outcome: both become "needs review".
    op.execute(
        "UPDATE school_runs SET status = 'COMPLETED_UNVERIFIED' "
        "WHERE status IN ('COMPLETED_LATE', 'INCOMPLETE')"
    )
    op.drop_constraint(op.f(NAME), "school_runs", type_="check")
    op.create_check_constraint(op.f(NAME), "school_runs", _check(OLD))
    op.drop_column("school_runs", "verification")
