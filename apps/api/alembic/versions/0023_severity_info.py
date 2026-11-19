"""INFO severity for review cases (U27).

Revision ID: 0023_severity_info
Revises: 0022_session_reauth
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023_severity_info"
down_revision: str | None = "0022_session_reauth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME = "ck_operational_exceptions_exception_severity"


def upgrade() -> None:
    op.drop_constraint(op.f(NAME), "operational_exceptions", type_="check")
    op.create_check_constraint(
        op.f(NAME), "operational_exceptions", "severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH')"
    )


def downgrade() -> None:
    op.execute("UPDATE operational_exceptions SET severity = 'LOW' WHERE severity = 'INFO'")
    op.drop_constraint(op.f(NAME), "operational_exceptions", type_="check")
    op.create_check_constraint(
        op.f(NAME), "operational_exceptions", "severity IN ('LOW', 'MEDIUM', 'HIGH')"
    )
