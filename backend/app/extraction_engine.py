"""Validated extraction providers. Model output is evidence, never bank approval."""
import importlib
import json
import logging
from datetime import date
from decimal import Decimal
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .config import settings
from .consistency import maturity_problem
from .extraction import candidates, extract_text, ocr_text, pdf_text_layer, structure
from .matching import same_amount, same_bank, same_name, same_text

log = logging.getLogger(__name__)

Text = Annotated[str, Field(strict=True, min_length=1, max_length=200)]
Confidence = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]


class ExtractedFields(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    bank: Text | None = None
    number: Text | None = None
    depositor_name: Text | None = None
    amount: Decimal | None = Field(default=None, gt=0, le=1_000_000_000_000, max_digits=15, decimal_places=2, allow_inf_nan=False)
    issue_date: date | None = None
    maturity_date: date | None = None
    lien: Text | None = None
    rate: Decimal | None = Field(default=None, gt=0, lt=100, max_digits=6, decimal_places=3, allow_inf_nan=False)
    maturity_value: Decimal | None = Field(default=None, gt=0, le=1_000_000_000_000, max_digits=15, decimal_places=2, allow_inf_nan=False)


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fields: ExtractedFields
    confidences: dict[str, Confidence] = Field(default_factory=dict)
    original_text: str = Field(default='', strict=True, max_length=200000)
    warnings: list[Annotated[str, Field(strict=True, max_length=500)]] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def validate_confidences(self):
        fields = self.fields.model_dump(exclude_none=True)
        if not fields:
            raise ValueError('The model returned no extracted fields')
        if set(self.confidences) - fields.keys():
            raise ValueError('Confidence must refer to a field actually extracted')
        return self


class ExtractionResult(BaseModel):
    method: str
    provider: str
    original_text: str
    fields: dict
    confidences: dict
    model_name: str | None = None
    model_version: str | None = None
    warnings: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)
    # Which stages ran and why the cascade moved on. Kept in the audit trail, not in the extraction row.
    stages: list[dict] = Field(default_factory=list)


class ExtractionFailure(Exception):
    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def validate_model_result(payload, provider):
    try:
        response = ModelResponse.model_validate(payload)
    except (ValidationError, TypeError, ValueError):
        raise ExtractionFailure('The VLM returned an invalid extraction. An administrator must check the model response format.') from None
    # JSON dates and decimal strings keep source values exact and independently reviewable.
    fields = response.fields.model_dump(mode='json', exclude_none=True)
    return ExtractionResult(method='trained_vlm', provider=provider, fields=fields,
                            original_text=response.original_text, confidences=response.confidences,
                            model_name=settings.vlm_model or None, model_version=settings.vlm_model_version or None,
                            warnings=response.warnings)


def http_extract(data, content_type):
    url = urlsplit(settings.vlm_endpoint)
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.fragment:
        raise ExtractionFailure('The VLM endpoint is not configured correctly. Contact an administrator.')
    if settings.environment == 'production' and url.scheme != 'https':
        raise ExtractionFailure('The production VLM endpoint must use HTTPS.')
    if not settings.vlm_model:
        raise ExtractionFailure('Configure the trained VLM model name before extracting documents.')
    key = settings.vlm_api_key.get_secret_value()
    headers = {'Authorization': 'Bearer ' + key} if key else {}
    suffix = '.pdf' if content_type == 'application/pdf' else '.png' if content_type == 'image/png' else '.jpg'
    try:
        with httpx.Client(timeout=httpx.Timeout(settings.vlm_timeout_seconds, connect=10),
                          follow_redirects=False, trust_env=False) as client:
            with client.stream('POST', settings.vlm_endpoint, headers=headers,
                               data={'model': settings.vlm_model},
                               files={'file': ('document' + suffix, data, content_type)}) as response:
                if response.status_code in (401, 403):
                    raise ExtractionFailure(
                        'The VLM service could not authenticate this backend. Reconnect it using the current '
                        'worker credentials, restart the backend, and retry extraction.')
                if response.headers.get('ngrok-error-code') == 'ERR_NGROK_3200':
                    raise ExtractionFailure(
                        'The Colab extraction tunnel is offline. Restart the worker and tunnel, update the '
                        'backend connection settings if they changed, and retry extraction.', retryable=True)
                if response.status_code == 429 or response.status_code >= 500:
                    raise ExtractionFailure('The VLM service is temporarily unavailable. Extraction will be retried.', retryable=True)
                if response.status_code == 404:
                    raise ExtractionFailure(
                        'The VLM extraction endpoint was not found. Check the current worker address and '
                        '/api/v1/extract-only path, restart the backend after updating its settings, and retry.')
                if response.status_code != 200:
                    raise ExtractionFailure('The VLM service rejected the request. Check its configuration and supported document formats.')
                raw = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    raw.extend(chunk)
                    if len(raw) > 512 * 1024:
                        raise ExtractionFailure('The VLM response exceeded the allowed size.')
                payload = json.loads(raw)
    except httpx.RequestError:
        raise ExtractionFailure('The VLM service could not be reached. Extraction will be retried.', retryable=True) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ExtractionFailure('The VLM did not return valid JSON. Contact an administrator.') from None
    return validate_model_result(payload, 'vlm_http')


