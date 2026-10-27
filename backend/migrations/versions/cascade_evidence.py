"""Preserve extraction stages and disagreements without rewriting old evidence."""
from alembic import op
import sqlalchemy as sa

revision = 'cascade_evidence'
down_revision = 'verification_gate'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('document_extractions', sa.Column('evidence', sa.JSON(), nullable=False, server_default='{}'))


def downgrade():
    op.drop_column('document_extractions', 'evidence')
