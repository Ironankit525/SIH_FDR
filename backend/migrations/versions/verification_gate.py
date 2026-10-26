"""Formal verification completion and escalation of suspicious cases to Vigilance."""
from alembic import op
import sqlalchemy as sa

revision = 'verification_gate'
down_revision = 'comparison_keys'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().dialect.name == 'sqlite':
        # Nullable inline references can be added without rebuilding this parent
        # table, which existing instruments, documents and audit rows reference.
        # https://www.sqlite.org/lang_altertable.html#alter_table_add_column
        for name in ('verified_at', 'escalated_at', 'vigilance_cleared_at'):
            op.add_column('security_deposits', sa.Column(name, sa.DateTime(timezone=True), nullable=True))
        for name in ('verified_by', 'vigilance_cleared_by'):
            op.execute(f'ALTER TABLE security_deposits ADD COLUMN {name} CHAR(32) REFERENCES users (id)')
        return
    with op.batch_alter_table('security_deposits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('verified_by', sa.Uuid(as_uuid=False), nullable=True))
        batch_op.add_column(sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('vigilance_cleared_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('vigilance_cleared_by', sa.Uuid(as_uuid=False), nullable=True))
        batch_op.create_foreign_key('fk_deposit_verified_by', 'users', ['verified_by'], ['id'])
        batch_op.create_foreign_key('fk_deposit_vigilance_cleared_by', 'users', ['vigilance_cleared_by'], ['id'])


def downgrade():
    if op.get_context().dialect.name == 'sqlite':
        for name in ('vigilance_cleared_by', 'vigilance_cleared_at', 'escalated_at', 'verified_by', 'verified_at'):
            op.drop_column('security_deposits', name)
        return
    with op.batch_alter_table('security_deposits', schema=None) as batch_op:
        batch_op.drop_constraint('fk_deposit_vigilance_cleared_by', type_='foreignkey')
        batch_op.drop_constraint('fk_deposit_verified_by', type_='foreignkey')
        for name in ('vigilance_cleared_by', 'vigilance_cleared_at', 'escalated_at', 'verified_by', 'verified_at'):
            batch_op.drop_column(name)
