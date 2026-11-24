"""Route versioning (U08).

Revision ID: 0024_route_versions
Revises: 0023_severity_info
Create Date: 2026-11-10

Existing routes get version 1 from their current definition (effective
from when the route was created), and existing route events are linked to
it: that is the only definition the system has ever known for them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_route_versions"
down_revision: str | None = "0023_severity_info"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "route_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["route_id"], ["route_definitions.id"], name=op.f("fk_route_versions_route_id_route_definitions")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_route_versions_created_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_route_versions")),
    )
    op.create_index(
        "uq_route_versions_route_version", "route_versions", ["route_id", "version"], unique=True
    )
    op.add_column("route_events", sa.Column("route_version", sa.Integer(), nullable=True))
    op.execute(
        """
        INSERT INTO route_versions (id, route_id, version, effective_from, snapshot)
        SELECT gen_random_uuid(), r.id, 1, r.created_at,
          jsonb_build_object(
            'name', r.name,
            'trip_pattern', r.trip_pattern,
            'expected_distance_km', r.expected_distance_km,
            'expected_duration_minutes', r.expected_duration_minutes,
            'window_start', r.window_start,
            'window_end', r.window_end,
            'operating_days', to_jsonb(r.operating_days),
            'stops', COALESCE((
              SELECT jsonb_agg(jsonb_build_object(
                'id', s.id, 'sequence', s.sequence, 'kind', s.kind, 'name', s.name,
                'latitude', s.latitude, 'longitude', s.longitude, 'radius_m', s.radius_m
              ) ORDER BY s.sequence)
              FROM route_stops s WHERE s.route_id = r.id
            ), '[]'::jsonb)
          )
        FROM route_definitions r
        """
    )
    op.execute("UPDATE route_events SET route_version = 1")


def downgrade() -> None:
    op.drop_column("route_events", "route_version")
    op.drop_index("uq_route_versions_route_version", table_name="route_versions")
    op.drop_table("route_versions")
