"""S5: agencies, invitations, activation flags

* new tables agencies and invitations (hashed single-use tokens)
* users.agency_id, users.contact_verification_required (default 0), users.contact_verification_waived_at, users.is_demo (default 0)
* rescue_teams.agency_id

No existing account is changed, flagged, verified, disabled or re-assigned: existing privileged accounts keep working under the
policy of the running configuration (docs/security/S5_ACCOUNTS_AGENCIES.md, "Existing accounts"). Downgrade drops the new tables
and columns (agencies, invitations, memberships and flags are lost; accounts and operational records are untouched).

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('agencies',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('agency_type', sa.String(length=30), nullable=False),
    sa.Column('region', sa.String(length=120), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.String(length=80), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('invitations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('recipient_email', sa.String(length=120), nullable=False),
    sa.Column('agency_id', sa.Integer(), nullable=True),
    sa.Column('team_id', sa.String(length=50), nullable=True),
    sa.Column('created_by', sa.String(length=80), nullable=False),
    sa.Column('reason', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('accepted_user_id', sa.Integer(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('revoked_by', sa.String(length=80), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('invitations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invitations_token_hash'), ['token_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_invitations_recipient_email'), ['recipient_email'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('agency_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('contact_verification_required', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('contact_verification_waived_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('is_demo', sa.Boolean(), server_default='0', nullable=False))
        batch_op.create_index(batch_op.f('ix_users_agency_id'), ['agency_id'], unique=False)

    with op.batch_alter_table('rescue_teams', schema=None) as batch_op:
        batch_op.add_column(sa.Column('agency_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_rescue_teams_agency_id'), ['agency_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('rescue_teams', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rescue_teams_agency_id'))
        batch_op.drop_column('agency_id')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_agency_id'))
        batch_op.drop_column('is_demo')
        batch_op.drop_column('contact_verification_waived_at')
        batch_op.drop_column('contact_verification_required')
        batch_op.drop_column('agency_id')

    with op.batch_alter_table('invitations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invitations_recipient_email'))
        batch_op.drop_index(batch_op.f('ix_invitations_token_hash'))

    op.drop_table('invitations')
    op.drop_table('agencies')
