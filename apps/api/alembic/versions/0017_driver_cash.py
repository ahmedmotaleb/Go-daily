"""Driver workflows: day-offs, odometer start photo, close-outs and cash collections.

Revision ID: 0017_driver_cash
Revises: 0016_school_run_verification
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_driver_cash"
down_revision: str | None = "0016_school_run_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNERS_OLD = (
    "fuel_transaction",
    "expense",
    "revenue_entry",
    "ride_hailing_statement",
    "maintenance_record",
    "vehicle",
)
OWNERS_NEW = (*OWNERS_OLD, "shift", "shift_closeout", "driver")
KINDS_OLD = (
    "FUEL_RECEIPT",
    "EXPENSE_RECEIPT",
    "REVENUE_DOCUMENT",
    "PLATFORM_STATEMENT",
    "MAINTENANCE_INVOICE",
    "VEHICLE_DOCUMENT",
    "OTHER",
)
KINDS_NEW = (*KINDS_OLD, "ODOMETER_PHOTO")
SOURCES_OLD = ("MANUAL", "SETTLEMENT", "EXPENSE", "FUEL", "REVENUE_RECEIPT")
SOURCES_NEW = (*SOURCES_OLD, "CASH_COLLECTION")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _replace_check(table: str, name: str, condition: str) -> None:
    op.drop_constraint(op.f(name), table, type_="check")
    op.create_check_constraint(op.f(name), table, condition)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "driver_day_offs",
        sa.Column("driver_id", sa.UUID(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column(
            "source",
            sa.Enum(
                "ADMIN",
                "DRIVER_APP",
                "SYSTEM",
                name="record_source",
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
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_id", sa.UUID(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=300), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["cancelled_by_id"], ["users.id"], name=op.f("fk_driver_day_offs_cancelled_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_driver_day_offs_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["driver_id"], ["drivers.id"], name=op.f("fk_driver_day_offs_driver_id_drivers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_driver_day_offs")),
    )
    op.create_index("ix_driver_day_offs_day", "driver_day_offs", ["day"], unique=False)
    op.create_index(
        "uq_driver_day_offs_live",
        "driver_day_offs",
        ["driver_id", "day"],
        unique=True,
        postgresql_where=sa.text("cancelled_at IS NULL"),
    )
    op.create_table(
        "shift_closeouts",
        sa.Column("shift_id", sa.UUID(), nullable=False),
        sa.Column("driver_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "ADMIN",
                "DRIVER_APP",
                "SYSTEM",
                name="record_source",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("end_odometer_km", sa.Integer(), nullable=False),
        sa.Column("collection_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("gas_quantity", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column(
            "gas_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("gasoline_quantity", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column(
            "gasoline_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "toll_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "maintenance_kind",
            sa.Enum(
                "NONE",
                "OIL_CHANGE",
                "MAINTENANCE",
                name="maintenance_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "maintenance_amount",
            sa.Numeric(precision=14, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("maintenance_note", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("revenue_entry_id", sa.UUID(), nullable=True),
        sa.Column("gas_fuel_id", sa.UUID(), nullable=True),
        sa.Column("gasoline_fuel_id", sa.UUID(), nullable=True),
        sa.Column("toll_expense_id", sa.UUID(), nullable=True),
        sa.Column("maintenance_expense_id", sa.UUID(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by_id", sa.UUID(), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "(maintenance_kind = 'NONE' AND maintenance_amount = 0) OR "
            "(maintenance_kind <> 'NONE' AND maintenance_amount > 0 "
            "AND maintenance_note IS NOT NULL AND length(trim(maintenance_note)) > 0)",
            name=op.f("ck_shift_closeouts_maintenance_complete"),
        ),
        sa.CheckConstraint(
            "collection_amount >= 0 AND gas_amount >= 0 AND gasoline_amount >= 0 "
            "AND toll_amount >= 0 AND maintenance_amount >= 0",
            name=op.f("ck_shift_closeouts_amounts_non_negative"),
        ),
        sa.CheckConstraint(
            "end_odometer_km >= 0", name=op.f("ck_shift_closeouts_odometer_non_negative")
        ),
        sa.CheckConstraint(
            "gas_amount = 0 OR (gas_quantity IS NOT NULL AND gas_quantity > 0)",
            name=op.f("ck_shift_closeouts_gas_quantity_required"),
        ),
        sa.CheckConstraint(
            "gasoline_amount = 0 OR (gasoline_quantity IS NOT NULL AND gasoline_quantity > 0)",
            name=op.f("ck_shift_closeouts_gasoline_quantity_required"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_shift_closeouts_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["driver_id"], ["drivers.id"], name=op.f("fk_shift_closeouts_driver_id_drivers")
        ),
        sa.ForeignKeyConstraint(
            ["gas_fuel_id"],
            ["fuel_transactions.id"],
            name=op.f("fk_shift_closeouts_gas_fuel_id_fuel_transactions"),
        ),
        sa.ForeignKeyConstraint(
            ["gasoline_fuel_id"],
            ["fuel_transactions.id"],
            name=op.f("fk_shift_closeouts_gasoline_fuel_id_fuel_transactions"),
        ),
        sa.ForeignKeyConstraint(
            ["maintenance_expense_id"],
            ["expenses.id"],
            name=op.f("fk_shift_closeouts_maintenance_expense_id_expenses"),
        ),
        sa.ForeignKeyConstraint(
            ["revenue_entry_id"],
            ["revenue_entries.id"],
            name=op.f("fk_shift_closeouts_revenue_entry_id_revenue_entries"),
        ),
        sa.ForeignKeyConstraint(
            ["shift_id"], ["shifts.id"], name=op.f("fk_shift_closeouts_shift_id_shifts")
        ),
        sa.ForeignKeyConstraint(
            ["toll_expense_id"],
            ["expenses.id"],
            name=op.f("fk_shift_closeouts_toll_expense_id_expenses"),
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"], ["vehicles.id"], name=op.f("fk_shift_closeouts_vehicle_id_vehicles")
        ),
        sa.ForeignKeyConstraint(
            ["voided_by_id"], ["users.id"], name=op.f("fk_shift_closeouts_voided_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shift_closeouts")),
    )
    op.create_index("ix_shift_closeouts_day", "shift_closeouts", ["service_date"], unique=False)
    op.create_index(
        "ix_shift_closeouts_driver", "shift_closeouts", ["driver_id", "service_date"], unique=False
    )
    op.create_index(
        "uq_shift_closeouts_live",
        "shift_closeouts",
        ["shift_id"],
        unique=True,
        postgresql_where=sa.text("voided_at IS NULL"),
    )
    op.create_table(
        "cash_collections",
        sa.Column("driver_id", sa.UUID(), nullable=False),
        sa.Column("closeout_id", sa.UUID(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("collected_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by_id", sa.UUID(), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("amount > 0", name=op.f("ck_cash_collections_amount_positive")),
        sa.ForeignKeyConstraint(
            ["closeout_id"],
            ["shift_closeouts.id"],
            name=op.f("fk_cash_collections_closeout_id_shift_closeouts"),
        ),
        sa.ForeignKeyConstraint(
            ["collected_by_id"],
            ["users.id"],
            name=op.f("fk_cash_collections_collected_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["driver_id"], ["drivers.id"], name=op.f("fk_cash_collections_driver_id_drivers")
        ),
        sa.ForeignKeyConstraint(
            ["voided_by_id"], ["users.id"], name=op.f("fk_cash_collections_voided_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cash_collections")),
    )
    op.create_index(
        "ix_cash_collections_closeout", "cash_collections", ["closeout_id"], unique=False
    )
    op.create_index(
        "ix_cash_collections_driver",
        "cash_collections",
        ["driver_id", "collected_at"],
        unique=False,
    )
    op.add_column("shifts", sa.Column("start_odometer_photo_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_shifts_start_odometer_photo_id_attachments"),
        "shifts",
        "attachments",
        ["start_odometer_photo_id"],
        ["id"],
    )
    _replace_check("attachments", "ck_attachments_attachment_owner", _in("owner_type", OWNERS_NEW))
    _replace_check("attachments", "ck_attachments_attachment_kind", _in("kind", KINDS_NEW))
    _replace_check(
        "driver_ledger_entries",
        "ck_driver_ledger_entries_ledger_source",
        _in("source_type", SOURCES_NEW),
    )
    # «تغيير زيت» from the close-out is its own maintenance expense category.
    op.execute(
        "INSERT INTO expense_categories (id, code, name_ar, pnl_group, is_active, sort_order) "
        "VALUES (gen_random_uuid(), 'OIL_CHANGE', 'تغيير زيت', 'MAINTENANCE', true, 9) "
        "ON CONFLICT (code) DO NOTHING"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Rows that only exist for the new workflows have no meaning in the old schema.
    op.execute("DELETE FROM driver_ledger_entries WHERE source_type = 'CASH_COLLECTION'")
    op.execute(
        "DELETE FROM attachments WHERE owner_type IN ('shift', 'shift_closeout', 'driver') "
        "OR kind = 'ODOMETER_PHOTO'"
    )
    _replace_check(
        "driver_ledger_entries",
        "ck_driver_ledger_entries_ledger_source",
        _in("source_type", SOURCES_OLD),
    )
    _replace_check("attachments", "ck_attachments_attachment_kind", _in("kind", KINDS_OLD))
    _replace_check("attachments", "ck_attachments_attachment_owner", _in("owner_type", OWNERS_OLD))
    # The category stays if expenses use it (history is never deleted).
    op.execute(
        "DELETE FROM expense_categories WHERE code = 'OIL_CHANGE' "
        "AND NOT EXISTS (SELECT 1 FROM expenses e WHERE e.category_id = expense_categories.id)"
    )
    op.drop_constraint(
        op.f("fk_shifts_start_odometer_photo_id_attachments"), "shifts", type_="foreignkey"
    )
    op.drop_column("shifts", "start_odometer_photo_id")
    op.drop_index("ix_cash_collections_driver", table_name="cash_collections")
    op.drop_index("ix_cash_collections_closeout", table_name="cash_collections")
    op.drop_table("cash_collections")
    op.drop_index(
        "uq_shift_closeouts_live",
        table_name="shift_closeouts",
        postgresql_where=sa.text("voided_at IS NULL"),
    )
    op.drop_index("ix_shift_closeouts_driver", table_name="shift_closeouts")
    op.drop_index("ix_shift_closeouts_day", table_name="shift_closeouts")
    op.drop_table("shift_closeouts")
    op.drop_index(
        "uq_driver_day_offs_live",
        table_name="driver_day_offs",
        postgresql_where=sa.text("cancelled_at IS NULL"),
    )
    op.drop_index("ix_driver_day_offs_day", table_name="driver_day_offs")
    op.drop_table("driver_day_offs")
