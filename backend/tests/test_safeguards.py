from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, func, delete

from app import jobs
from app.audit import audit, event_digest
from app.config import settings
from app.extraction_engine import ExtractionFailure, ExtractionResult, validate_model_result
from app.models import AuditLog, AuditChainHead, Clearance, Document, Extraction, Instrument, ReleaseRequest, SecurityDeposit, User, Discrepancy, utcnow
from app.workflows import detect, release_blockers


@pytest.mark.parametrize('action', ['scrutiny_observation', 'extracted_field_corrected'])
def test_review_history_blocks_self_approval_after_role_change(env, action):
    factory, client = env
    with factory() as db:
        release = db.scalar(select(ReleaseRequest))
        deposit = db.get(SecurityDeposit, release.deposit_id)
        officer = db.scalar(select(User).where(User.email == 'officer@demo.local'))
        audit(db, officer, action, deposit.id, deposit.institution_id, after={'notes': 'Reviewed evidence'})
        # Even after reassignment and a later role change, the historical reviewer cannot approve.
        deposit.assigned_officer_id = None
        officer.role = 'authority'
        release_id, officer_id = release.id, officer.id
        db.commit()
    reviewer = client('officer')
    detail = next(r for r in reviewer.get('/api/releases').json() if r['id'] == release_id)
    assert officer_id in detail['reviewer_ids']
    result = reviewer.post(f'/api/releases/{release_id}/decision', json={'decision': 'approved', 'notes': 'Final decision after reassignment'})
    assert result.status_code == 403
    assert 'different approving authority' in result.text


def test_missing_clearance_and_inflight_receipt_block_release(env):
    factory, _ = env
    with factory() as db:
        release = db.scalar(select(ReleaseRequest))
        deposit = db.get(SecurityDeposit, release.deposit_id)
        db.execute(delete(Clearance).where(Clearance.release_id == release.id, Clearance.cell == 'Vigilance'))
        doc = db.scalar(select(Document).where(Document.deposit_id == deposit.id, Document.category == 'instrument'))
        doc.processing_status = 'processing'
        db.flush()
        blockers = release_blockers(db, deposit, release)
        assert 'Vigilance clearance is missing.' in blockers
        assert 'Instrument document extraction is still in progress.' in blockers


def queued_receipt(factory):
    with factory() as db:
        doc = db.scalar(select(Document).where(Document.category == 'instrument'))
        db.execute(delete(Extraction).where(Extraction.document_id == doc.id))
        doc.processing_status = 'queued'
        doc.processing_attempts = 0
        db.commit()
        return doc.id


def test_transient_extraction_retry_is_bounded_and_does_not_duplicate(env, monkeypatch):
    factory, _ = env
    doc_id = queued_receipt(factory)
    calls = []
    def infer(*args, **kwargs):
        # A separate write transaction succeeds: inference does not hold a database write lock.
        with factory() as db:
            audit(db, None, 'inference_test', 'test-extraction')
            db.commit()
        calls.append(1)
        if len(calls) == 1:
            raise ExtractionFailure('Temporary service failure', retryable=True)
        return ExtractionResult(method='test', provider='ocr', original_text='', fields={}, confidences={})
    monkeypatch.setattr(jobs, 'extract_document', infer)
    jobs.process_document(doc_id)
    with factory() as db:
        doc = db.get(Document, doc_id)
        assert doc.processing_status == 'queued' and doc.processing_attempts == 1
        assert doc.next_attempt_at is not None
    jobs.process_document(doc_id)
    assert len(calls) == 1  # Backoff is enforced even if a duplicate task arrives.
    with factory() as db:
        db.get(Document, doc_id).next_attempt_at = utcnow() - timedelta(seconds=1)
        db.commit()
    jobs.process_document(doc_id)
    jobs.process_document(doc_id)
    with factory() as db:
        doc = db.get(Document, doc_id)
        assert doc.processing_status == 'completed' and doc.processing_attempts == 2
        extraction = db.scalar(select(Extraction).where(Extraction.document_id == doc_id))
        assert extraction.document_sha256 == doc.sha256
        assert db.scalar(select(func.count()).select_from(Extraction).where(Extraction.document_id == doc_id)) == 1
    assert len(calls) == 2


