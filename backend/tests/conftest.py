import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.db import Base, get_db
from app.main import app
from app.config import settings
from app.seed import seed, DEMO_PASSWORD
from app import jobs
from app.security import _attempts


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings, "storage_path", str(tmp_path / "documents"))
    monkeypatch.setattr(settings, "job_mode", "local")
    monkeypatch.setattr(settings, "extraction_provider", "ocr")
    monkeypatch.setattr(settings, "require_malware_scan", False)
    monkeypatch.setattr(settings, "clamav_host", "")
    monkeypatch.setattr(jobs, "SessionLocal", factory)
    _attempts.clear()
    with factory() as db:
        seed(db)
    def override_db():
        with factory() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise
    app.dependency_overrides[get_db] = override_db
    clients = []
    def client(role="institution"):
        c = TestClient(app)
        clients.append(c)
        if role:
            result = c.post("/api/auth/login", json={"email": f"{role}@demo.local", "password": DEMO_PASSWORD})
            assert result.status_code == 200, result.text
            c.headers["X-CSRF-Token"] = c.cookies.get("df_csrf")
        return c
    yield factory, client
    for c in clients:
        c.close()
    app.dependency_overrides.clear()
    engine.dispose()
