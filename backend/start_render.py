"""Start the hosted API with durable external storage. Local dev.py is unchanged."""
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

from cryptography.fernet import Fernet


def validate_environment(env):
    required = ('DATABASE_URL', 'SECRET_KEY', 'STORAGE_ENCRYPTION_KEY', 'FRONTEND_ORIGIN',
                'S3_ENDPOINT', 'S3_REGION', 'S3_BUCKET', 'S3_ACCESS_KEY', 'S3_SECRET_KEY')
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise ValueError('Set these Render environment variables: ' + ', '.join(missing))
    if not env['DATABASE_URL'].startswith('postgresql+psycopg://') or env.get('STORAGE_BACKEND') != 's3':
        raise ValueError('Hosted startup requires PostgreSQL (postgresql+psycopg://) and STORAGE_BACKEND=s3; local files are ephemeral.')
    origin = urlsplit(env['FRONTEND_ORIGIN'])
    if origin.scheme != 'https' or not origin.hostname or origin.path or origin.query or origin.fragment or origin.username or origin.password:
        raise ValueError('FRONTEND_ORIGIN must be an HTTPS origin without a trailing slash, path or credentials.')
    if env.get('COOKIE_SECURE', '').lower() != 'true':
        raise ValueError('Set COOKIE_SECURE=true for the hosted frontend.')
    try:
        Fernet(env['STORAGE_ENCRYPTION_KEY'].encode())
    except (ValueError, TypeError):
        raise ValueError('STORAGE_ENCRYPTION_KEY must be a generated Fernet key.') from None
    if len(env['SECRET_KEY']) < 32:
        raise ValueError('Generate a SECRET_KEY with at least 32 characters.')
    seed_demo = env.get('SEED_DEMO', '').lower() == 'true'
    if seed_demo and (env.get('ENVIRONMENT') != 'development' or len(env.get('DEMO_PASSWORD', '')) < 12):
        raise ValueError('Demo seeding requires ENVIRONMENT=development and a DEMO_PASSWORD of at least 12 characters.')
    port = env.get('PORT', '8000')
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError('PORT must be between 1 and 65535.')
    return seed_demo, port


def main():
    try:
        seed_demo, port = validate_environment(os.environ)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    os.chdir(Path(__file__).resolve().parent)
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], check=True)
    if seed_demo:
        from app.db import SessionLocal
        from app.seed import seed
        with SessionLocal() as session:
            seed(session, save_files=False)
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'app.main:app',
                             '--host', '0.0.0.0', '--port', port, '--no-access-log'])


if __name__ == '__main__':
    main()
