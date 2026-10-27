"""The extraction cascade: PDF text layer, then Tesseract, then the Colab VLM, each only when the one before fell short."""
from datetime import timedelta

import pymupdf as fitz
import pytest
from sqlalchemy import select

from app import extraction_engine as engine, jobs
from app.config import settings
from app.extraction_engine import ExtractionFailure, ExtractionResult, cascade_extract
from app.models import AuditLog, Document, Extraction, utcnow
from test_safeguards import queued_receipt

RECEIPT = ("Bank: Demo National Bank\nBranch: Main\nFDR Number: CASC-001\nDepositor Name: Meridian Institute\n"
           "Amount: INR 3500000.00\nIssue Date: 2026-01-01\nMaturity Date: 2028-01-01\n")
PARTIAL = "Amount: INR 3500000.00\nFDR Number: CASC-001\n"  # no bank and no dates


def text_pdf(text):
    doc = fitz.open(); page = doc.new_page()
    page.insert_textbox(fitz.Rect(50, 60, 550, 700), text, fontsize=12)
    data = doc.tobytes(); doc.close()
    return data


def scanned_pdf():
    doc = fitz.open(); page = doc.new_page()
    page.draw_rect(fitz.Rect(100, 100, 300, 200), fill=(0.8, 0.8, 0.8))  # drawn shapes only: no text layer
    data = doc.tobytes(); doc.close()
    return data


def vlm_result():
    return ExtractionResult(method='trained_vlm', provider='vlm_http', original_text='', confidences={'amount': 0.9},
                            fields={'bank': 'Demo National Bank', 'number': 'CASC-001', 'amount': '3500000.00',
                                    'issue_date': '2026-01-01', 'maturity_date': '2028-01-01'})


@pytest.fixture
def stages(monkeypatch):
    """Records which stages are reached. Each test says what OCR reads and whether a worker is configured."""
    calls = {'ocr': 0, 'vlm': 0}

    def configure(ocr_text=None, vlm=None, worker=False):
        def ocr(data, content_type):
            calls['ocr'] += 1
            if ocr_text is None:
                raise AssertionError('OCR must not run')
            return ocr_text
        def http(data, content_type):
            calls['vlm'] += 1
            if vlm is None:
                raise AssertionError('The VLM must not be called')
            if isinstance(vlm, Exception):
                raise vlm
            return vlm
        monkeypatch.setattr(engine, 'ocr_text', ocr)
        monkeypatch.setattr(engine, 'http_extract', http)
        monkeypatch.setattr(settings, 'vlm_endpoint', 'https://worker.example/api/v1/extract-only' if worker else '')
        monkeypatch.setattr(settings, 'vlm_model', 'test-model' if worker else '')
        return calls
    return configure


def test_selectable_pdf_stops_at_the_text_layer(stages):
    calls = stages()
    result = cascade_extract(text_pdf(RECEIPT), 'application/pdf')
    assert (result.provider, result.method) == ('pdf_text', 'embedded_pdf_text')
    assert result.fields['number'] == 'CASC-001' and result.fields['amount'] == 3500000
    assert calls == {'ocr': 0, 'vlm': 0}
    assert [s['stage'] for s in result.stages] == ['pdf_text'] and result.stages[0]['outcome'] == 'accepted'
    assert result.warnings == []


def test_scanned_pdf_stops_at_ocr(stages):
    calls = stages(ocr_text=RECEIPT, worker=True)  # a worker exists but is never needed
    result = cascade_extract(scanned_pdf(), 'application/pdf')
    assert (result.provider, result.method) == ('ocr', 'tesseract_ocr')
    assert result.fields['maturity_date'] == '2028-01-01'
    assert calls == {'ocr': 1, 'vlm': 0}
    assert [(s['stage'], s['outcome']) for s in result.stages] == [('pdf_text', 'no_text_layer'), ('ocr', 'accepted')]


def test_image_goes_straight_to_ocr(stages):
    calls = stages(ocr_text=RECEIPT)
    result = cascade_extract(b'not read: OCR is stubbed', 'image/png')
    assert result.provider == 'ocr' and calls['ocr'] == 1
    assert result.stages[0] == {'stage': 'pdf_text', 'outcome': 'not_applicable'}


def test_incomplete_text_layer_falls_through_to_ocr(stages):
    calls = stages(ocr_text=RECEIPT)
    result = cascade_extract(text_pdf(PARTIAL), 'application/pdf')
    assert result.provider == 'ocr' and calls['ocr'] == 1
    first = result.stages[0]
    assert first['outcome'] == 'insufficient' and 'bank' in first['reasons'][0]
    assert 'moved past earlier stages' in result.warnings[0]


def test_noisy_receipt_escalates_to_the_vlm(stages):
    calls = stages(ocr_text=PARTIAL, vlm=vlm_result(), worker=True)
    result = cascade_extract(text_pdf(PARTIAL), 'application/pdf')
    assert (result.provider, result.method) == ('vlm_http', 'trained_vlm')
    assert result.fields['bank'] == 'Demo National Bank'
    assert calls == {'ocr': 1, 'vlm': 1}
    assert [(s['stage'], s['outcome']) for s in result.stages] == [('pdf_text', 'insufficient'), ('ocr', 'insufficient'), ('vlm_http', 'accepted')]


