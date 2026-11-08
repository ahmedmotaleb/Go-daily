"""Versioned company policies (U47).

Revision ID: 0021_policy_versions
Revises: 0020_two_factor
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_policy_versions"
down_revision: str | None = "0020_two_factor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_policy_versions_created_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_versions")),
        sa.UniqueConstraint("version", name=op.f("uq_policy_versions_version")),
    )


def downgrade() -> None:
    op.drop_table("policy_versions")