# What an FDR receipt must state before a cheaper stage may stop the cascade.
CORE_FIELDS = ('bank', 'number', 'amount', 'issue_date', 'maturity_date')
MIN_TEXT_LAYER = 25  # characters; below this a PDF is treated as a scan


def vlm_configured():
    return bool(settings.vlm_endpoint and settings.vlm_model)


def shortfall(fields, confidences):
    """Why a stage's result is not good enough to stop the cascade; empty when it is."""
    reasons = []
    missing = [key for key in CORE_FIELDS if key not in fields]
    if missing:
        reasons.append('missing ' + ', '.join(missing))
    weak = [key for key in CORE_FIELDS if key in fields and confidences.get(key, 0) < settings.extraction_min_confidence]
    if weak:
        reasons.append('low confidence in ' + ', '.join(weak))
    if not missing and fields.get('maturity_value'):
        try:
            problem = maturity_problem(fields['amount'], fields['maturity_value'], fields['issue_date'], fields['maturity_date'], fields.get('rate'))
        except (ValueError, TypeError):
            problem = 'the figures could not be compared'
        if problem:
            reasons.append('receipt figures do not agree')
    return reasons


def _quality(result):
    present = [key for key in CORE_FIELDS if key in result.fields]
    return len(present), sum(result.confidences.get(key, 0) for key in present)


def _from_text(text, method, provider):
    fields, confidences = structure(text, method)
    return ExtractionResult(method=method, provider=provider, original_text=text, fields=fields, confidences=confidences)


def _finish(result, stages, sources=None):
    notes = [f"{s['stage']}: {s['outcome']}" + (f" ({'; '.join(s['reasons'])})" if s.get('reasons') else '')
             for s in stages if s['outcome'] not in ('accepted', 'not_applicable')]
    if notes:
        result.warnings = [*result.warnings, 'Extraction moved past earlier stages. ' + ' | '.join(notes)]
    result.stages = stages
    snapshots, values = [], {}
    for source in sources or [result]:
        snapshot = {'provider': source.provider, 'method': source.method,
                    'fields': dict(source.fields), 'confidences': dict(source.confidences),
                    'original_text': source.original_text}
        alternatives = ({key: options[0] for key, options in candidates(source.original_text).items()}
                        if not source.provider.startswith('vlm') else {})
        snapshot['candidates'] = alternatives
        snapshots.append(snapshot)
        for field, value in source.fields.items():
            for candidate in alternatives.get(field, [value]):
                values.setdefault(field, []).append({'source': source.provider, 'value': candidate})
    conflicts = []
    for field, observations in values.items():
        compare = {'amount': same_amount, 'maturity_value': same_amount, 'rate': same_amount,
                   'bank': same_bank, 'depositor_name': same_name}.get(field, same_text)
        if any(not compare(observations[0]['value'], item['value']) for item in observations[1:]):
            conflicts.append({'field': field, 'observations': observations})
    # Models need not provide confidence scores. Missing fields and disagreements
    # still require review; model confidence is not evidence of authenticity.
    reasons = shortfall(result.fields, result.confidences if not result.provider.startswith('vlm') else
                        {key: 1 for key in result.fields})
    result.evidence = {'status': 'conflict' if conflicts else 'incomplete' if reasons else 'complete',
                       'reasons': reasons, 'sources': snapshots, 'conflicts': conflicts, 'stages': stages}
    return result


