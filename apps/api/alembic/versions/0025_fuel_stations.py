"""Fuel stations and vendors (U16).

Revision ID: 0025_fuel_stations
Revises: 0024_route_versions
Create Date: 2026-11-17

A station master table and an optional link from each purchase. Existing
purchases keep their free-text vendor and no station: nothing is guessed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_fuel_stations"
down_revision: str | None = "0024_route_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fuel_stations",
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("brand", sa.String(length=80), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("latitude", sa.Double(), nullable=True),
        sa.Column("longitude", sa.Double(), nullable=True),
        sa.Column("radius_m", sa.Integer(), server_default=sa.text("150"), nullable=False),
        sa.Column("is_trusted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name=op.f("ck_fuel_stations_location_complete"),
        ),
        sa.CheckConstraint(
            "NOT is_trusted OR latitude IS NOT NULL",
            name=op.f("ck_fuel_stations_trusted_has_location"),
        ),
        sa.CheckConstraint(
            "radius_m BETWEEN 20 AND 5000", name=op.f("ck_fuel_stations_radius_range")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fuel_stations")),
    )
    op.create_table(
        "fuel_station_fuel_types",
        sa.Column("station_id", sa.UUID(), nullable=False),
        sa.Column("fuel_type_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fuel_type_id"],
            ["fuel_types.id"],
            name=op.f("fk_fuel_station_fuel_types_fuel_type_id_fuel_types"),
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["fuel_stations.id"],
            name=op.f("fk_fuel_station_fuel_types_station_id_fuel_stations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "station_id", "fuel_type_id", name=op.f("pk_fuel_station_fuel_types")
        ),
    )
    op.add_column("fuel_transactions", sa.Column("station_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_fuel_transactions_station",
        "fuel_transactions",
        ["station_id", "occurred_at"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_fuel_transactions_station_id_fuel_stations"),
        "fuel_transactions",
        "fuel_stations",
        ["station_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_fuel_transactions_station_id_fuel_stations"),
        "fuel_transactions",
        type_="foreignkey",
    )
    op.drop_index("ix_fuel_transactions_station", table_name="fuel_transactions")
    op.drop_column("fuel_transactions", "station_id")
    op.drop_table("fuel_station_fuel_types")
    op.drop_table("fuel_stations")
