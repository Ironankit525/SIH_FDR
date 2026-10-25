"""Preserve the existing local database and keys, then recreate fictional fixtures."""
import argparse
import datetime
import socket
import subprocess
import os
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--confirm-reset", action="store_true", help="Archive the current local demo and create a clean one")
args = parser.parse_args()
if not args.confirm_reset:
    parser.error("Pass --confirm-reset to archive the current local demo and start fresh.")
root = Path(__file__).resolve().parents[1]
backend_env = root / "backend/.env"
if os.environ.get("DATABASE_URL") or os.environ.get("STORAGE_BACKEND") or backend_env.exists():
    raise SystemExit("This reset helper supports only the default unconfigured local mode. Preserve and explicitly review custom backend configuration before resetting.")
with socket.socket() as sock:
    if sock.connect_ex(("127.0.0.1", 8000)) == 0:
        raise SystemExit("Stop the backend before resetting the local demo.")
data = root / "backend/.data"
if data.exists():
    archive = root / "backend" / (".data-backup-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    data.rename(archive)
    print(f"Previous database, documents and keys preserved in {archive.name}")
python = root / ".venv/bin/python"
subprocess.run([str(python), "-m", "alembic", "upgrade", "head"], cwd=root / "backend", check=True)
subprocess.run([str(python), "-m", "app.seed"], cwd=root / "backend", check=True)
