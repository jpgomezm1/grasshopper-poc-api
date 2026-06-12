"""Rate limit del endpoint público POST /lead-profile/submit.

Fix hardening: el endpoint es público (sin auth) e inserta filas en DB,
así que sin límite era spammeable. Sigue el patrón de los otros públicos
(login/register/parental-consent): dependencia ``rate_limit`` con límite
configurable (``settings.rate_limit_lead_submit`` · default 10/minute) y
scope propio para no compartir bucket con otros endpoints.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def app_with_db(monkeypatch):
    sqlite_url = "sqlite:///:memory:"
    engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    from app.db import database as dbmod
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)

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

    yield app, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _payload(email="lead@gh.example.com"):
    return {
        "answers": {"q2_free_time": "Aprender algo nuevo online"},
        "contact": {"name": "Lead Test", "email": email},
    }


def test_submit_sigue_funcionando_y_persiste(app_with_db):
    app, SessionLocal = app_with_db
    with TestClient(app) as client:
        r = client.post("/api/v1/lead-profile/submit", json=_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["profile_type"]
    assert body["profile_name"]

    from app.db.models import LeadProfile
    db = SessionLocal()
    try:
        leads = db.query(LeadProfile).all()
        assert len(leads) == 1
        assert leads[0].email == "lead@gh.example.com"
    finally:
        db.close()


def test_submit_devuelve_429_pasado_el_limite(app_with_db, monkeypatch):
    app, _ = app_with_db
    # Límite apretado para el test (el default de prod es 10/minute)
    from app.api.v1 import lead_profile as lp_mod
    monkeypatch.setattr(
        lp_mod,
        "get_settings",
        lambda: SimpleNamespace(rate_limit_lead_submit="3/minute"),
    )

    with TestClient(app) as client:
        statuses = [
            client.post(
                "/api/v1/lead-profile/submit",
                json=_payload(email=f"lead{i}@gh.example.com"),
            ).status_code
            for i in range(5)
        ]
        last = client.post("/api/v1/lead-profile/submit", json=_payload())

    # Las 3 primeras pasan, después 429 estructurado
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429 and statuses[4] == 429
    assert last.status_code == 429
    body = last.json()
    assert body["error"] == "rate_limit_exceeded"
    assert "retry_after" in body
    assert "retry-after" in last.headers


def test_quiz_publico_sin_limite_propio_sigue_abierto(app_with_db):
    """GET /quiz (solo lectura) no quedó atrapado por el límite del submit."""
    app, _ = app_with_db
    with TestClient(app) as client:
        for _ in range(12):
            r = client.get("/api/v1/lead-profile/quiz")
            assert r.status_code == 200
