"""Oil and service reconciliation (U17).

Revision ID: 0026_service_consumables
Revises: 0025_fuel_stations
Create Date: 2026-11-17

Service types can name the consumable they use (the engine oil change uses
engine oil). Service records gain the quantity and grade put in and the next
targets decided at the service. Existing records keep these empty: the
quantities were never recorded, and their next targets keep being computed
from the intervals as before.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_service_consumables"
down_revision: str | None = "0025_fuel_stations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("maintenance_types", sa.Column("consumable_type_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_maintenance_types_consumable_type_id_fuel_types"),
        "maintenance_types",
        "fuel_types",
        ["consumable_type_id"],
        ["id"],
    )
    op.add_column(
        "maintenance_records",
        sa.Column("consumable_quantity", sa.Numeric(precision=14, scale=3), nullable=True),
    )
    op.add_column(
        "maintenance_records", sa.Column("consumable_spec", sa.String(length=80), nullable=True)
    )
    op.add_column("maintenance_records", sa.Column("next_due_km", sa.Integer(), nullable=True))
    op.add_column("maintenance_records", sa.Column("next_due_on", sa.Date(), nullable=True))
    op.create_check_constraint(
        op.f("ck_maintenance_records_consumable_quantity_positive"),
        "maintenance_records",
        "consumable_quantity IS NULL OR consumable_quantity > 0",
    )
    op.execute(
        "UPDATE maintenance_types SET consumable_type_id = "
        "(SELECT id FROM fuel_types WHERE code = 'ENGINE_OIL') "
        "WHERE code = 'ENGINE_OIL_CHANGE'"
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_maintenance_records_consumable_quantity_positive"),
        "maintenance_records",
        type_="check",
    )
    op.drop_column("maintenance_records", "next_due_on")
    op.drop_column("maintenance_records", "next_due_km")
    op.drop_column("maintenance_records", "consumable_spec")
    op.drop_column("maintenance_records", "consumable_quantity")
    op.drop_constraint(
        op.f("fk_maintenance_types_consumable_type_id_fuel_types"),
        "maintenance_types",
        type_="foreignkey",
    )
    op.drop_column("maintenance_types", "consumable_type_id")
