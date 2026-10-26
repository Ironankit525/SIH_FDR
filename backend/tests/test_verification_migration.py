"""The verification upgrade must also work when deposits already have children."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_verification_migration_preserves_referenced_deposits():
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/verification_gate.py'
    spec = importlib.util.spec_from_file_location('verification_gate_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        connection.exec_driver_sql('CREATE TABLE users (id CHAR(32) PRIMARY KEY)')
        connection.exec_driver_sql('CREATE TABLE security_deposits (id CHAR(32) PRIMARY KEY)')
        connection.exec_driver_sql('CREATE TABLE documents (id INTEGER PRIMARY KEY, deposit_id CHAR(32) REFERENCES security_deposits(id))')
        connection.exec_driver_sql("INSERT INTO users VALUES ('officer')")
        connection.exec_driver_sql("INSERT INTO security_deposits VALUES ('deposit')")
        connection.exec_driver_sql("INSERT INTO documents VALUES (1, 'deposit')")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.exec_driver_sql('SELECT verified_by, vigilance_cleared_by FROM security_deposits').one() == (None, None)
            for column in ('verified_by', 'vigilance_cleared_by'):
                with pytest.raises(sa.exc.IntegrityError):
                    with connection.begin_nested():
                        connection.exec_driver_sql(f"UPDATE security_deposits SET {column}='missing-officer'")
                connection.exec_driver_sql(f"UPDATE security_deposits SET {column}='officer'")
            migration.downgrade()
        assert connection.exec_driver_sql('SELECT * FROM documents').all() == [(1, 'deposit')]
        assert connection.exec_driver_sql('SELECT * FROM security_deposits').all() == [('deposit',)]
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
        assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
    engine.dispose()