def test_exhausted_worker_claim_recovers_to_failed(env):
    factory, _ = env
    doc_id = queued_receipt(factory)
    with factory() as db:
        doc = db.get(Document, doc_id)
        doc.processing_status = 'processing'
        doc.processing_token = 'interrupted-worker'
        doc.processing_attempts = settings.extraction_max_attempts
        doc.processing_started_at = utcnow() - timedelta(seconds=settings.extraction_lease_seconds + 1)
        db.commit()
    jobs.periodic_tick()
    with factory() as db:
        doc = db.get(Document, doc_id)
        assert doc.processing_status == 'failed' and doc.processing_token is None
        assert db.scalar(select(Discrepancy).where(Discrepancy.code == 'extraction_failed:' + doc_id))


def test_late_worker_cannot_overwrite_new_claim(env, monkeypatch):
    factory, _ = env
    doc_id = queued_receipt(factory)
    def infer(*args, **kwargs):
        with factory() as db:
            db.get(Document, doc_id).processing_token = 'new-worker'
            db.commit()
        return ExtractionResult(method='test', provider='ocr', original_text='', fields={}, confidences={})
    monkeypatch.setattr(jobs, 'extract_document', infer)
    jobs.process_document(doc_id)
    with factory() as db:
        assert db.get(Document, doc_id).processing_token == 'new-worker'
        assert db.scalar(select(Extraction).where(Extraction.document_id == doc_id)) is None


def test_extraction_errors_do_not_expose_internal_secrets(env, monkeypatch):
    factory, _ = env
    doc_id = queued_receipt(factory)
    def fail(*args, **kwargs):
        raise RuntimeError('private-token-123 and /private/document/path')
    monkeypatch.setattr(jobs, 'extract_document', fail)
    jobs.process_document(doc_id)
    with factory() as db:
        doc = db.get(Document, doc_id)
        assert doc.processing_status == 'failed'
        assert 'private-token' not in doc.processing_error


def test_one_paisa_difference_is_flagged(env):
    factory, _ = env
    with factory() as db:
        inst = db.scalar(select(Instrument).where(Instrument.number == 'MATCH-001'))
        doc = db.scalar(select(Document).where(Document.instrument_id == inst.id, Document.category == 'instrument'))
        extraction = db.scalar(select(Extraction).where(Extraction.document_id == doc.id))
        extraction.fields = {**extraction.fields, 'amount': str(inst.amount - Decimal('0.01'))}
        db.flush()
        detect(db, db.get(SecurityDeposit, inst.deposit_id))
        assert db.scalar(select(Discrepancy).where(Discrepancy.code == 'mismatch_amount:' + doc.id))


def test_audit_concurrent_writers_and_rollback(env):
    factory, _ = env
    def append(index):
        with factory() as db:
            audit(db, None, 'concurrent_test', 'shared-test', after={'index': index})
            db.commit()
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(append, range(9)))
    with factory() as db:
        entries = db.scalars(select(AuditLog).where(AuditLog.entity_id == 'shared-test').order_by(AuditLog.created_at)).all()
        assert len(entries) == 9
        previous = ''
        for entry in entries:
            assert entry.previous_hash == previous and entry.event_hash == event_digest(entry)
            previous = entry.event_hash
        assert db.get(AuditChainHead, 'shared-test').event_hash == previous
        audit(db, None, 'rolled_back', 'shared-test')
        db.rollback()
        assert db.get(AuditChainHead, 'shared-test').event_hash == previous
        assert db.scalar(select(AuditLog).where(AuditLog.action == 'rolled_back')) is None


@pytest.mark.parametrize('payload', [
    {'fields': {'amount': 'NaN'}},
    {'fields': {'bank': 'Test', 'bank_confirmed': True}},
    {'fields': {'bank': 'Test'}, 'confidences': {'amount': 0.8}},
    {'fields': {'bank': 'Test'}, 'confidences': {'bank': 1.5}},
])
def test_future_model_adapter_rejects_untrusted_shapes(payload):
    with pytest.raises(ExtractionFailure):
        validate_model_result(payload, 'vlm_http')
