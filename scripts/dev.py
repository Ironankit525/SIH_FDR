"""Start the complete lightweight demo without Docker, Redis or MinIO."""
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main():
    if not PYTHON.exists() or not (ROOT / "frontend/node_modules").exists():
        raise SystemExit("Install dependencies first. See README: Lightweight setup.")
    for port in (8000, 5173):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} is in use. Stop the existing service before starting another demo.")
    subprocess.run([str(PYTHON), "-m", "alembic", "upgrade", "head"], cwd=ROOT / "backend", check=True)
    subprocess.run([str(PYTHON), "-m", "app.seed"], cwd=ROOT / "backend", check=True)
    processes = []
    try:
        processes.append(subprocess.Popen([str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"], cwd=ROOT / "backend"))
        processes.append(subprocess.Popen(["npm", "run", "dev", "--", "--host", "127.0.0.1"], cwd=ROOT / "frontend", start_new_session=True))
        print("\nDepositFlow: http://localhost:5173\nAPI documentation: http://127.0.0.1:8000/docs\nPress Ctrl+C to stop. Docker is not used.\n", flush=True)
        while all(p.poll() is None for p in processes):
            try:
                processes[0].wait(timeout=1)
            except subprocess.TimeoutExpired:
                continue
    except KeyboardInterrupt:
        pass
    finally:
        for index, process in enumerate(processes):
            if process.poll() is None:
                if index == 1 and os.name != "nt":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
