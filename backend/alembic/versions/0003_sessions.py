"""S2: server-side sessions, hashed rotating refresh tokens, per-user token version

* new tables auth_sessions and refresh_tokens (no secrets: refresh tokens are stored only as SHA-256)
* users.token_version (default 0) and users.password_changed_at

Legacy long-lived JWTs are NOT converted: they carry no session id, so the new code rejects them at once and everyone
signs in again. No grace period. Downgrade drops the tables/columns (all sessions end); an older build would then accept
its own old-format tokens again, so restore the pre-migration backup together with the old code if rolling back.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('auth_sessions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_used_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('idle_timeout_s', sa.Integer(), nullable=False),
    sa.Column('remember', sa.Boolean(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('revoked_reason', sa.String(length=40), nullable=True),
    sa.Column('user_agent', sa.String(length=200), nullable=True),
    sa.Column('client_hash', sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('auth_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_auth_sessions_revoked_at'), ['revoked_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_auth_sessions_user_id'), ['user_id'], unique=False)

    op.create_table('refresh_tokens',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.String(length=32), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_refresh_tokens_session_id'), ['session_id'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('token_version', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('password_changed_at', sa.DateTime(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('password_changed_at')
        batch_op.drop_column('token_version')

    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_session_id'))

    op.drop_table('refresh_tokens')
    with op.batch_alter_table('auth_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_auth_sessions_user_id'))
        batch_op.drop_index(batch_op.f('ix_auth_sessions_revoked_at'))

    op.drop_table('auth_sessions')
