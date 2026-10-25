"""Extraction provenance, durable worker claims and serialised audit heads."""
from alembic import op
import sqlalchemy as sa

revision = 'extraction_provenance'
down_revision = 'audit_append_only'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('documents', sa.Column('processing_token', sa.String(64), nullable=True))
    op.add_column('documents', sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('processing_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('documents', sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('document_extractions', sa.Column('provider', sa.String(30), nullable=False, server_default='ocr'))
    op.add_column('document_extractions', sa.Column('model_name', sa.String(150), nullable=True))
    op.add_column('document_extractions', sa.Column('model_version', sa.String(100), nullable=True))
    op.add_column('document_extractions', sa.Column('document_sha256', sa.String(64), nullable=True))
    op.add_column('document_extractions', sa.Column('warnings', sa.JSON(), nullable=False, server_default='[]'))
    op.create_table('audit_chain_heads', sa.Column('entity_id', sa.String(80), primary_key=True),
                    sa.Column('event_hash', sa.String(64), nullable=False),
                    sa.Column('last_created_at', sa.DateTime(timezone=True), nullable=True))
    # Preserve old events verbatim, including their hashes and exact timestamps.
    op.execute("""INSERT INTO audit_chain_heads(entity_id, event_hash, last_created_at)
        SELECT entity_id, event_hash, created_at FROM (
            SELECT entity_id, event_hash, created_at,
                   ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY created_at DESC, id DESC) AS rank
            FROM audit_logs
        ) latest WHERE rank = 1""")
    op.execute("""UPDATE document_extractions SET document_sha256 =
        (SELECT sha256 FROM documents WHERE documents.id = document_extractions.document_id)""")


def downgrade():
    op.drop_table('audit_chain_heads')
    for name in ('warnings', 'document_sha256', 'model_version', 'model_name', 'provider'):
        op.drop_column('document_extractions', name)
    for name in ('next_attempt_at', 'processing_attempts', 'processing_started_at', 'processing_token'):
        op.drop_column('documents', name)
