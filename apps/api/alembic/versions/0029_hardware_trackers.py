"""Hardware GPS tracker ingestion (U05).

Revision ID: 0029_hardware_trackers
Revises: 0028_settlement_workflow
Create Date: 2026-11-23

Provider-neutral tables for a future vehicle tracker: devices, their vehicle
bindings over time, every raw event received (accepted or quarantined) and
normalised locations. No data: no tracker is in use yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_hardware_trackers"
down_revision: str | None = "0028_settlement_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tracker_devices",
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tracker_devices")),
        sa.UniqueConstraint("provider", "external_id", name="uq_tracker_devices_ref"),
    )
    op.create_table(
        "tracker_raw_events",
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_event_id", sa.String(length=120), nullable=False),
        sa.Column("device_external_id", sa.String(length=100), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACCEPTED",
                "QUARANTINED",
                name="tracker_event_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=40), nullable=True),
        sa.Column("reprocessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tracker_raw_events")),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_tracker_raw_events_ref"),
    )
    op.create_index(
        "ix_tracker_raw_events_status",
        "tracker_raw_events",
        ["status", "received_at"],
        unique=False,
    )
    op.create_table(
        "tracker_bindings",
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at", name=op.f("ck_tracker_bindings_binding_range")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_tracker_bindings_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["tracker_devices.id"],
            name=op.f("fk_tracker_bindings_device_id_tracker_devices"),
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"], ["vehicles.id"], name=op.f("fk_tracker_bindings_vehicle_id_vehicles")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tracker_bindings")),
    )
    op.create_index(
        "ix_tracker_bindings_device", "tracker_bindings", ["device_id", "starts_at"], unique=False
    )
    op.create_table(
        "tracker_locations",
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("raw_event_id", sa.UUID(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("speed_mps", sa.Float(), nullable=True),
        sa.Column("heading_deg", sa.Float(), nullable=True),
        sa.Column("ignition_on", sa.Boolean(), nullable=True),
        sa.Column("external_power", sa.Boolean(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["tracker_devices.id"],
            name=op.f("fk_tracker_locations_device_id_tracker_devices"),
        ),
        sa.ForeignKeyConstraint(
            ["raw_event_id"],
            ["tracker_raw_events.id"],
            name=op.f("fk_tracker_locations_raw_event_id_tracker_raw_events"),
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"], ["vehicles.id"], name=op.f("fk_tracker_locations_vehicle_id_vehicles")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tracker_locations")),
    )
    op.create_index(
        "ix_tracker_locations_recorded_brin",
        "tracker_locations",
        ["recorded_at"],
        unique=False,
        postgresql_using="brin",
    )
    op.create_index(
        "ix_tracker_locations_vehicle",
        "tracker_locations",
        ["vehicle_id", "recorded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tracker_locations_vehicle", table_name="tracker_locations")
    op.drop_index(
        "ix_tracker_locations_recorded_brin",
        table_name="tracker_locations",
        postgresql_using="brin",
    )
    op.drop_table("tracker_locations")
    op.drop_index("ix_tracker_bindings_device", table_name="tracker_bindings")
    op.drop_table("tracker_bindings")
    op.drop_index("ix_tracker_raw_events_status", table_name="tracker_raw_events")
    op.drop_table("tracker_raw_events")
    op.drop_table("tracker_devices")
