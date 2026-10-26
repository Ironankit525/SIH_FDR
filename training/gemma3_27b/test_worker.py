"""CPU contract/regression tests; these do not pretend to measure the 27B model."""
import asyncio
import io
import json
from pathlib import Path

import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from . import service
from .evaluation import evaluate, load_manifest, make_synthetic_holdout, metrics
from .service import MODEL_ID, ReviewPolicy, create_app, normalise, portal_response, scrutiny_flags

TOKEN = 'test_only_' + 'a' * 40
DEMO_POLICY = ReviewPolicy(8, 'Illustrative regression test; not verified APH policy')
# Exact fields from the reviewed notebook's saved inference output. Its three flags were missing.
RECORDED = {'fdr_number': 'BARBFDR100000', 'issuing_bank': 'Bank of Baroda',
            'ifsc_code': 'BARB0VJPUNE', 'deposit_amount': 1500000,
            'issue_date': '2025-06-15', 'maturity_date': '2030-06-15', 'tenure_years': 5,
            'joint_holder_aicte_verified': False, 'lien_marked_aicte': False,
            'official_bank_stamp_present': True, 'document_scrutiny_flags': []}


def png(color='white'):
    buffer = io.BytesIO()
    Image.new('RGB', (64, 64), color).save(buffer, format='PNG')
    return buffer.getvalue()


def client(infer=None, **kwargs):
    app = create_app(infer or (lambda image: json.dumps(RECORDED)), api_key=TOKEN, policy=DEMO_POLICY, **kwargs)
    return TestClient(app, headers={'Authorization': 'Bearer ' + TOKEN})


def upload(c, data=None, mime='image/png', name='file', model=MODEL_ID):
    return c.post('/api/v1/extract-only', data={'model': model}, files={name: ('receipt', data if data is not None else png(), mime)})


def test_recorded_missing_flags_are_recomputed_and_model_flags_ignored():
    response, evidence = portal_response(json.dumps(RECORDED), DEMO_POLICY)
    assert set(evidence['flag_codes']) == {'MISSING_AICTE_JOINT_HOLDING', 'LIEN_NOT_MARKED', 'TERM_BELOW_CONFIGURED_MINIMUM'}
    assert response['fields']['amount'] == '1500000.00'
    assert response['fields']['depositor_name'] is None
    spoof = dict(RECORDED, document_scrutiny_flags=['APPROVED_BY_BANK'])
    assert portal_response(json.dumps(spoof), DEMO_POLICY) == (response, evidence)
    assert not response['confidences']
    assert any('LEGACY_' in warning for warning in response['warnings'])
    assert any('DOCUMENT_CLAIMS_ONLY' in warning for warning in response['warnings'])


def test_unknowns_do_not_become_false_and_no_universal_eight_year_rule():
    response, evidence = portal_response('{"fdr_number":"ONE"}', ReviewPolicy())
    assert 'MISSING_AICTE_JOINT_HOLDING' not in evidence['flag_codes']
    assert 'JOINT_HOLDING_UNCLEAR' in evidence['flag_codes']
    assert 'TENURE_RULE_NOT_CONFIGURED' in evidence['flag_codes']
    assert 'TERM_BELOW_CONFIGURED_MINIMUM' not in evidence['flag_codes']
    with pytest.raises(ValueError): ReviewPolicy(8)


def test_quotes_conflicts_and_independent_claims():
    raw = dict(RECORDED, institution_name='Visible institute',
               holding_pattern='Jointly held: Institute and AICTE', lien_clause='No regulatory lien recorded')
    # Legacy false versus positive quotation must go to review, not silently pick a winner.
    response, evidence = portal_response(json.dumps(raw), DEMO_POLICY)
    assert evidence['claims']['joint_holding'] is None
    assert evidence['claims']['lien'] is False
    assert response['fields']['depositor_name'] == 'Visible institute'
    assert any('CONFLICTING_JOINT_HOLDING' in warning for warning in response['warnings'])


@pytest.mark.parametrize('raw', [
    '{"deposit_amount": NaN}', '{"deposit_amount": true}', '{"deposit_amount":"-2"}',
    '{"deposit_amount":"1,234"}', '{"issue_date":"2026-02-30"}',
    '{"joint_holder_aicte_verified":"false"}', '{"fdr_number":"A","fdr_number":"B"}',
    '{"bank_confirmed":true}', 'prose instead of JSON',
])
def test_reject_bad_model_values(raw):
    with pytest.raises(ValueError): normalise(raw)


def test_date_boundary_is_calendar_based():
    fields = {'issue_date': '2020-02-29', 'maturity_date': '2028-02-28'}
    assert 'TERM_BELOW_CONFIGURED_MINIMUM' in scrutiny_flags(fields, {}, DEMO_POLICY)
    fields['maturity_date'] = '2028-02-29'
    assert 'TERM_BELOW_CONFIGURED_MINIMUM' not in scrutiny_flags(fields, {}, DEMO_POLICY)
    fields['maturity_date'] = '2019-01-01'
    assert 'DOCUMENT_DATE_ORDER_INVALID' in scrutiny_flags(fields, {}, DEMO_POLICY)


