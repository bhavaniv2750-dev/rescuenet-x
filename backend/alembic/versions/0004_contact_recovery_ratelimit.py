"""S3: contact verification, password recovery, notification outbox and the shared rate-limit store

* users.email_verified_at / phone_verified_at / email_changed_at (all NULL: nothing existing is marked verified)
* users.must_change_password (default false)
* new tables one_time_tokens (hashed codes/reset tokens), notification_outbox (honest delivery status), rate_limit_events

No existing account is changed, disabled or marked verified. Downgrade drops the new tables and columns (pending codes, the
outbox and rate-limit counters are lost; nothing else).

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('notification_outbox',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('channel', sa.String(length=10), nullable=False),
    sa.Column('purpose', sa.String(length=30), nullable=False),
    sa.Column('recipient_masked', sa.String(length=120), nullable=False),
    sa.Column('transport', sa.String(length=20), nullable=False),
    sa.Column('delivery_status', sa.String(length=20), nullable=False),
    sa.Column('detail', sa.String(length=200), nullable=True),
    sa.Column('subject', sa.String(length=160), nullable=True),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notification_outbox', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notification_outbox_user_id'), ['user_id'], unique=False)

    op.create_table('one_time_tokens',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('purpose', sa.String(length=20), nullable=False),
    sa.Column('target', sa.String(length=160), nullable=True),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('one_time_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_one_time_tokens_token_hash'), ['token_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_one_time_tokens_user_id'), ['user_id'], unique=False)

    op.create_table('rate_limit_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('bucket', sa.String(length=40), nullable=False),
    sa.Column('key_hash', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('rate_limit_events', schema=None) as batch_op:
        batch_op.create_index('ix_rate_limit_lookup', ['bucket', 'key_hash', 'created_at'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_verified_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('phone_verified_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('email_changed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('must_change_password', sa.Boolean(), server_default='0', nullable=False))



def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('must_change_password')
        batch_op.drop_column('email_changed_at')
        batch_op.drop_column('phone_verified_at')
        batch_op.drop_column('email_verified_at')

    with op.batch_alter_table('rate_limit_events', schema=None) as batch_op:
        batch_op.drop_index('ix_rate_limit_lookup')

    op.drop_table('rate_limit_events')
    with op.batch_alter_table('one_time_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_one_time_tokens_user_id'))
        batch_op.drop_index(batch_op.f('ix_one_time_tokens_token_hash'))

    op.drop_table('one_time_tokens')
    with op.batch_alter_table('notification_outbox', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notification_outbox_user_id'))

    op.drop_table('notification_outbox')
