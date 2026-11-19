"""Ride-hailing statement CSV import (U19).

Revision ID: 0027_statement_imports
Revises: 0026_service_consumables
Create Date: 2026-11-19

Import batches, the batch and row of each imported statement, and the last
column mapping used per platform. Existing statements were entered by hand
and keep no batch.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_statement_imports"
down_revision: str | None = "0026_service_consumables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ride_hailing_import_batches",
        sa.Column("platform_id", sa.UUID(), nullable=False),
        sa.Column("file_name", sa.String(length=200), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rows_total", sa.Integer(), nullable=False),
        sa.Column("rows_imported", sa.Integer(), nullable=False),
        sa.Column("skipped", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "IMPORTED",
                "VOIDED",
                name="import_batch_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("voided_by_id", sa.UUID(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_ride_hailing_import_batches_created_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["platform_id"],
            ["ride_hailing_platforms.id"],
            name=op.f("fk_ride_hailing_import_batches_platform_id_ride_hailing_platforms"),
        ),
        sa.ForeignKeyConstraint(
            ["voided_by_id"],
            ["users.id"],
            name=op.f("fk_ride_hailing_import_batches_voided_by_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ride_hailing_import_batches")),
    )
    op.create_index(
        "uq_ride_hailing_import_batches_file",
        "ride_hailing_import_batches",
        ["platform_id", "file_sha256"],
        unique=True,
        postgresql_where=sa.text("status = 'IMPORTED'"),
    )
    op.add_column(
        "ride_hailing_platforms",
        sa.Column("import_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("ride_hailing_statements", sa.Column("import_batch_id", sa.UUID(), nullable=True))
    op.add_column("ride_hailing_statements", sa.Column("import_row", sa.Integer(), nullable=True))
    op.create_index(
        "ix_ride_hailing_statements_import_batch",
        "ride_hailing_statements",
        ["import_batch_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_ride_hailing_statements_import_batch_id_ride_hailing_import_batches"),
        "ride_hailing_statements",
        "ride_hailing_import_batches",
        ["import_batch_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_ride_hailing_statements_import_batch_id_ride_hailing_import_batches"),
        "ride_hailing_statements",
        type_="foreignkey",
    )
    op.drop_index("ix_ride_hailing_statements_import_batch", table_name="ride_hailing_statements")
    op.drop_column("ride_hailing_statements", "import_row")
    op.drop_column("ride_hailing_statements", "import_batch_id")
    op.drop_column("ride_hailing_platforms", "import_mapping")
    op.drop_index(
        "uq_ride_hailing_import_batches_file",
        table_name="ride_hailing_import_batches",
        postgresql_where=sa.text("status = 'IMPORTED'"),
    )
    op.drop_table("ride_hailing_import_batches")
