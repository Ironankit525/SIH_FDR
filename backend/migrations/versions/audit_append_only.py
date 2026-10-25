"""Enforce append-only audit events at the database boundary."""
from alembic import op
revision = "audit_append_only"
down_revision = "3d40e7401453"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION depositflow_protect_audit() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'Audit events are append-only'; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER audit_no_change BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION depositflow_protect_audit()")
    elif op.get_bind().dialect.name == "sqlite":
        op.execute("CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_logs BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END")
        op.execute("CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_logs BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER audit_no_change ON audit_logs")
        op.execute("DROP FUNCTION depositflow_protect_audit()")
    elif op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER audit_no_update")
        op.execute("DROP TRIGGER audit_no_delete")
