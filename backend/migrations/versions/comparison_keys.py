"""Indexed normalised keys for duplicate and reuse checks, replacing full-table scans."""
from alembic import context, op
import sqlalchemy as sa

from app.matching import normalise_bank, normalise_number, text_fingerprint

revision = 'comparison_keys'
down_revision = 'risk_engine'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('deposit_instruments', sa.Column('number_key', sa.String(100), nullable=True))
    op.add_column('deposit_instruments', sa.Column('bank_key', sa.String(150), nullable=True))
    op.add_column('document_extractions', sa.Column('text_fingerprint', sa.String(64), nullable=True))
    op.create_index(op.f('ix_deposit_instruments_number_key'), 'deposit_instruments', ['number_key'])
    op.create_index(op.f('ix_document_extractions_text_fingerprint'), 'document_extractions', ['text_fingerprint'])
    if context.is_offline_mode():
        return  # SQL-only runs cannot read rows; the application fills keys as records are next saved
    # Backfill with the application's own normalisation so existing and new rows compare identically.
    bind = op.get_bind()
    instruments = sa.table('deposit_instruments', sa.column('id'), sa.column('bank'), sa.column('number'), sa.column('number_key'), sa.column('bank_key'))
    for row in bind.execute(sa.select(instruments.c.id, instruments.c.bank, instruments.c.number)).all():
        bind.execute(instruments.update().where(instruments.c.id == row.id).values(number_key=normalise_number(row.number), bank_key=normalise_bank(row.bank)))
    extractions = sa.table('document_extractions', sa.column('id'), sa.column('original_text'), sa.column('text_fingerprint'))
    for row in bind.execute(sa.select(extractions.c.id, extractions.c.original_text)).all():
        bind.execute(extractions.update().where(extractions.c.id == row.id).values(text_fingerprint=text_fingerprint(row.original_text)))


def downgrade():
    op.drop_index(op.f('ix_document_extractions_text_fingerprint'), 'document_extractions')
    op.drop_index(op.f('ix_deposit_instruments_number_key'), 'deposit_instruments')
    op.drop_column('document_extractions', 'text_fingerprint')
    op.drop_column('deposit_instruments', 'bank_key')
    op.drop_column('deposit_instruments', 'number_key')
