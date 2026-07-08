"""Fix 503/H12 (R3 · 2026-07-08) · generación de recomendaciones en background.

La generación fresca (~45s de IA) superaba el timeout de 30s del router de
Heroku → 503 al cliente aunque la generación completaba server-side. Ahora los
endpoints NUNCA llaman a la IA dentro del request: devuelven el cache vigente
o encolan la generación (BackgroundTasks) y responden `status="generating"`.

Contratos verificados:
- sin tests → `empty` en /me (B-010 intacto)
- sin cache → `generating` + la generación corre en background exactamente 1 vez
- lock activo → polling devuelve `generating` sin encolar duplicados
- fallo en background → 503 con detail (mismo contrato de error de siempre)
  y el siguiente request re-encola
- cache vigente → `ready` sin encolar nada
"""
from __future__ import annotations

import time
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import recommendations as rec_module


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    from app.db import database as dbmod
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)
    # El worker de background abre su PROPIA sesión vía el SessionLocal
    # importado en el módulo de recommendations — parchear también ahí.
    monkeypatch.setattr(rec_module, "SessionLocal", TestingSessionLocal)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    from app.db.models import Base
    Base.metadata.create_all(bind=engine)
    from app.main import app
    app.dependency_overrides[dbmod.get_db] = _override_get_db
    from app.core.rate_limiter import limiter
    limiter.reset()

    # estado limpio del guard entre tests
    rec_module._GENERATING.clear()
    rec_module._FAILURES.clear()

    with TestClient(app) as client:
        yield client, TestingSessionLocal
    app.dependency_overrides.clear()
    rec_module._GENERATING.clear()
    rec_module._FAILURES.clear()


def _student(client, email="rec.async@example.com", with_test=False, sessionmaker_=None):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Test2026!", "name": "Rec"},
    )
    assert r.status_code in (200, 201), r.text
    token = r.json()["access_token"]
    H = {"Authorization": f"Bearer {token}"}
    if with_test:
        from app.db.models import User, VocationalTestResult
        db = sessionmaker_()
        u = db.query(User).filter(User.email == email).first()
        db.add(VocationalTestResult(user_id=u.id, test_id="holland",
                                    answers={"h-r-1": 5}, scores={"R": 80}))
        db.commit()
        db.close()
    return H


def test_me_sin_tests_devuelve_empty(env):
    client, SL = env
    H = _student(client, "rec.empty@example.com")
    r = client.get("/api/v1/recommendations/me", headers=H)
    assert r.status_code == 200
    assert r.json()["status"] == "empty"


def test_generate_encola_y_corre_en_background(env, monkeypatch):
    client, SL = env
    H = _student(client, "rec.bg@example.com", with_test=True, sessionmaker_=SL)

    calls = []

    def _spy(db, user, limit=5, force_refresh=False):
        calls.append((str(user.id), limit, force_refresh))

    monkeypatch.setattr(rec_module, "generate_recommendations", _spy)

    r = client.post("/api/v1/recommendations/generate", headers=H, json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "generating"
    # TestClient ejecuta las BackgroundTasks al cerrar la respuesta:
    assert len(calls) == 1
    # el lock quedó liberado al terminar el worker
    assert not rec_module._GENERATING


def test_polling_con_lock_activo_no_duplica(env, monkeypatch):
    client, SL = env
    H = _student(client, "rec.lock@example.com", with_test=True, sessionmaker_=SL)

    calls = []
    monkeypatch.setattr(
        rec_module, "generate_recommendations",
        lambda *a, **k: calls.append(1),
    )

    # simular generación en curso
    from app.db.models import User
    db = SL()
    uid = str(db.query(User).filter(User.email == "rec.lock@example.com").first().id)
    db.close()
    rec_module._GENERATING[uid] = time.time()

    r = client.get("/api/v1/recommendations/me", headers=H)
    assert r.status_code == 200
    assert r.json()["status"] == "generating"
    assert calls == []  # no encoló un duplicado


def test_fallo_en_background_sale_como_503_y_reencola(env, monkeypatch):
    client, SL = env
    H = _student(client, "rec.fail@example.com", with_test=True, sessionmaker_=SL)

    from app.db.models import User
    db = SL()
    uid = str(db.query(User).filter(User.email == "rec.fail@example.com").first().id)
    db.close()
    rec_module._FAILURES[uid] = "la IA no respondió"

    r = client.get("/api/v1/recommendations/me", headers=H)
    assert r.status_code == 503
    assert "la IA no respondió" in r.json()["detail"]

    # el fallo se consumió → el siguiente request re-encola
    calls = []
    monkeypatch.setattr(rec_module, "generate_recommendations", lambda *a, **k: calls.append(1))
    r2 = client.get("/api/v1/recommendations/me", headers=H)
    assert r2.status_code == 200
    assert r2.json()["status"] == "generating"
    assert len(calls) == 1


def test_cache_vigente_responde_ready_sin_encolar(env, monkeypatch):
    client, SL = env
    H = _student(client, "rec.cache@example.com", with_test=True, sessionmaker_=SL)

    from datetime import datetime

    fake_row = types.SimpleNamespace(
        generated_at=datetime.utcnow(), profile_hash="abc123", recommendations_data=[]
    )
    monkeypatch.setattr(
        rec_module, "peek_recommendations_bundle",
        lambda db, user, limit=5: (None, [], fake_row),
    )
    called = []
    monkeypatch.setattr(rec_module, "generate_recommendations", lambda *a, **k: called.append(1))

    r = client.get("/api/v1/recommendations/me", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["cached"] is True
    assert called == []
