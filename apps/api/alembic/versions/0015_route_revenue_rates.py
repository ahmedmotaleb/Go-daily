"""Expected revenue rates per fixed route, versioned by date (U10).

Revision ID: 0015_route_revenue_rates
Revises: 0014_route_leg_evidence
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_route_revenue_rates"
down_revision: str | None = "0014_route_leg_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('route_revenue_rates',
    sa.Column('route_id', sa.UUID(), nullable=False),
    sa.Column('model', sa.Enum('PER_LOOP', 'PER_LEG', 'PASSENGERS_X_FARE', name='expected_revenue_model', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('amount_per_loop', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('amount_per_leg', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('fare', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('passengers_per_leg', sa.Integer(), nullable=True),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(model <> 'PER_LOOP' OR amount_per_loop > 0) AND (model <> 'PER_LEG' OR amount_per_leg > 0) AND (model <> 'PASSENGERS_X_FARE' OR (fare > 0 AND passengers_per_leg > 0))", name=op.f('ck_route_revenue_rates_model_amounts')),
    sa.CheckConstraint('effective_to IS NULL OR effective_to >= effective_from', name=op.f('ck_route_revenue_rates_effective_range')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_route_revenue_rates_created_by_id_users')),
    sa.ForeignKeyConstraint(['route_id'], ['route_definitions.id'], name=op.f('fk_route_revenue_rates_route_id_route_definitions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_route_revenue_rates'))
    )
    op.create_index('uq_route_revenue_rates_start', 'route_revenue_rates', ['route_id', 'effective_from'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_route_revenue_rates_start', table_name='route_revenue_rates')
    op.drop_table('route_revenue_rates')
