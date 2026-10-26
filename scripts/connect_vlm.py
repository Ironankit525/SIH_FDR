"""Validate a downloaded Colab configuration and merge only its worker settings."""
import argparse
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('EXTRACTION_PROVIDER', 'VLM_ENDPOINT', 'VLM_API_KEY', 'VLM_MODEL',
        'VLM_MODEL_VERSION', 'VLM_TIMEOUT_SECONDS')


def read_worker_config(source):
    values = dotenv_values(source, interpolate=False)
    if any(not values.get(key) or '\n' in values[key] or '\r' in values[key] for key in KEYS):
        raise ValueError('The downloaded worker configuration is incomplete or invalid.')
    config = {key: values[key] for key in KEYS}
    url = urlsplit(config['VLM_ENDPOINT'])
    if (url.scheme != 'https' or not url.hostname or url.path != '/api/v1/extract-only'
            or any((url.username, url.password, url.query, url.fragment))):
        raise ValueError('Expected an HTTPS worker URL ending in /api/v1/extract-only.')
    if config['EXTRACTION_PROVIDER'] != 'vlm_http':
        raise ValueError('Expected EXTRACTION_PROVIDER=vlm_http.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,}', config['VLM_API_KEY']):
        raise ValueError('The worker API key is invalid.')
    if not config['VLM_TIMEOUT_SECONDS'].isdigit() or not 1 <= int(config['VLM_TIMEOUT_SECONDS']) <= 300:
        raise ValueError('Worker timeout must be between 1 and 300 seconds.')
    return config


def check_worker(config):
    url = urlsplit(config['VLM_ENDPOINT'])
    try:
        response = httpx.get(f'{url.scheme}://{url.netloc}/health',
                            headers={'Authorization': 'Bearer ' + config['VLM_API_KEY']},
                            timeout=30, follow_redirects=False, trust_env=False)
    except httpx.RequestError:
        raise ValueError('Cannot reach Colab. Check the runtime, tunnel and internet connection.') from None
    if response.status_code in (401, 403):
        raise ValueError('Worker authentication failed. Get the latest backend-vlm.env from its owner.')
    if response.headers.get('ngrok-error-code') == 'ERR_NGROK_3200':
        raise ValueError('The Colab tunnel is offline. Ask its owner to restart the serving cell.')
    if response.status_code != 200:
        raise ValueError(f'Worker health check failed (HTTP {response.status_code}). No settings changed.')
    try:
        health = response.json()
        if health.get('status') != 'ready' or health.get('model') != config['VLM_MODEL']:
            raise ValueError()
    except (ValueError, AttributeError):
        raise ValueError('Worker health response does not match the configured model.') from None


def save_config(config, destination):
    original = destination.read_text() if destination.exists() else '# Private local configuration.\n'
    existing = dotenv_values(destination, interpolate=False) if destination.exists() else {}
    if existing.get('ENVIRONMENT', 'development') != 'development' or os.environ.get('ENVIRONMENT', 'development') != 'development':
        raise ValueError('This helper configures development environments only.')
    lines = [line for line in original.splitlines()
             if not re.match(r'^\s*(?:export\s+)?(' + '|'.join(KEYS) + r')\s*=', line)]
    def quote(value):
        return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"
    content = '\n'.join(lines).rstrip() + '\n\n' + '\n'.join(
        key + '=' + quote(config[key]) for key in KEYS) + '\n'
    descriptor, temporary = tempfile.mkstemp(prefix='.env-', dir=destination.parent)
    try:
        with os.fdopen(descriptor, 'w') as handle:
            handle.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path, help='Path to the current backend-vlm.env downloaded from Colab')
    args = parser.parse_args()
    if any(key in os.environ for key in KEYS):
        parser.exit(1, 'Unset exported EXTRACTION_PROVIDER/VLM settings first; they override backend/.env.\n')
    try:
        config = read_worker_config(args.config.expanduser())
        check_worker(config)
        save_config(config, ROOT / 'backend/.env')
    except (ValueError, OSError):
        # Never display file contents, response bodies, endpoint credentials or request headers.
        import sys
        error = sys.exception()
        message = str(error) if isinstance(error, ValueError) else 'Could not read the configuration or write backend/.env.'
        parser.exit(1, message + '\n')
    print('Worker authentication and model health verified. Updated backend/.env (private permissions).')
    print('Other backend settings were preserved. Restart python3 scripts/dev.py, then retry failed extraction.')


if __name__ == '__main__':
    main()
