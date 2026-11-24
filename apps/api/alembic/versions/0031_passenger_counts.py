"""Passenger counts (U11).

Revision ID: 0031_passenger_counts
Revises: 0030_route_geometries
Create Date: 2026-11-23

Recorded counts with their source and confidence. No data: counts were
never recorded before, and none are inferred.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_passenger_counts"
down_revision: str | None = "0030_route_geometries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "passenger_counts",
        sa.Column("shift_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("route_id", sa.UUID(), nullable=True),
        sa.Column(
            "direction",
            sa.Enum(
                "OUTBOUND",
                "INBOUND",
                name="leg_direction",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("counted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("passengers", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "DRIVER",
                "SUPERVISOR",
                "TICKETING",
                "HARDWARE",
                name="count_source",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Enum(
                "COUNTED",
                "ESTIMATED",
                name="count_confidence",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
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
        sa.CheckConstraint(
            "passengers BETWEEN 0 AND 200", name=op.f("ck_passenger_counts_passengers_range")
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_id"], ["users.id"], name=op.f("fk_passenger_counts_recorded_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["route_definitions.id"],
            name=op.f("fk_passenger_counts_route_id_route_definitions"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["operation_sessions.id"],
            name=op.f("fk_passenger_counts_session_id_operation_sessions"),
        ),
        sa.ForeignKeyConstraint(
            ["shift_id"], ["shifts.id"], name=op.f("fk_passenger_counts_shift_id_shifts")
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"], ["vehicles.id"], name=op.f("fk_passenger_counts_vehicle_id_vehicles")
        ),
        sa.ForeignKeyConstraint(
            ["voided_by_id"], ["users.id"], name=op.f("fk_passenger_counts_voided_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passenger_counts")),
    )
    op.create_index(
        "ix_passenger_counts_route", "passenger_counts", ["route_id", "counted_at"], unique=False
    )
    op.create_index(
        "ix_passenger_counts_shift", "passenger_counts", ["shift_id", "counted_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_passenger_counts_shift", table_name="passenger_counts")
    op.drop_index("ix_passenger_counts_route", table_name="passenger_counts")
    op.drop_table("passenger_counts")
