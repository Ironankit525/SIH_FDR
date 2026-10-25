"""Review-task resolution provenance and stored document integrity indicators."""
from alembic import op
import sqlalchemy as sa

revision = 'risk_safeguards'
down_revision = 'extraction_provenance'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('discrepancy_cases', schema=None) as batch_op:
        batch_op.add_column(sa.Column('resolution_kind', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('resolved_by', sa.Uuid(as_uuid=False), nullable=True))
        batch_op.add_column(sa.Column('confirmed_by', sa.Uuid(as_uuid=False), nullable=True))
        batch_op.add_column(sa.Column('condition_active', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.create_foreign_key('fk_discrepancy_resolved_by', 'users', ['resolved_by'], ['id'])
        batch_op.create_foreign_key('fk_discrepancy_confirmed_by', 'users', ['confirmed_by'], ['id'])
    op.add_column('documents', sa.Column('forensics', sa.JSON(), nullable=False, server_default='{}'))
    # Existing resolutions were recorded by officers before automatic clearing existed.
    op.execute("UPDATE discrepancy_cases SET resolution_kind = 'officer' WHERE status = 'resolved'")


def downgrade():
    op.drop_column('documents', 'forensics')
    with op.batch_alter_table('discrepancy_cases', schema=None) as batch_op:
        batch_op.drop_constraint('fk_discrepancy_confirmed_by', type_='foreignkey')
        batch_op.drop_constraint('fk_discrepancy_resolved_by', type_='foreignkey')
        for name in ('condition_active', 'confirmed_by', 'resolved_by', 'resolution_kind'):
            batch_op.drop_column(name)
