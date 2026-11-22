"""S0: private evidence photos and random public report references

* new table media_assets (one row per evidence photo; files are private)
* incidents.public_ref (random, unique) and incidents.tracking_code_hash
* every existing incident gets a random public_ref. Existing reports get NO tracking code (a code cannot be
  reconstructed and none was ever issued), so they cannot be looked up by guests; staff are unaffected.

Downgrade drops the new columns/table (public references, tracking hashes and media rows are lost; the image
files themselves are not deleted). Restoring the pre-migration backup is the safer rollback.

Revision ID: 0002
Revises: 0001
"""
import secrets

from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('media_assets',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('incident_id', sa.String(length=50), nullable=True),
    sa.Column('stored_name', sa.String(length=80), nullable=False),
    sa.Column('content_type', sa.String(length=50), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('uploader_user_id', sa.Integer(), nullable=True),
    sa.Column('uploader_hash', sa.String(length=32), nullable=True),
    sa.Column('privacy', sa.String(length=20), nullable=False),
    sa.Column('legacy_source', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_media_assets_incident_id'), ['incident_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_media_assets_uploader_hash'), ['uploader_hash'], unique=False)

    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('public_ref', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('tracking_code_hash', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_incidents_public_ref'), ['public_ref'], unique=True)

    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    conn = op.get_bind()
    taken = set()
    for (incident_id,) in conn.execute(sa.text("SELECT id FROM incidents WHERE public_ref IS NULL")).fetchall():
        while True:
            body = "".join(secrets.choice(alphabet) for _ in range(12))
            ref = "RN-" + "-".join(body[i:i + 4] for i in range(0, 12, 4))
            if ref not in taken:
                taken.add(ref)
                break
        conn.execute(sa.text("UPDATE incidents SET public_ref = :r WHERE id = :i"), {"r": ref, "i": incident_id})


def downgrade() -> None:
    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_incidents_public_ref'))
        batch_op.drop_column('tracking_code_hash')
        batch_op.drop_column('public_ref')

    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_media_assets_uploader_hash'))
        batch_op.drop_index(batch_op.f('ix_media_assets_incident_id'))

    op.drop_table('media_assets')