def test_exact_portal_multipart_and_response():
    with client() as c:
        response = upload(c)
        assert response.status_code == 200
        assert set(response.json()) == {'fields', 'confidences', 'original_text', 'warnings'}
        assert set(response.json()['fields']) == set(service.FIELDS)
        assert upload(c, name='fdr_image').status_code == 422
        assert upload(c, model='different-model').status_code == 422
        assert c.post('/api/v1/extract-only', headers={'Authorization': 'wrong'}, content=b'bad').status_code == 401


def test_single_page_pdf_renders_and_multiple_pages_are_explicitly_rejected():
    sizes = []
    def infer(image):
        sizes.append(image.size)
        return json.dumps(RECORDED)
    with pymupdf.open() as pdf, client(infer) as c:
        pdf.new_page().insert_text((72, 72), 'FDR ONE')
        assert upload(c, pdf.tobytes(), 'application/pdf').status_code == 200
        assert sizes and sizes[0][0] * sizes[0][1] <= service.MAX_RENDER_PIXELS + 5000
        pdf.new_page()
        result = upload(c, pdf.tobytes(), 'application/pdf')
        assert result.status_code == 422 and 'single FDR receipt page' in result.text
        assert upload(c, b'not pdf', 'application/pdf').status_code == 422
        assert upload(c, png(), 'image/jpeg').status_code == 422
        assert upload(c, png(), 'text/plain').status_code == 422


def test_auth_and_size_checked_before_inference(monkeypatch):
    monkeypatch.setattr(service, 'MAX_BODY_BYTES', 512)
    calls = []
    with client(lambda image: calls.append(1)) as c:
        assert c.post('/api/v1/extract-only', content=b'x' * 513).status_code == 413
        assert c.post('/api/v1/extract-only', headers={'Authorization': ''}, content=b'x' * 513).status_code == 401
        assert not calls


def test_chunked_request_cannot_bypass_size_limit(monkeypatch):
    monkeypatch.setattr(service, 'MAX_BODY_BYTES', 32)
    app = create_app(lambda image: '{}', api_key=TOKEN)
    async def exercise():
        async def chunks():
            yield b'x' * 20
            yield b'x' * 20
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://worker') as c:
            return await c.post('/api/v1/extract-only', headers={'Authorization': 'Bearer ' + TOKEN}, content=chunks())
    assert asyncio.run(exercise()).status_code == 413


def test_busy_and_model_failures_do_not_leak_secrets():
    def broken(image): raise RuntimeError('private-token-do-not-return')
    with client(broken) as c:
        c.app.state.inference_slot.acquire()
        assert upload(c).status_code == 429
        c.app.state.inference_slot.release()
        result = upload(c)
        assert result.status_code == 503 and 'private-token' not in result.text
    with client(lambda image: '{"fdr_number":null}') as c:
        assert upload(c).status_code == 422


def test_holdout_manifest_is_reproducible_and_rejects_training_duplicates(tmp_path):
    train = tmp_path / 'training'; train.mkdir()
    (train / 'original.png').write_bytes(png())
    manifest = make_synthetic_holdout(tmp_path / 'holdout', count=4)
    rows, provenance = load_manifest(manifest, train)
    assert len(rows) == 4 and provenance['training_images_checked'] == 1
    assert all(r['kind'] == 'synthetic' for r in rows)
    with pytest.raises(ValueError, match='overwritten'):
        make_synthetic_holdout(tmp_path / 'holdout')
    Path(rows[0]['_path']).write_bytes(png())
    with pytest.raises(ValueError, match='duplicates a training'):
        load_manifest(manifest, train)


def test_metrics_penalize_invalid_and_invented_values(tmp_path):
    train = tmp_path / 'train'; train.mkdir(); (train / 'a.png').write_bytes(png())
    manifest = make_synthetic_holdout(tmp_path / 'heldout', count=3)
    rows, _ = load_manifest(manifest, train)
    perfect = [{'id': r['id'], 'fields': dict(r['fields']), 'seconds': 1,
                'flag_codes': list(scrutiny_flags(r['fields'], r['document_claims'], DEMO_POLICY))} for r in rows]
    assert metrics(rows, perfect, DEMO_POLICY)['exact_record_accuracy'] == 1
    perfect[0]['fields']['depositor_name'] = 'invented name'
    result = metrics(rows, perfect, DEMO_POLICY)
    assert result['invented_values_on_null_labels'] == 1
    perfect[1]['fields'] = None
    assert metrics(rows, perfect, DEMO_POLICY)['schema_valid_rate'] == 2 / 3
    # Exercise persistence using a stub, without claiming any real model score.
    score = evaluate(lambda image: 'invalid JSON', rows, DEMO_POLICY, tmp_path / 'results', 'stub')
    assert score['schema_valid_rate'] == 0
    assert (tmp_path / 'results' / 'stub_predictions.jsonl').is_file()
