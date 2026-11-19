"""Driver settlement workflow (U20).

Revision ID: 0028_settlement_workflow
Revises: 0027_statement_imports
Create Date: 2026-11-19

Adds the REVIEWED and PAID steps around the existing approval (FINALIZED),
with who reviewed and who recorded the payment. Existing settlements keep
their status; a FINALIZED one is still approved and simply has no payment
recorded. Paid settlements stay in the no-overlap rule.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_settlement_workflow"
down_revision: str | None = "0027_statement_imports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "driver_settlements"
STATUS = "ck_driver_settlements_settlement_status"
METHODS = "'CASH', 'CARD', 'BANK_TRANSFER', 'WALLET', 'PLATFORM', 'OTHER'"


def _overlap(where: str) -> None:
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT ex_driver_settlements_overlap")
    op.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT ex_driver_settlements_overlap "
        "EXCLUDE USING gist (driver_id WITH =, "
        "daterange(period_start, period_end, '[]') WITH &&) "
        f"WHERE ({where})"
    )


def upgrade() -> None:
    for name in ("reviewed_by_id", "paid_by_id"):
        op.add_column(TABLE, sa.Column(name, sa.Uuid(), nullable=True))
        op.create_foreign_key(op.f(f"fk_{TABLE}_{name}_users"), TABLE, "users", [name], ["id"])
    op.add_column(TABLE, sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("paid_on", sa.Date(), nullable=True))
    op.add_column(TABLE, sa.Column("paid_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column(TABLE, sa.Column("payment_method", sa.String(length=32), nullable=True))
    op.add_column(TABLE, sa.Column("payment_reference", sa.String(length=100), nullable=True))
    op.create_check_constraint(
        op.f("ck_driver_settlements_payment_method"), TABLE, f"payment_method IN ({METHODS})"
    )
    op.create_check_constraint(
        op.f("ck_driver_settlements_paid_amount_positive"),
        TABLE,
        "paid_amount IS NULL OR paid_amount > 0",
    )
    op.drop_constraint(op.f(STATUS), TABLE, type_="check")
    op.create_check_constraint(
        op.f(STATUS),
        TABLE,
        "status IN ('DRAFT', 'REVIEWED', 'FINALIZED', 'PAID', 'VOIDED')",
    )
    _overlap("status IN ('FINALIZED', 'PAID')")


def downgrade() -> None:
    # A paid settlement is still an approved one; a reviewed one goes back to draft.
    op.execute(f"UPDATE {TABLE} SET status = 'FINALIZED' WHERE status = 'PAID'")
    op.execute(f"UPDATE {TABLE} SET status = 'DRAFT' WHERE status = 'REVIEWED'")
    _overlap("status = 'FINALIZED'")
    op.drop_constraint(op.f(STATUS), TABLE, type_="check")
    op.create_check_constraint(op.f(STATUS), TABLE, "status IN ('DRAFT', 'FINALIZED', 'VOIDED')")
    op.drop_constraint(op.f("ck_driver_settlements_paid_amount_positive"), TABLE, type_="check")
    op.drop_constraint(op.f("ck_driver_settlements_payment_method"), TABLE, type_="check")
    for name in ("payment_reference", "payment_method", "paid_amount", "paid_on", "paid_at"):
        op.drop_column(TABLE, name)
    op.drop_column(TABLE, "reviewed_at")
    for name in ("paid_by_id", "reviewed_by_id"):
        op.drop_constraint(op.f(f"fk_{TABLE}_{name}_users"), TABLE, type_="foreignkey")
        op.drop_column(TABLE, name)
