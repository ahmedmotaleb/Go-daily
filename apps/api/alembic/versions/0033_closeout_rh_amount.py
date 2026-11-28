"""Close-outs record the ride-hailing part of the cash collected.

Revision ID: 0033_closeout_rh_amount
Revises: 0032_route_stop_soft_delete
Create Date: 2026-11-28

A shift can mix a fixed route and ride-hailing. Ride-hailing revenue comes
only from the platform statement, so the close-out must say how much of the
cash came from ride-hailing; only the rest is booked as revenue. Null on
existing close-outs (they were booked with the old single-kind rule).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_closeout_rh_amount"
down_revision: str | None = "0032_route_stop_soft_delete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "shift_closeouts",
        sa.Column("ride_hailing_amount", sa.Numeric(14, 2), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_shift_closeouts_ride_hailing_within_collection"),
        "shift_closeouts",
        "ride_hailing_amount IS NULL OR "
        "(ride_hailing_amount >= 0 AND ride_hailing_amount <= collection_amount)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_shift_closeouts_ride_hailing_within_collection"),
        "shift_closeouts",
        type_="check",
    )
    op.drop_column("shift_closeouts", "ride_hailing_amount")
