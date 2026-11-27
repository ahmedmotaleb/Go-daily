"""Route stops are never deleted: removed_at and a partial unique order index.

Revision ID: 0032_route_stop_soft_delete
Revises: 0031_passenger_counts
Create Date: 2026-11-26

Editing a route used to delete surplus stops, which fails once a route event
points at the stop and loses what the event referred to. A stop taken off a
route now gets `removed_at`; the order (route_id, sequence) is unique among
the current stops only. No data change: every existing stop is current.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_route_stop_soft_delete"
down_revision: str | None = "0031_passenger_counts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("route_stops", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_index("uq_route_stops_route_sequence", table_name="route_stops")
    op.create_index(
        "uq_route_stops_route_sequence",
        "route_stops",
        ["route_id", "sequence"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )


def downgrade() -> None:
    # Removed stops stay (route events reference them). They get negative,
    # distinct sequence numbers so the full unique index can be restored;
    # without removed_at they then read as current stops again.
    op.execute(
        """
        UPDATE route_stops AS s
           SET sequence = -r.n
          FROM (
                SELECT id, row_number() OVER (PARTITION BY route_id ORDER BY removed_at, sequence) AS n
                  FROM route_stops
                 WHERE removed_at IS NOT NULL
               ) AS r
         WHERE s.id = r.id
        """
    )
    op.drop_index(
        "uq_route_stops_route_sequence",
        table_name="route_stops",
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.create_index(
        "uq_route_stops_route_sequence", "route_stops", ["route_id", "sequence"], unique=True
    )
    op.drop_column("route_stops", "removed_at")
