"""Private encrypted object storage; no user-supplied object paths."""
import hashlib
import io
import socket
import struct
from pathlib import Path
from uuid import uuid4

import pymupdf as fitz
from cryptography.fernet import Fernet
from fastapi import HTTPException
from PIL import Image
from .config import settings

Image.MAX_IMAGE_PIXELS = 20_000_000


def validate_file(data, filename):
    if not data or len(data) > settings.max_upload_bytes:
        raise HTTPException(422, "Upload a nonempty PDF, PNG or JPEG of at most 10 MB")
    suffix = Path(filename).suffix.lower()
    try:
        if data.startswith(b"%PDF-") and suffix == ".pdf":
            with fitz.open(stream=data, filetype="pdf") as doc:
                if doc.is_encrypted or not 1 <= len(doc) <= 15:
                    raise ValueError("Encrypted PDFs or PDFs with more than 15 pages are not supported")
                if doc.embfile_count():
                    for name in doc.embfile_names():
                        if name in ("Content Credentials", "c2pa") or name.lower().endswith(".c2pa"):
                            continue
                        ext = Path(name).suffix.lower()
                        if ext in (".exe", ".js", ".vbs", ".bat", ".cmd", ".scr", ".sh", ".py", ".bin", ".msi", ".jar") or not ext:
                            raise ValueError("Active or executable attachments are not permitted")
                for xref in range(1, doc.xref_length()):
                    obj = doc.xref_object(xref)
                    if any(term in obj for term in ("/JavaScript", "/JS", "/Launch", "/RichMedia")):
                        raise ValueError("Active PDF content is not permitted")
            mime = "application/pdf"
        elif suffix in (".png", ".jpg", ".jpeg"):
            with Image.open(io.BytesIO(data)) as im:
                if im.format not in ("PNG", "JPEG") or im.width * im.height > Image.MAX_IMAGE_PIXELS:
                    raise ValueError("Unsupported image")
                mime = "image/png" if im.format == "PNG" else "image/jpeg"
                if (mime == "image/png") != (suffix == ".png"):
                    raise ValueError("Extension does not match file content")
                im.verify()
        else:
            raise ValueError("Only genuine PDF, PNG or JPEG files are supported")
    except Exception as exc:
        raise HTTPException(422, "Invalid or unsafe document: " + str(exc)[:160])
    scan_status = "structure_checked_only"
    if settings.clamav_host:
        try:
            with socket.create_connection((settings.clamav_host, settings.clamav_port), timeout=15) as sock:
                sock.sendall(b"zINSTREAM\0")
                for offset in range(0, len(data), 65536):
                    chunk = data[offset:offset + 65536]
                    sock.sendall(struct.pack("!I", len(chunk)) + chunk)
                sock.sendall(struct.pack("!I", 0))
                result = sock.recv(1024)
                if b"OK" not in result:
                    raise HTTPException(422, "Document failed malware scanning")
            scan_status = "malware_scanned"
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "Malware scanner unavailable; upload was not accepted")
    elif settings.require_malware_scan:
        raise HTTPException(503, "Malware scanning must be configured before accepting uploads")
    return mime, scan_status


class ObjectStore:
    def __init__(self):
        self.cipher = Fernet(settings.storage_encryption_key.encode())

    def s3(self):
        import boto3
        return boto3.client("s3", endpoint_url=settings.s3_endpoint, aws_access_key_id=settings.s3_access_key,
                            aws_secret_access_key=settings.s3_secret_key, region_name=settings.s3_region)

    def put(self, data):
        key = str(uuid4()) + ".encrypted"
        encrypted = self.cipher.encrypt(data)
        if settings.storage_backend == "s3":
            self.s3().put_object(Bucket=settings.s3_bucket, Key=key, Body=encrypted, ContentType="application/octet-stream")
        else:
            root = Path(settings.storage_path)
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            (root / key).write_bytes(encrypted)
            (root / key).chmod(0o600)
        return key

    def get(self, key):
        if Path(key).name != key:
            raise ValueError("Invalid object key")
        if settings.storage_backend == "s3":
            encrypted = self.s3().get_object(Bucket=settings.s3_bucket, Key=key)["Body"].read()
        else:
            encrypted = (Path(settings.storage_path) / key).read_bytes()
        return self.cipher.decrypt(encrypted)


store = ObjectStore()
