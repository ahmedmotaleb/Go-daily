"""Notifications record the permission they were sent under.

Revision ID: 0035_notification_permission
Revises: 0034_maint_closeout_expense
Create Date: 2026-11-28

The inbox only shows notices whose permission the user still holds, so a
user whose role is lowered stops seeing finance notices (security audit L8).
Existing rows are filled from their kind; money review cases get
revenue:read.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_notification_permission"
down_revision: str | None = "0034_maint_closeout_expense"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BY_KIND = {
    "VEHICLE_DOCUMENT": "vehicles:read",
    "DRIVER_LICENSE": "drivers:read",
    "MAINTENANCE_DUE": "maintenance:read",
    "TRACKING_INTERRUPTED": "tracking:read",
    "EXCEPTION": "exceptions:read",
    "ESCALATION": "exceptions:review",
    "PENDING_REVIEW": "expenses:approve",
}
MONEY_RULES = ("COLLECTION_GAP", "REVENUE_INCONSISTENT", "RIDE_HAILING_MISMATCH", "CASH_NOT_HANDED_OVER")


def upgrade() -> None:
    op.add_column("notifications", sa.Column("permission", sa.String(40), nullable=True))
    for kind, permission in BY_KIND.items():
        op.execute(
            sa.text("UPDATE notifications SET permission = :p WHERE kind = :k").bindparams(
                p=permission, k=kind
            )
        )
    op.execute(
        sa.text(
            "UPDATE notifications AS n SET permission = 'revenue:read' "
            "FROM operational_exceptions AS e "
            "WHERE n.kind IN ('EXCEPTION', 'ESCALATION') AND n.entity_id = e.id "
            "AND e.rule_code IN :rules"
        ).bindparams(sa.bindparam("rules", MONEY_RULES, expanding=True))
    )


def downgrade() -> None:
    op.drop_column("notifications", "permission")
