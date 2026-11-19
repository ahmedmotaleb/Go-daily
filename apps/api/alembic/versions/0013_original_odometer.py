"""Keep shifts' first-entered odometer readings when corrected (U04).

Revision ID: 0013_original_odometer
Revises: 0012_gps_integrity
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_original_odometer"
down_revision: str | None = "0012_gps_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("shifts", sa.Column("original_start_odometer_km", sa.Integer(), nullable=True))
    op.add_column("shifts", sa.Column("original_end_odometer_km", sa.Integer(), nullable=True))
    # Recover the originals of shifts corrected before this column existed,
    # from the first correction's audit entry ("old" value).
    for field in ("start_odometer_km", "end_odometer_km"):
        op.execute(
            sa.text(
                f"""
                UPDATE shifts AS s
                SET original_{field} = first.old_value
                FROM (
                    SELECT DISTINCT ON (entity_id)
                        entity_id, (changes -> '{field}' ->> 'old')::integer AS old_value
                    FROM audit_logs
                    WHERE action = 'shift.odometer_corrected'
                      AND entity_type = 'shift'
                      AND changes ? '{field}'
                    ORDER BY entity_id, occurred_at
                ) AS first
                WHERE s.id::text = first.entity_id
                """  # noqa: S608 - field comes from the fixed tuple above
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("shifts", "original_end_odometer_km")
    op.drop_column("shifts", "original_start_odometer_km")
