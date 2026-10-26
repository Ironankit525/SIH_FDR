import asyncio
import hashlib
import secrets
import threading
from datetime import timedelta
from sqlalchemy import select, update, and_, or_
from .config import settings
from .db import SessionLocal
from .models import Document, Extraction, SecurityDeposit, utcnow
from .storage import store
from .extraction_engine import extract_document, ExtractionFailure
from .audit import audit
from . import forensics
from .workflows import detect, monitor, flag
from .risk import assess

_inference_slot = threading.BoundedSemaphore(1)


def process_document(document_id):
    # Keep local inference bounded without blocking request threads on a queue.
    if not _inference_slot.acquire(blocking=False):
        return
    try:
        _process_document(document_id)
    finally:
        _inference_slot.release()


def ready_condition(now):
    return or_(and_(Document.processing_status == 'queued',
                    or_(Document.next_attempt_at.is_(None), Document.next_attempt_at <= now)),
               and_(Document.processing_status == 'processing',
                    Document.processing_started_at <= now - timedelta(seconds=settings.extraction_lease_seconds)))


def _process_document(document_id):
    now, token = utcnow(), secrets.token_hex(24)
    with SessionLocal() as db:
        claimed = db.execute(update(Document).where(Document.id == document_id, ready_condition(now),
                             Document.processing_attempts < settings.extraction_max_attempts)
                             .values(processing_status='processing', processing_token=token,
                                     processing_started_at=now, next_attempt_at=None,
                                     processing_attempts=Document.processing_attempts + 1))
        if claimed.rowcount != 1:
            db.rollback()
            return
        doc = db.get(Document, document_id)
        deposit = db.get(SecurityDeposit, doc.deposit_id)
        audit(db, None, 'extraction_started', deposit.id, deposit.institution_id,
              after={'document_id': doc.id, 'attempt': doc.processing_attempts})
        db.commit()
        storage_key, mime, digest, category = doc.storage_key, doc.content_type, doc.sha256, doc.category

    # Inference and storage I/O run outside a database transaction.
    result, failure, report = None, None, {}
    try:
        data = store.get(storage_key)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ExtractionFailure('Document integrity verification failed. Contact an administrator.')
        result = extract_document(data, mime, provider='ocr' if category != 'instrument' else None)
        if category == 'instrument':
            try:
                report = forensics.inspect(data, mime, ocr=settings.forensic_ocr_check)
            except Exception:
                report = {"version": forensics.VERSION, "signals": [], "error": "Integrity checks could not run on this file."}
    except Exception as exc:
        failure = exc if isinstance(exc, ExtractionFailure) else ExtractionFailure(
            'Document extraction failed. Check readability and the configured extraction service, or request manual review.')

    with SessionLocal() as db:
        doc = db.scalar(select(Document).where(Document.id == document_id, Document.processing_token == token,
                         Document.processing_status == 'processing').with_for_update())
        if not doc:
            return  # Another worker recovered this expired claim; discard the late result.
        deposit = db.get(SecurityDeposit, doc.deposit_id)
        doc.processing_token = None
        if failure is None:
            if not db.scalar(select(Extraction.id).where(Extraction.document_id == doc.id)):
                db.add(Extraction(document_id=doc.id, document_sha256=digest, **result.model_dump(exclude={'stages'})))
            doc.processing_status, doc.processing_error, doc.forensics = 'completed', None, report
            audit(db, None, 'ocr_completed', deposit.id, deposit.institution_id,
                  after={'document_id': doc.id, 'method': result.method, 'provider': result.provider,
                         'model_name': result.model_name, 'model_version': result.model_version,
                         'document_sha256': digest, 'fields': list(result.fields), 'stages': result.stages})
            if doc.category == "instrument":
                detect(db, deposit)
        else:
            retry = failure.retryable and doc.processing_attempts < settings.extraction_max_attempts
            doc.processing_status = 'queued' if retry else 'failed'
            doc.processing_error = str(failure) if retry or not failure.retryable else 'Automatic extraction attempts finished. Retry after checking the extraction service, or request manual review.'
            doc.next_attempt_at = utcnow() + timedelta(seconds=15 * 2 ** (doc.processing_attempts - 1)) if retry else None
            audit(db, None, 'extraction_retry_scheduled' if retry else 'ocr_failed', deposit.id, deposit.institution_id,
                  after={'document_id': doc.id, 'attempt': doc.processing_attempts})
            if not retry and doc.category == 'instrument':
                flag(db, deposit, 'extraction_failed:' + doc.id,
                     'Instrument extraction failed. Review the original document and record how its details were checked.',
                     'warning', source='document_extraction', instrument_id=doc.instrument_id)
                assess(db, deposit)
        db.commit()


def periodic_tick():
    with SessionLocal() as db:
        now = utcnow()
        exhausted = db.scalars(select(Document).where(ready_condition(now),
                              Document.processing_attempts >= settings.extraction_max_attempts).with_for_update()).all()
        for doc in exhausted:
            doc.processing_status, doc.processing_token = 'failed', None
            doc.processing_error = 'Extraction stopped after repeated interrupted attempts. Retry or request manual review.'
            deposit = db.get(SecurityDeposit, doc.deposit_id)
            audit(db, None, 'extraction_attempts_exhausted', deposit.id, deposit.institution_id, after={'document_id': doc.id})
            if doc.category == 'instrument':
                flag(db, deposit, 'extraction_failed:' + doc.id, doc.processing_error, 'warning',
                     source='document_extraction', instrument_id=doc.instrument_id)
                assess(db, deposit)
        queued = db.scalars(select(Document.id).where(ready_condition(now), Document.processing_attempts < settings.extraction_max_attempts)
                            .order_by(Document.created_at).limit(10)).all()
        monitor(db)
    for document_id in queued:
        process_document(document_id)


async def local_scheduler():
    while True:
        await asyncio.sleep(5)
        try:
            await asyncio.to_thread(periodic_tick)
        except Exception:
            # Retained database queue is retried on the next tick. No document text is logged.
            import logging
            logging.getLogger(__name__).warning("Background tick failed; retained tasks will retry")


def dispatch(document_id, background_tasks):
    if settings.job_mode == "celery":
        from .worker import extract_job
        try:
            extract_job.delay(document_id)
        except Exception:
            pass  # The scheduled database queue sweep recovers broker publication failures.
    else:
        background_tasks.add_task(process_document, document_id)
