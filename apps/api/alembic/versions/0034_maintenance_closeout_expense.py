"""A maintenance record can name the close-out expense it covers.

Revision ID: 0034_maint_closeout_expense
Revises: 0033_closeout_rh_amount
Create Date: 2026-11-28

A driver's close-out books a maintenance line as an expense; the office may
also enter a maintenance record for the same job. Profitability counted both.
The record now names that expense, and profitability counts the job once
(security audit M11). Null on existing records.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_maint_closeout_expense"
down_revision: str | None = "0033_closeout_rh_amount"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "maintenance_records",
        sa.Column("closeout_expense_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_maintenance_records_closeout_expense_id_expenses"),
        "maintenance_records",
        "expenses",
        ["closeout_expense_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_maintenance_records_closeout_expense_id_expenses"),
        "maintenance_records",
        type_="foreignkey",
    )
    op.drop_column("maintenance_records", "closeout_expense_id")
