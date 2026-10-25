"""Environment configuration. Lightweight development never starts Docker."""
import json
import os
import secrets
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite:///./.data/depositflow.db"
    storage_backend: str = "local"
    storage_path: str = ".data/documents"
    storage_encryption_key: str = ""
    secret_key: str = ""
    s3_endpoint: str = "http://minio:9000"
    s3_bucket: str = "depositflow-private"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    redis_url: str = "redis://redis:6379/0"
    job_mode: str = "local"
    clamav_host: str = ""
    clamav_port: int = 3310
    require_malware_scan: bool = False
    cookie_secure: bool = False
    frontend_origin: str = "http://localhost:5173"
    demo_password: str = ""
    max_upload_bytes: int = 10 * 1024 * 1024
    extraction_provider: Literal['ocr', 'vlm_http', 'vlm_local'] = 'ocr'
    vlm_endpoint: str = ''
    vlm_api_key: SecretStr = SecretStr('')
    vlm_model: str = ''
    vlm_model_version: str = ''
    vlm_local_callable: str = ''
    vlm_timeout_seconds: int = Field(default=90, ge=1, le=300)
    extraction_max_attempts: int = Field(default=3, ge=1, le=5)
    extraction_lease_seconds: int = Field(default=900, ge=600, le=3600)
    forensic_ocr_check: bool = True


settings = Settings()
Path(".data").mkdir(exist_ok=True, mode=0o700)
if settings.environment == "production":
    if not settings.secret_key or not settings.storage_encryption_key:
        raise RuntimeError("Production requires SECRET_KEY and STORAGE_ENCRYPTION_KEY")
    if not settings.cookie_secure or not settings.require_malware_scan:
        raise RuntimeError("Production requires secure cookies and malware scanning")
else:
    path = Path(".data/local-secrets.json")
    if not path.exists():
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
            json.dump({"secret_key": secrets.token_urlsafe(48), "storage_encryption_key": Fernet.generate_key().decode()}, f)
    values = json.loads(path.read_text())
    settings.secret_key = settings.secret_key or values["secret_key"]
    settings.storage_encryption_key = settings.storage_encryption_key or values["storage_encryption_key"]
