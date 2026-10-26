"""Risk score history and approved risk weight versions."""
from alembic import op
import sqlalchemy as sa

revision = 'risk_engine'
down_revision = 'risk_safeguards'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('risk_weight_versions',
                    sa.Column('version', sa.Integer(), nullable=False),
                    sa.Column('status', sa.String(20), nullable=False),
                    sa.Column('weights', sa.JSON(), nullable=False),
                    sa.Column('category_caps', sa.JSON(), nullable=False),
                    sa.Column('thresholds', sa.JSON(), nullable=False),
                    sa.Column('notes', sa.Text(), nullable=False),
                    sa.Column('proposed_by', sa.Uuid(as_uuid=False), nullable=False),
                    sa.Column('approved_by', sa.Uuid(as_uuid=False), nullable=True),
                    sa.Column('id', sa.Uuid(as_uuid=False), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.ForeignKeyConstraint(['proposed_by'], ['users.id']),
                    sa.ForeignKeyConstraint(['approved_by'], ['users.id']),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('version'))
    op.create_index(op.f('ix_risk_weight_versions_created_at'), 'risk_weight_versions', ['created_at'])
    op.create_table('risk_assessments',
                    sa.Column('deposit_id', sa.Uuid(as_uuid=False), nullable=False),
                    sa.Column('instrument_id', sa.Uuid(as_uuid=False), nullable=True),
                    sa.Column('score', sa.Numeric(4, 1), nullable=False),
                    sa.Column('level', sa.String(10), nullable=False),
                    sa.Column('signals', sa.JSON(), nullable=False),
                    sa.Column('engine_version', sa.String(20), nullable=False),
                    sa.Column('weights_version', sa.Integer(), nullable=False),
                    sa.Column('inputs_digest', sa.String(64), nullable=False),
                    sa.Column('id', sa.Uuid(as_uuid=False), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.CheckConstraint('score >= 0 AND score <= 100'),
                    sa.ForeignKeyConstraint(['deposit_id'], ['security_deposits.id']),
                    sa.ForeignKeyConstraint(['instrument_id'], ['deposit_instruments.id']),
                    sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_risk_assessments_created_at'), 'risk_assessments', ['created_at'])
    op.create_index(op.f('ix_risk_assessments_deposit_id'), 'risk_assessments', ['deposit_id'])
    op.create_index(op.f('ix_risk_assessments_level'), 'risk_assessments', ['level'])


def downgrade():
    op.drop_table('risk_assessments')
    op.drop_table('risk_weight_versions')
