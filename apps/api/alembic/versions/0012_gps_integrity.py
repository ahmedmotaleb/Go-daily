"""Integrity evidence on GPS upload batches (U02).

Revision ID: 0012_gps_integrity
Revises: 0011_notifications
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_gps_integrity"
down_revision: str | None = "0011_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("gps_upload_batches") as t:
        t.add_column(sa.Column("device_time", sa.DateTime(timezone=True), nullable=True))
        t.add_column(sa.Column("first_recorded_at", sa.DateTime(timezone=True), nullable=True))
        t.add_column(sa.Column("last_recorded_at", sa.DateTime(timezone=True), nullable=True))
        t.add_column(
            sa.Column(
                "rejected_outside_shift", sa.Integer(), server_default=sa.text("0"), nullable=False
            )
        )
        t.add_column(
            sa.Column("outside_shift_first_at", sa.DateTime(timezone=True), nullable=True)
        )
        t.add_column(sa.Column("outside_shift_last_at", sa.DateTime(timezone=True), nullable=True))
        t.add_column(
            sa.Column("rejected_future", sa.Integer(), server_default=sa.text("0"), nullable=False)
        )
        t.add_column(sa.Column("future_max_seconds", sa.Integer(), nullable=True))
    op.create_index(
        "ix_gps_batches_shift_received",
        "gps_upload_batches",
        ["shift_id", "received_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_gps_batches_shift_received", table_name="gps_upload_batches")
    with op.batch_alter_table("gps_upload_batches") as t:
        for name in (
            "future_max_seconds",
            "rejected_future",
            "outside_shift_last_at",
            "outside_shift_first_at",
            "rejected_outside_shift",
            "last_recorded_at",
            "first_recorded_at",
            "device_time",
        ):
            t.drop_column(name)