def cascade_extract(data, content_type):
    """PDF text layer, then Tesseract, then the Colab VLM; each stage runs only if the one before fell short.

    The forensic text-layer-versus-OCR check reads the original file itself (see jobs.py), so falling back
    to OCR never discards the evidence it needs. Model output stays evidence, never bank approval."""
    stages, partials, sources = [], [], []

    def attempt(stage, read):
        try:
            result = read()
        except Exception:
            stages.append({'stage': stage, 'outcome': 'failed'})
            return None
        sources.append(result)
        reasons = shortfall(result.fields, result.confidences)
        stages.append({'stage': stage, 'outcome': 'insufficient' if reasons else 'accepted', 'reasons': reasons,
                       'fields': sorted(result.fields), 'text_chars': len(result.original_text)})
        if reasons:
            partials.append(result)
            return None
        return result

    if content_type == 'application/pdf':
        try:
            layer = pdf_text_layer(data)
        except Exception:
            layer = ''
        if len(layer) >= MIN_TEXT_LAYER:
            done = attempt('pdf_text', lambda: _from_text(layer, 'embedded_pdf_text', 'pdf_text'))
            if done:
                return _finish(done, stages, sources)
        else:
            stages.append({'stage': 'pdf_text', 'outcome': 'no_text_layer', 'text_chars': len(layer)})
    else:
        stages.append({'stage': 'pdf_text', 'outcome': 'not_applicable'})

    def read_ocr():
        text = ocr_text(data, content_type)
        if not text:
            raise ValueError('no text')
        return _from_text(text, 'tesseract_ocr', 'ocr')
    done = attempt('ocr', read_ocr)
    if done:
        return _finish(done, stages, sources)

    best = max(partials, key=_quality, default=None)
    if not vlm_configured():
        stages.append({'stage': 'vlm_http', 'outcome': 'skipped', 'reasons': ['VLM is not configured']})
        log.info('Extraction cascade stopped before the VLM: no worker is configured')
        if best is None:
            raise ExtractionFailure('Document extraction failed. Check readability and the configured extraction service, or request manual review.')
        return _finish(best, stages, sources)

    try:
        model = http_extract(data, content_type)
    except ExtractionFailure as failure:
        if failure.retryable:
            raise  # jobs.py retries within its bounded attempts and keeps the claim
        stages.append({'stage': 'vlm_http', 'outcome': 'failed', 'reasons': [str(failure)]})
        if best is None:
            raise
        return _finish(best, stages, sources)
    sources.append(model)
    stages.append({'stage': 'vlm_http', 'outcome': 'accepted', 'fields': sorted(model.fields)})
    if best is not None and _quality(best)[0] > _quality(model)[0]:
        stages[-1]['outcome'] = 'insufficient'
        stages[-1]['reasons'] = ['returned fewer core fields than the earlier stage']
        return _finish(best, stages, sources)
    return _finish(model, stages, sources)


def extract_document(data, content_type, *, provider=None):
    provider = provider or settings.extraction_provider
    if provider == 'cascade':
        return cascade_extract(data, content_type)
    if provider == 'ocr':
        text, method = extract_text(data, content_type)
        fields, confidences = structure(text, method)
        return _finish(ExtractionResult(method=method, provider='ocr', original_text=text, fields=fields, confidences=confidences), [])
    if provider == 'vlm_http':
        return _finish(http_extract(data, content_type), [])
    if provider == 'vlm_local':
        module, separator, name = settings.vlm_local_callable.partition(':')
        if not separator or not module or not name or not settings.vlm_model:
            raise ExtractionFailure('Configure the local VLM inference function and model name before extraction.')
        try:
            # Only the trusted server configuration selects executable code.
            infer = getattr(importlib.import_module(module), name)
            payload = infer(data, content_type)
        except Exception:
            raise ExtractionFailure('Local VLM inference failed. Check the model installation and inference function.') from None
        return _finish(validate_model_result(payload, 'vlm_local'), [])
    raise ExtractionFailure('The extraction provider is not supported.')
