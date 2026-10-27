"""Add Bank role and bank verification tracking fields.

Revision ID: bank_role_workflow
Revises: verification_gate
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'bank_role_workflow'
down_revision = 'verification_gate'
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_context().dialect.name
    if dialect == 'sqlite':
        op.add_column('users', sa.Column('bank_name', sa.String(150), nullable=True))
        op.add_column('verification_requests', sa.Column('bank_name', sa.String(150), nullable=True))
        op.add_column('verification_requests', sa.Column('officer_notes', sa.Text(), nullable=True))
        op.add_column('verification_requests', sa.Column('bank_decision', sa.String(40), nullable=True))
        op.add_column('verification_requests', sa.Column('bank_remarks', sa.Text(), nullable=True))
        op.execute('ALTER TABLE verification_requests ADD COLUMN bank_user_id CHAR(32) REFERENCES users (id)')
        op.add_column('verification_requests', sa.Column('bank_verified_at', sa.DateTime(timezone=True), nullable=True))
        return

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bank_name', sa.String(150), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_bank_name'), ['bank_name'], unique=False)

    with op.batch_alter_table('verification_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bank_name', sa.String(150), nullable=True))
        batch_op.add_column(sa.Column('officer_notes', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('bank_decision', sa.String(40), nullable=True))
        batch_op.add_column(sa.Column('bank_remarks', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('bank_user_id', sa.Uuid(as_uuid=False), nullable=True))
        batch_op.add_column(sa.Column('bank_verified_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key('fk_verification_requests_bank_user_id', 'users', ['bank_user_id'], ['id'])
        batch_op.create_index(batch_op.f('ix_verification_requests_bank_name'), ['bank_name'], unique=False)


def downgrade():
    dialect = op.get_context().dialect.name
    if dialect == 'sqlite':
        for col in ('bank_verified_at', 'bank_user_id', 'bank_remarks', 'bank_decision', 'officer_notes', 'bank_name'):
            op.drop_column('verification_requests', col)
        op.drop_column('users', 'bank_name')
        return

    with op.batch_alter_table('verification_requests', schema=None) as batch_op:
        batch_op.drop_constraint('fk_verification_requests_bank_user_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_verification_requests_bank_name'))
        for col in ('bank_verified_at', 'bank_user_id', 'bank_remarks', 'bank_decision', 'officer_notes', 'bank_name'):
            batch_op.drop_column(col)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_bank_name'))
        batch_op.drop_column('bank_name')
