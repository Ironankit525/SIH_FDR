"""Validated extraction providers. Model output is evidence, never bank approval."""
import importlib
import json
from datetime import date
from decimal import Decimal
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .config import settings
from .extraction import extract_text, structure

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
                if response.status_code == 429 or response.status_code >= 500:
                    raise ExtractionFailure('The VLM service is temporarily unavailable. Extraction will be retried.', retryable=True)
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


def extract_document(data, content_type, *, provider=None):
    provider = provider or settings.extraction_provider
    if provider == 'ocr':
        text, method = extract_text(data, content_type)
        fields, confidences = structure(text, method)
        return ExtractionResult(method=method, provider='ocr', original_text=text, fields=fields, confidences=confidences)
    if provider == 'vlm_http':
        return http_extract(data, content_type)
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
        return validate_model_result(payload, 'vlm_local')
    raise ExtractionFailure('The extraction provider is not supported.')
