"""Users carry must_change_password (opt-in forced change for driver accounts).

Revision ID: 0036_user_must_change_password
Revises: 0035_notification_permission
Create Date: 2026-11-28

With DRIVER_FORCE_PASSWORD_CHANGE on, a password set by staff for a driver
account must be changed by the driver before any driver-app write
(security audit L10). Existing users: false.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_user_must_change_password"
down_revision: str | None = "0035_notification_permission"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
