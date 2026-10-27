"""Check hosted startup without contacting a database, bucket or hosting account."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import types

from cryptography.fernet import Fernet
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('render_start', ROOT / 'backend/start_render.py')
startup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(startup)


@pytest.fixture
def hosted():
    return dict(DATABASE_URL='postgresql+psycopg://test:fictional@db.example/postgres',
                SECRET_KEY='fictional-test-key-' * 3, STORAGE_ENCRYPTION_KEY=Fernet.generate_key().decode(),
                STORAGE_BACKEND='s3', S3_ENDPOINT='https://storage.example', S3_REGION='ap-south-1',
                S3_BUCKET='test', S3_ACCESS_KEY='fictional', S3_SECRET_KEY='fictional',
                FRONTEND_ORIGIN='https://portal.example', COOKIE_SECURE='true',
                ENVIRONMENT='development', SEED_DEMO='true', DEMO_PASSWORD='fictional-demo-password', PORT='10000')


@pytest.mark.parametrize('key,value', [('DATABASE_URL', 'sqlite:///data.db'), ('STORAGE_BACKEND', 'local'),
    ('STORAGE_ENCRYPTION_KEY', 'invalid'), ('COOKIE_SECURE', 'false'), ('FRONTEND_ORIGIN', 'https://portal.example/path'),
    ('ENVIRONMENT', 'production'), ('DEMO_PASSWORD', ''), ('PORT', 'invalid')])
def test_hosted_start_rejects_ephemeral_or_incomplete_configuration(hosted, key, value):
    hosted[key] = value
    with pytest.raises(ValueError):
        startup.validate_environment(hosted)


def test_hosted_start_migrates_then_seeds_without_exporting_files_then_execs_server(hosted, monkeypatch):
    calls = []
    monkeypatch.setattr(startup.os, 'environ', hosted)
    monkeypatch.setattr(startup.os, 'chdir', lambda path: None)
    monkeypatch.setattr(startup.subprocess, 'run', lambda args, **kwargs: calls.append(('migrate', args, kwargs)))
    monkeypatch.setattr(startup.os, 'execv', lambda executable, args: calls.append(('serve', args)))
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setitem(sys.modules, 'app.db', types.SimpleNamespace(SessionLocal=Session))
    monkeypatch.setitem(sys.modules, 'app.seed', types.SimpleNamespace(seed=lambda session, **kwargs: calls.append(('seed', kwargs))))
    startup.main()
    assert [call[0] for call in calls] == ['migrate', 'seed', 'serve']
    assert calls[0][2] == {'check': True}
    assert calls[1][1] == {'save_files': False}
    assert calls[2][1][calls[2][1].index('--port') + 1] == '10000'


def test_failed_migration_does_not_start_server_or_seed(hosted, monkeypatch):
    monkeypatch.setattr(startup.os, 'environ', hosted)
    monkeypatch.setattr(startup.os, 'chdir', lambda path: None)
    def fail(*args, **kwargs): raise subprocess.CalledProcessError(1, 'alembic')
    monkeypatch.setattr(startup.subprocess, 'run', fail)
    monkeypatch.setattr(startup.os, 'execv', lambda *args: pytest.fail('Server started despite failed migration'))
    with pytest.raises(subprocess.CalledProcessError): startup.main()


def vercel_config(origin):
    env = {**os.environ, 'BACKEND_ORIGIN': origin}
    return subprocess.run(['node', '--input-type=module', '-e',
        "import {config} from './vercel.mjs'; console.log(JSON.stringify(config))"],
        cwd=ROOT / 'frontend', env=env, text=True, capture_output=True)


def test_vercel_keeps_api_prefix_and_only_falls_back_for_frontend_routes():
    result = vercel_config('https://backend.example/')
    assert result.returncode == 0, result.stderr
    routes = json.loads(result.stdout)['rewrites']
    assert routes[0] == {'source': '/api/:path*', 'destination': 'https://backend.example/api/:path*'}
    assert routes[1]['source'] == '/((?!api(?:/|$)).*)'


@pytest.mark.parametrize('origin', ['', 'http://localhost:8000', 'https://backend.example/api', 'https://user:secret@backend.example'])
def test_vercel_requires_public_https_origin_without_credentials(origin):
    assert vercel_config(origin).returncode != 0
