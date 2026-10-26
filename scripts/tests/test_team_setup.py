"""Check credential import boundaries without contacting Colab or changing local settings."""
import importlib.util
import os
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values

spec = importlib.util.spec_from_file_location('team_connect_vlm', Path(__file__).resolve().parents[1] / 'connect_vlm.py')
connect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(connect)


@pytest.fixture
def configuration():
    return {'EXTRACTION_PROVIDER': 'vlm_http', 'VLM_ENDPOINT': 'https://worker.example/api/v1/extract-only',
            'VLM_API_KEY': 'fictional-test-token-' + 'x' * 40, 'VLM_MODEL': 'fictional-test-model',
            'VLM_MODEL_VERSION': 'test-version', 'VLM_TIMEOUT_SECONDS': '300'}


def test_import_only_worker_fields_and_preserve_other_settings(tmp_path, monkeypatch, configuration):
    monkeypatch.delenv('ENVIRONMENT', raising=False)
    source = tmp_path / 'download.env'
    source.write_text('\n'.join(f'{k}={v}' for k, v in configuration.items()) +
                      '\nDATABASE_URL=untrusted-database\nSECRET_KEY=untrusted-key\n')
    destination = tmp_path / '.env'
    destination.write_text('DATABASE_URL=sqlite:///existing.db\nSECRET_KEY=existing-test-key\n'
                           'EXTRACTION_PROVIDER=ocr\nVLM_API_KEY=old-test-key\n')
    config = connect.read_worker_config(source)
    connect.save_config(config, destination)
    saved = dotenv_values(destination)
    assert saved['DATABASE_URL'] == 'sqlite:///existing.db'
    assert saved['SECRET_KEY'] == 'existing-test-key'
    assert all(saved[k] == v for k, v in configuration.items())
    assert destination.read_text().count('VLM_API_KEY=') == 1
    if os.name != 'nt':
        assert destination.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('status,headers', [(401, {}), (404, {'ngrok-error-code': 'ERR_NGROK_3200'})])
def test_failed_health_check_preserves_settings_and_hides_response(tmp_path, monkeypatch, capsys, configuration, status, headers):
    for key in connect.KEYS:
        monkeypatch.delenv(key, raising=False)
    (tmp_path / 'backend').mkdir()
    destination = tmp_path / 'backend/.env'
    original = 'EXTRACTION_PROVIDER=ocr\nSECRET_KEY=local-test-key\n'
    destination.write_text(original)
    source = tmp_path / 'download.env'
    source.write_text('\n'.join(f'{k}={v}' for k, v in configuration.items()))
    monkeypatch.setattr(connect, 'ROOT', tmp_path)
    monkeypatch.setattr('sys.argv', ['connect_vlm.py', str(source)])
    monkeypatch.setattr(connect.httpx, 'get', lambda *args, **kwargs: httpx.Response(
        status, headers=headers, text='PRIVATE_RESPONSE_' + configuration['VLM_API_KEY']))
    with pytest.raises(SystemExit) as exc:
        connect.main()
    assert exc.value.code == 1
    assert destination.read_text() == original
    output = capsys.readouterr()
    assert configuration['VLM_API_KEY'] not in output.out + output.err
    assert 'PRIVATE_RESPONSE_' not in output.out + output.err


def test_health_requires_authentication_and_matching_model(monkeypatch, configuration):
    def health(url, **kwargs):
        assert url == 'https://worker.example/health'
        assert kwargs['headers']['Authorization'] == 'Bearer ' + configuration['VLM_API_KEY']
        assert kwargs['follow_redirects'] is False
        return httpx.Response(200, json={'status': 'ready', 'model': configuration['VLM_MODEL']})
    monkeypatch.setattr(connect.httpx, 'get', health)
    connect.check_worker(configuration)
    monkeypatch.setattr(connect.httpx, 'get', lambda *args, **kwargs: httpx.Response(
        200, json={'status': 'ready', 'model': 'different-model'}))
    with pytest.raises(ValueError, match='does not match'):
        connect.check_worker(configuration)
