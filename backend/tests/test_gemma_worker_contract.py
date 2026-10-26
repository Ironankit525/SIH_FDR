"""Exercise the real backend HTTP client against the standalone worker using CPU inference stubs."""
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from training.gemma3_27b.service import MODEL_ID, ReviewPolicy, create_app
from training.gemma3_27b.test_worker import RECORDED, TOKEN, png
from app import extraction_engine
from app.config import settings
from app.extraction_engine import ExtractionFailure


def connect_worker(monkeypatch, worker):
    real_client = httpx.Client
    monkeypatch.setattr(settings, 'vlm_endpoint', 'https://worker.example/api/v1/extract-only')
    monkeypatch.setattr(settings, 'vlm_model', MODEL_ID)
    monkeypatch.setattr(settings, 'vlm_api_key', SecretStr(TOKEN))
    monkeypatch.setattr(settings, 'vlm_model_version', 'gemma27b-reviewed-adapter')
    client = TestClient(worker)
    def handle(request):
        assert request.url.path == '/api/v1/extract-only'
        assert request.headers['authorization'] == 'Bearer ' + TOKEN
        response = client.request(request.method, request.url.path,
                                  headers=dict(request.headers), content=request.read())
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)
    def patched_client(**kwargs):
        return real_client(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr(extraction_engine.httpx, 'Client', patched_client)
    return client


def test_portal_http_client_accepts_worker_and_preserves_review_warnings(monkeypatch):
    app = create_app(lambda image: json.dumps(RECORDED), api_key=TOKEN,
                     policy=ReviewPolicy(8, 'Illustrative test rule'))
    with connect_worker(monkeypatch, app):
        result = extraction_engine.http_extract(png(), 'image/png')
    assert result.provider == 'vlm_http'
    assert result.fields['number'] == 'BARBFDR100000'
    assert result.fields['amount'] == '1500000.00'
    assert result.model_name == MODEL_ID
    assert result.model_version == 'gemma27b-reviewed-adapter'
    assert any('MISSING_AICTE_JOINT_HOLDING' in warning for warning in result.warnings)
    assert any('LIEN_NOT_MARKED' in warning for warning in result.warnings)
    assert any('TERM_BELOW_CONFIGURED_MINIMUM' in warning for warning in result.warnings)
    assert 'bank_confirmed' not in result.fields
    assert not result.confidences


def test_worker_busy_maps_to_bounded_backend_retry(monkeypatch):
    app = create_app(lambda image: json.dumps(RECORDED), api_key=TOKEN)
    app.state.inference_slot.acquire()
    try:
        with connect_worker(monkeypatch, app), pytest.raises(ExtractionFailure) as exc:
            extraction_engine.http_extract(png(), 'image/png')
        assert exc.value.retryable
    finally:
        app.state.inference_slot.release()


def test_invalid_output_is_not_saved_as_success(monkeypatch):
    app = create_app(lambda image: '{"deposit_amount":"NaN"}', api_key=TOKEN)
    with connect_worker(monkeypatch, app), pytest.raises(ExtractionFailure) as exc:
        extraction_engine.http_extract(png(), 'image/png')
    assert not exc.value.retryable


@pytest.mark.parametrize('status,headers,message,retryable', [
    (401, {}, 'could not authenticate', False),
    (403, {}, 'could not authenticate', False),
    (404, {'ngrok-error-code': 'ERR_NGROK_3200'}, 'tunnel is offline', True),
    (404, {}, 'endpoint was not found', False),
])
def test_connection_errors_explain_recovery_without_exposing_response(monkeypatch, status, headers, message, retryable):
    real_client = httpx.Client
    monkeypatch.setattr(settings, 'vlm_endpoint', 'https://worker.example/api/v1/extract-only')
    monkeypatch.setattr(settings, 'vlm_model', MODEL_ID)
    transport = httpx.MockTransport(lambda request: httpx.Response(
        status, headers=headers, text='UNTRUSTED_RESPONSE_WITH_PRIVATE_DETAILS'))
    monkeypatch.setattr(extraction_engine.httpx, 'Client',
                        lambda **kwargs: real_client(transport=transport, **kwargs))
    with pytest.raises(ExtractionFailure) as exc:
        extraction_engine.http_extract(png(), 'image/png')
    assert message in str(exc.value)
    assert exc.value.retryable is retryable
    assert 'UNTRUSTED_RESPONSE_WITH_PRIVATE_DETAILS' not in str(exc.value)
