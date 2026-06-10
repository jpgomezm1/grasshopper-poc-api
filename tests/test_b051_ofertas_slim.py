"""B-051 · GET /ofertas con slim/limit (optimización de carga del catálogo).

La lista completa (2.511 programas en prod) pesaba varios MB porque cada
oferta viaja con fullDescription (description_long entero) y media, que la UI
de lista nunca muestra. `slim=true` los omite y `limit` corta la cola (el
detalle de un programa solo necesita un puñado de "relacionadas").

Back-compat: sin los params nuevos la respuesta es EXACTAMENTE la de antes.

SQLite + TestClient · patrón de tests/test_programs_list_nullable_b042.py.
"""
from __future__ import annotations

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
    monkeypatch.setenv("BITRIX_WEBHOOK_URL", "")
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

    from app.core.rate_limiter import limiter as gh_limiter
    gh_limiter.reset()

    yield app, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _student(SessionLocal):
    from app.db.models import User, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    try:
        u = User(
            email="b051.student@grasshopper.dev",
            hashed_password=get_password_hash("testpass123"),
            name="B051",
            onboarding_status=OnboardingStatus.NOT_STARTED,
        )
        db.add(u)
        db.commit()
        return u.email
    finally:
        db.close()


def _login(client, email, password="testpass123"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _seed_programs(SessionLocal, n=5):
    from app.db.models import Program

    db = SessionLocal()
    try:
        for i in range(n):
            db.add(Program(
                program_id=f"P-{i:03d}",
                name=f"Programa {i:03d}",
                slug=f"programa-{i:03d}",
                country="Canadá",
                city="Toronto",
                institution="Uni Toronto",
                type="pregrado" if i % 2 == 0 else "diplomado",
                description_long="Descripción larguísima del programa. " * 30,
                images=[{"url": f"https://img.example/{i}.jpg"}],
                cost_total=4000,
                currency="USD",
                budget_tier="low",
                active=True,
            ))
        db.commit()
    finally:
        db.close()


def _client_and_token(app_with_db):
    app, SessionLocal = app_with_db
    _seed_programs(SessionLocal)
    email = _student(SessionLocal)
    client = TestClient(app)
    token = _login(client, email)
    return client, {"Authorization": f"Bearer {token}"}


def test_default_response_unchanged(app_with_db):
    """Sin params nuevos el contrato es el de siempre (back-compat)."""
    client, headers = _client_and_token(app_with_db)

    r = client.get("/api/v1/ofertas", headers=headers)
    assert r.status_code == 200
    ofertas = r.json()
    assert len(ofertas) == 5
    assert ofertas[0]["fullDescription"].startswith("Descripción larguísima")
    assert ofertas[0]["media"] == [{"type": "image", "url": "https://img.example/0.jpg"}]


def test_slim_omits_heavy_fields_keeps_the_rest(app_with_db):
    client, headers = _client_and_token(app_with_db)

    r = client.get("/api/v1/ofertas?slim=true", headers=headers)
    assert r.status_code == 200
    ofertas = r.json()
    assert len(ofertas) == 5
    for o in ofertas:
        assert o["fullDescription"] == ""
        assert o["media"] == []
        # Lo que la lista SÍ usa sigue intacto
        assert o["shortDescription"]
        assert o["featuredImage"]
        assert o["name"]
        assert "scholarshipsForLatam" in o
        assert "admissionFit" in o


def test_limit_caps_results(app_with_db):
    client, headers = _client_and_token(app_with_db)

    r = client.get("/api/v1/ofertas?limit=2", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_limit_applies_after_filters(app_with_db):
    """limit corta el resultado FILTRADO (no la query cruda)."""
    client, headers = _client_and_token(app_with_db)

    # 'certificacion_corta' mapea a diplomado/curso_corto/bootcamp → 2 seeded
    r = client.get(
        "/api/v1/ofertas?category=certificacion_corta&limit=10", headers=headers
    )
    assert r.status_code == 200
    ofertas = r.json()
    assert len(ofertas) == 2
    assert all(o["category"] == "certificacion_corta" for o in ofertas)

    r2 = client.get(
        "/api/v1/ofertas?category=certificacion_corta&limit=1", headers=headers
    )
    assert len(r2.json()) == 1
