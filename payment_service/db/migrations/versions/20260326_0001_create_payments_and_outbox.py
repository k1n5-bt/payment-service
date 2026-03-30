"""create payments and outbox

Revision ID: 20260326_0001
Revises:
Create Date: 2026-03-26 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '20260326_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    payment_status_enum = postgresql.ENUM('pending', 'succeeded', 'failed', name='payment_status_enum')
    currency_enum = postgresql.ENUM('RUB', 'USD', 'EUR', name='currency_enum')
    payment_status_enum.create(op.get_bind(), checkfirst=True)
    currency_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'payments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', currency_enum, nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', payment_status_enum, nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('webhook_url', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('idempotency_key', name='uq_payments_idempotency_key'),
    )

    op.create_table(
        'outbox',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('event_name', sa.String(length=120), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('published', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('outbox')
    op.drop_table('payments')
    op.execute('DROP TYPE IF EXISTS payment_status_enum')
    op.execute('DROP TYPE IF EXISTS currency_enum')
