"""Road geometry cache for routes (U07).

Revision ID: 0030_route_geometries
Revises: 0029_hardware_trackers
Create Date: 2026-11-23

Geometry answers from a routing provider, per route version. Empty until a
provider is configured; straight lines are never stored here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_route_geometries"
down_revision: str | None = "0029_hardware_trackers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "route_geometries",
        sa.Column("route_id", sa.UUID(), nullable=False),
        sa.Column("route_version", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("points", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("distance_m", sa.Double(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["route_definitions.id"],
            name=op.f("fk_route_geometries_route_id_route_definitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_route_geometries")),
    )
    op.create_index(
        "uq_route_geometries_route_version_provider",
        "route_geometries",
        ["route_id", "route_version", "provider"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_route_geometries_route_version_provider", table_name="route_geometries")
    op.drop_table("route_geometries")
