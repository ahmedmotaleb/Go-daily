"""Re-authentication for sensitive actions (U35).

Revision ID: 0022_session_reauth
Revises: 0021_policy_versions
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_session_reauth"
down_revision: str | None = "0021_policy_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions", sa.Column("reauthenticated_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("auth_sessions", "reauthenticated_at")
