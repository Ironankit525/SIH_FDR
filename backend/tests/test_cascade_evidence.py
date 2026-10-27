"""Regressions from receipt testing; source disagreement is review evidence, not fraud."""
import shutil

import pymupdf as fitz
import pytest
from sqlalchemy import select

from app import extraction_engine as engine, jobs
from app.config import settings
from app.extraction import candidates, structure
from app.models import Document, Extraction, Discrepancy, Instrument
from test_extraction_cascade import RECEIPT, scanned_pdf, text_pdf, vlm_result
from test_safeguards import queued_receipt


@pytest.mark.parametrize('text,amount', [
    ('Deposit Amount: INR|10000.00 for a period of 1(yrs)', 10000),
    ('Principal Amt: Rs. 7,00,000/-', 700000),
    ('Deposit Amount : Seven Lakh Only', 700000),
    ('Amount in words: Rupees Thirty Five Lakh Only', 3500000),
    ('Principal Amount: One Lakh Twenty Three Thousand Four Hundred Fifty Six Only', 123456),
])
def test_principal_formats(text, amount):
    assert structure(text, 'tesseract_ocr')[0]['amount'] == amount


@pytest.mark.parametrize('text', ['Maturity   Amount: INR 450000', 'Interest Amount: INR 10000',
                                      'Deposit Amount: Five Six Only', 'Deposit Amount: Seven lakh dollars',
                                      'Deposit Amount: INR 1000O00',
                                      'Stamp paper value: INR 220', 'Account Number: 700000'])
def test_other_figures_and_unrecognised_words_are_not_principal(text):
    assert 'amount' not in structure(text, 'tesseract_ocr')[0]


def test_digits_and_words_disagree_without_silently_replacing_evidence():
    text = 'Deposit Amount: INR 7000000\nAmount in words: Seven Lakh Only'
    assert candidates(text)['amount'][0] == [7000000, 700000]
    assert structure(text, 'tesseract_ocr')[1]['amount'] < settings.extraction_min_confidence


def configure(monkeypatch, text, result):
    monkeypatch.setattr(engine, 'pdf_text_layer', lambda data: '')
    monkeypatch.setattr(engine, 'ocr_text', lambda data, mime: text)
    monkeypatch.setattr(engine, 'http_extract', lambda data, mime: result)
    monkeypatch.setattr(settings, 'vlm_endpoint', 'https://worker.example/extract')
    monkeypatch.setattr(settings, 'vlm_model', 'test')


def test_ocr_vlm_amount_conflict_preserves_both_sources(monkeypatch):
    model = vlm_result(); model.fields['amount'] = '100000.00'
    configure(monkeypatch, 'Deposit Amount: INR|10000.00', model)
    result = engine.cascade_extract(scanned_pdf(), 'application/pdf')
    assert result.fields['amount'] == '100000.00'  # raw model evidence is not rewritten
    assert result.evidence['status'] == 'conflict'
    conflict = result.evidence['conflicts'][0]
    assert conflict == {'field': 'amount', 'observations': [{'source': 'ocr', 'value': 10000}, {'source': 'vlm_http', 'value': '100000.00'}]}
    assert result.evidence['sources'][0]['original_text'] == 'Deposit Amount: INR|10000.00'


def test_equivalent_decimal_formats_do_not_conflict(monkeypatch):
    configure(monkeypatch, 'Deposit Amount: INR 35,00,000.00', vlm_result())
    result = engine.cascade_extract(scanned_pdf(), 'application/pdf')
    assert result.evidence['status'] == 'complete'
    assert not result.evidence['conflicts']


def test_partial_model_output_is_incomplete(monkeypatch):
    model = vlm_result(); model.fields = {'bank': 'Demo National Bank'}
    configure(monkeypatch, 'Unstructured page text', model)
    result = engine.cascade_extract(scanned_pdf(), 'application/pdf')
    assert result.evidence['status'] == 'incomplete'
    assert 'amount' in result.evidence['reasons'][0]


def test_empty_ocr_after_permanent_model_failure_is_incomplete(monkeypatch):
    configure(monkeypatch, 'Unstructured page text', None)
    def fail(*args):
        raise engine.ExtractionFailure('Model rejected the request')
    monkeypatch.setattr(engine, 'http_extract', fail)
    result = engine.cascade_extract(scanned_pdf(), 'application/pdf')
    assert result.fields == {} and result.evidence['status'] == 'incomplete'
    assert result.evidence['stages'][-1]['outcome'] == 'failed'


def test_complete_ocr_still_keeps_a_conflicting_pdf_candidate(monkeypatch):
    monkeypatch.setattr(engine, 'ocr_text', lambda *args: RECEIPT)
    monkeypatch.setattr(engine, 'http_extract', lambda *args: pytest.fail('Complete OCR should not call VLM'))
    result = engine.cascade_extract(text_pdf('Deposit Amount: INR 5000000\nUnstructured receipt'), 'application/pdf')
    assert result.evidence['status'] == 'conflict'
    assert [s['provider'] for s in result.evidence['sources']] == ['pdf_text', 'ocr']


@pytest.mark.skipif(not shutil.which('tesseract'), reason='Tesseract is needed for a real OCR early-exit check')
def test_real_scanned_receipt_stops_at_ocr(monkeypatch):
    with fitz.open(stream=text_pdf(RECEIPT), filetype='pdf') as original:
        image = original[0].get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes('png')
    with fitz.open() as scan:
        page = scan.new_page(); page.insert_image(page.rect, stream=image)
        data = scan.tobytes()
    monkeypatch.setattr(engine, 'http_extract', lambda *args: pytest.fail('VLM must not run for a clear scan'))
    result = engine.cascade_extract(data, 'application/pdf')
    assert result.provider == 'ocr'
    assert result.evidence['status'] == 'complete'
    assert [s['outcome'] for s in result.stages] == ['no_text_layer', 'accepted']


def test_job_persists_disagreement_and_flags_it_even_when_declaration_matches_model(env, monkeypatch):
    factory, client = env
    model = vlm_result(); model.fields['amount'] = '100000.00'
    configure(monkeypatch, 'Deposit Amount: INR|10000.00', model)
    doc_id = queued_receipt(factory)
    with factory() as db:
        doc = db.get(Document, doc_id)
        deposit_id = doc.deposit_id
        db.get(Instrument, doc.instrument_id).amount = 100000
        db.commit()
    jobs.process_document(doc_id)
    with factory() as db:
        extraction = db.scalar(select(Extraction).where(Extraction.document_id == doc_id))
        assert extraction.evidence['status'] == 'conflict'
        task = db.scalar(select(Discrepancy).where(Discrepancy.code == 'extraction_conflict_amount:' + doc_id))
        assert task and task.status == 'open' and task.severity == 'high'
    response = client('institution').get('/api/deposits/' + deposit_id)
    assert response.status_code == 200
    saved = next(d for d in response.json()['documents'] if d['id'] == doc_id)
    assert saved['extraction']['evidence']['sources'][0]['fields']['amount'] == 10000
