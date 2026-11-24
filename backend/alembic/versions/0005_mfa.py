"""S4: TOTP multi-factor authentication

* new tables mfa_credentials (encrypted TOTP secret, status, replay step), mfa_recovery_codes (HMAC only) and auth_challenges
* auth_sessions.assurance (default PASSWORD), mfa_at, mfa_method

No existing account is changed or marked MFA-enrolled. Existing sessions keep assurance PASSWORD, so a privileged account
with such a session is in the restricted "MFA enrolment pending" state until it enrols. Downgrade drops the new tables and
columns (every enrolment, recovery code and pending challenge is lost; accounts and records are untouched).

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('auth_challenges',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('purpose', sa.String(length=20), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('remember', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('auth_challenges', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_auth_challenges_token_hash'), ['token_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_auth_challenges_user_id'), ['user_id'], unique=False)

    op.create_table('mfa_credentials',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('secret_enc', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(), nullable=True),
    sa.Column('last_used_step', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mfa_credentials', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mfa_credentials_user_id'), ['user_id'], unique=True)

    op.create_table('mfa_recovery_codes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mfa_recovery_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mfa_recovery_codes_code_hash'), ['code_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_mfa_recovery_codes_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('auth_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assurance', sa.String(length=10), server_default='PASSWORD', nullable=False))
        batch_op.add_column(sa.Column('mfa_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('mfa_method', sa.String(length=10), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('auth_sessions', schema=None) as batch_op:
        batch_op.drop_column('mfa_method')
        batch_op.drop_column('mfa_at')
        batch_op.drop_column('assurance')

    with op.batch_alter_table('mfa_recovery_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mfa_recovery_codes_user_id'))
        batch_op.drop_index(batch_op.f('ix_mfa_recovery_codes_code_hash'))

    op.drop_table('mfa_recovery_codes')
    with op.batch_alter_table('mfa_credentials', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mfa_credentials_user_id'))

    op.drop_table('mfa_credentials')
    with op.batch_alter_table('auth_challenges', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_auth_challenges_user_id'))
        batch_op.drop_index(batch_op.f('ix_auth_challenges_token_hash'))

    op.drop_table('auth_challenges')
