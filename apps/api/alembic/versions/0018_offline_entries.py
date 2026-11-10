"""Offline financial entries: client entry ids and device times (U45/U46).

Revision ID: 0018_offline_entries
Revises: 0017_driver_cash
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_offline_entries"
down_revision: str | None = "0017_driver_cash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("fuel_transactions", "shift_closeouts"):
        op.add_column(table, sa.Column("client_entry_id", sa.String(length=64), nullable=True))
        op.add_column(
            table, sa.Column("device_recorded_at", sa.DateTime(timezone=True), nullable=True)
        )
    # A queued entry sent twice (lost response, long offline) is recognised by
    # its client id, for as long as the record exists.
    op.create_index(
        "uq_fuel_transactions_client_entry",
        "fuel_transactions",
        ["driver_id", "client_entry_id"],
        unique=True,
        postgresql_where=sa.text("client_entry_id IS NOT NULL"),
    )
    op.create_index(
        "uq_shift_closeouts_client_entry",
        "shift_closeouts",
        ["driver_id", "client_entry_id"],
        unique=True,
        postgresql_where=sa.text("client_entry_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_shift_closeouts_client_entry", table_name="shift_closeouts")
    op.drop_index("uq_fuel_transactions_client_entry", table_name="fuel_transactions")
    for table in ("fuel_transactions", "shift_closeouts"):
        op.drop_column(table, "device_recorded_at")
        op.drop_column(table, "client_entry_id")