def test_unconfigured_vlm_returns_the_best_partial_result(stages):
    calls = stages(ocr_text=PARTIAL, worker=False)
    result = cascade_extract(scanned_pdf(), 'application/pdf')
    assert result.provider == 'ocr' and sorted(result.fields) == ['amount', 'number']
    assert calls['vlm'] == 0
    assert result.stages[-1] == {'stage': 'vlm_http', 'outcome': 'skipped', 'reasons': ['VLM is not configured']}


def test_nothing_readable_and_no_worker_fails(stages):
    stages(ocr_text='', worker=False)
    with pytest.raises(ExtractionFailure) as failure:
        cascade_extract(scanned_pdf(), 'application/pdf')
    assert not failure.value.retryable


def test_a_vlm_that_finds_less_does_not_replace_a_better_partial(stages):
    thin = ExtractionResult(method='trained_vlm', provider='vlm_http', original_text='', confidences={}, fields={'amount': '3500000.00'})
    stages(ocr_text='Bank: Demo National Bank\nFDR Number: CASC-001\nAmount: INR 3500000.00\n', vlm=thin, worker=True)
    result = cascade_extract(scanned_pdf(), 'application/pdf')
    assert result.provider == 'ocr'
    assert result.stages[-1]['outcome'] == 'insufficient'


def test_a_permanent_vlm_failure_keeps_the_partial_result(stages):
    stages(ocr_text=PARTIAL, vlm=ExtractionFailure('The VLM service could not authenticate this backend.'), worker=True)
    result = cascade_extract(scanned_pdf(), 'application/pdf')
    assert result.provider == 'ocr'
    assert result.stages[-1]['outcome'] == 'failed'


def test_figures_that_disagree_do_not_stop_the_cascade(stages):
    calls = stages(ocr_text=RECEIPT, worker=False)
    inconsistent = RECEIPT + 'Maturity Value: INR 3500001.00\n'  # not above a plausible return on the principal
    result = cascade_extract(text_pdf(inconsistent), 'application/pdf')
    assert result.stages[0]['outcome'] == 'insufficient' and 'figures do not agree' in result.stages[0]['reasons'][0]
    assert calls['ocr'] == 1


# Through the job runner: the winning provider is stored and a transient VLM outage uses the bounded retry.

def test_job_records_the_winning_stage_and_still_runs_forensics(env, monkeypatch):
    factory, _ = env
    monkeypatch.setattr(settings, 'extraction_provider', 'cascade')
    doc_id = queued_receipt(factory)
    jobs.process_document(doc_id)
    with factory() as db:
        doc = db.get(Document, doc_id)
        extraction = db.scalar(select(Extraction).where(Extraction.document_id == doc_id))
        assert doc.processing_status == 'completed'
        assert extraction.provider == 'pdf_text' and extraction.method == 'embedded_pdf_text'
        assert doc.forensics.get('ocr_crosscheck') and doc.forensics['structure']['text_layer']
        event = db.scalars(select(AuditLog).where(AuditLog.action == 'ocr_completed').order_by(AuditLog.created_at.desc())).first()
        assert event.after['provider'] == 'pdf_text' and event.after['stages'][0]['outcome'] == 'accepted'


def test_unreachable_worker_retries_within_the_attempt_limit(env, monkeypatch):
    factory, _ = env
    monkeypatch.setattr(settings, 'extraction_provider', 'cascade')
    monkeypatch.setattr(settings, 'vlm_endpoint', 'https://worker.example/api/v1/extract-only')
    monkeypatch.setattr(settings, 'vlm_model', 'test-model')
    monkeypatch.setattr(engine, 'pdf_text_layer', lambda data: '')
    monkeypatch.setattr(engine, 'ocr_text', lambda data, content_type: PARTIAL)
    calls = []
    def unreachable(data, content_type):
        calls.append(1)
        raise ExtractionFailure('The VLM service could not be reached. Extraction will be retried.', retryable=True)
    monkeypatch.setattr(engine, 'http_extract', unreachable)
    doc_id = queued_receipt(factory)

    def run():
        with factory() as db:
            db.get(Document, doc_id).next_attempt_at = utcnow() - timedelta(seconds=1)
            db.commit()
        jobs.process_document(doc_id)
        with factory() as db:
            doc = db.get(Document, doc_id)
            return doc.processing_status, doc.processing_attempts

    jobs.process_document(doc_id)
    with factory() as db:
        assert (db.get(Document, doc_id).processing_status, db.get(Document, doc_id).processing_attempts) == ('queued', 1)
        assert db.scalar(select(Extraction).where(Extraction.document_id == doc_id)) is None  # the partial result is not saved
    assert run() == ('queued', 2)
    assert run() == ('failed', settings.extraction_max_attempts)
    assert len(calls) == settings.extraction_max_attempts


def test_supporting_documents_never_reach_the_vlm(env, monkeypatch):
    factory, _ = env
    monkeypatch.setattr(settings, 'extraction_provider', 'cascade')
    monkeypatch.setattr(settings, 'vlm_endpoint', 'https://worker.example/api/v1/extract-only')
    monkeypatch.setattr(settings, 'vlm_model', 'test-model')
    monkeypatch.setattr(engine, 'http_extract', lambda *a: (_ for _ in ()).throw(AssertionError('The VLM must not be called')))
    doc_id = queued_receipt(factory)
    with factory() as db:
        db.get(Document, doc_id).category = 'supporting'
        db.commit()
    jobs.process_document(doc_id)
    with factory() as db:
        extraction = db.scalar(select(Extraction).where(Extraction.document_id == doc_id))
        assert extraction.provider == 'ocr'
