"""Generate optional Compose secrets locally; never print their values."""
import base64
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
destination = root / ".env"
if destination.exists():
    raise SystemExit(".env already exists; preserved. Edit it explicitly if changes are needed.")
values = {"ENVIRONMENT": "development", "SECRET_KEY": secrets.token_urlsafe(48),
          "STORAGE_ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
          "POSTGRES_PASSWORD": secrets.token_urlsafe(32), "MINIO_ROOT_USER": "depositflow-local", "MINIO_ROOT_PASSWORD": secrets.token_urlsafe(32),
          "FRONTEND_ORIGIN": "http://localhost:5173", "DEMO_PASSWORD": "DemoFlow2026!", "COOKIE_SECURE": "false", "REQUIRE_MALWARE_SCAN": "false", "CLAMAV_HOST": ""}
with os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
    file.write("# Generated local demo configuration. Never commit this file.\n")
    for name, value in values.items():
        file.write(f"{name}={value}\n")
print("Created private .env for the optional Compose stack. No Docker services were started.")
