"""Pilot vehicles (U50/U51).

Revision ID: 0019_pilot_vehicles
Revises: 0018_offline_entries
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_pilot_vehicles"
down_revision: str | None = "0018_offline_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vehicles",
        sa.Column("pilot", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("vehicles", "pilot")
