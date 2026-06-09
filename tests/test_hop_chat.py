"""Fase C pieza C (B-049) · chat real de Hop · POST /api/v1/hop/chat.

Cubre el contrato fijado con el FE:
  (a) 200 con reply + profile_used/oferta_context_used correctos
  (b) 503 cuando la IA devuelve (None, {...})
  (c) 422 con history de 21 items
  (d) 422 con message vacío o >2000
  (e) sin perfil cacheado → profile_used False
  (f) oferta_id inexistente → 200 con oferta_context_used False
  (g) oferta_id válido con financieros NULL → oferta_context_used True
      y el bloque dice "a confirmar"
  (h) historial de 20 se capa a 12 al llamar la IA
  (i) record_ai_usage se llamó con feature="hop_chat"

La IA se mockea SIEMPRE (monkeypatch de `call_claude_chat` en el módulo del
servicio, donde se importa). Usa SQLite + TestClient (sin Postgres) — patrón
de fixture copiado de tests/test_programs_import_scholarships_f003.py.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Fixture (SQLite in-memory + TestClient)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _student(SessionLocal, email="student@x.com", **extra):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash("testpass123"),
            name="Student",
            role=UserRole.STUDENT,
            onboarding_status=OnboardingStatus.NOT_STARTED,
            **extra,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id, u.email
    finally:
        db.close()


def _login(client, email, password="testpass123"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _seed_profile_cache(SessionLocal, user_id):
    """Perfil consolidado cacheado y válido (invalidated_at=None)."""
    from app.db.models import ConsolidatedProfileCache

    db = SessionLocal()
    try:
        row = ConsolidatedProfileCache(
            user_id=user_id,
            profile_hash="x" * 64,
            profile_data={
                "summary_narrative": "Eres una persona curiosa y analítica.",
                "strengths": ["Análisis de datos", "Curiosidad", "Persistencia"],
                "interests": ["Ingeniería ambiental", "Ciencia de datos", "Diseño"],
                "values": ["Autonomía", "Aprendizaje continuo"],
                "learning_style": "Reflexivo-analítico",
                "work_style": "Autónomo orientado a resultados",
                "suggested_career_paths": ["Ciencia ambiental aplicada"],
            },
            recommendations_data=[],
        )
        db.add(row)
        db.commit()
    finally:
        db.close()


def _seed_program_null_financials(SessionLocal):
    """Program con financieros NULL (migración 048: NULL = 'a confirmar')."""
    from app.db.models import Program

    db = SessionLocal()
    try:
        p = Program(
            program_id="P-HOP-1",
            name="Pregrado en Ciencias",
            slug="pregrado-ciencias-hop",
            country="Canada",
            city="Toronto",
            institution="Hop University",
            type="pregrado",
            duration_months=None,
            cost_total=None,
            budget_tier=None,
            language_requirement=None,
            scholarships_for_latam=None,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        return str(p.id)
    finally:
        db.close()


def _mock_ai(monkeypatch, reply="¡Hola! Soy Hop.", metadata=None):
    """Mockea call_claude_chat EN EL MÓDULO DEL SERVICIO y captura las llamadas."""
    calls = []

    def _fake(messages, system, session_id, feature, max_tokens=1000, temperature=0.6):
        calls.append({
            "messages": messages,
            "system": system,
            "session_id": session_id,
            "feature": feature,
        })
        meta = metadata or {
            "model": "claude-sonnet-4-5",
            "tokens_input": 321,
            "tokens_output": 87,
            "latency_ms": 450,
            "stop_reason": "end_turn",
        }
        return reply, meta

    from app.services import hop_chat_service
    monkeypatch.setattr(hop_chat_service, "call_claude_chat", _fake)
    return calls


def _chat(client, token, payload):
    return client.post(
        "/api/v1/hop/chat",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )


# ---------------------------------------------------------------------------
# (a) 200 con reply y flags correctos (perfil cacheado + sin oferta)
# ---------------------------------------------------------------------------

def test_chat_200_with_cached_profile(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    user_id, email = _student(
        SessionLocal,
        budget_band="medio",
        budget_max_usd=20000,
        preferred_countries=["Canadá"],
        english_cefr_level="B2",
    )
    _seed_profile_cache(SessionLocal, user_id)
    calls = _mock_ai(monkeypatch, reply="Con tu perfil analítico, te sugiero explorar el catálogo.")

    client = TestClient(app)
    token = _login(client, email)
    r = _chat(client, token, {"message": "¿Qué carrera me recomiendas?"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"] == "Con tu perfil analítico, te sugiero explorar el catálogo."
    assert body["profile_used"] is True
    assert body["oferta_context_used"] is False

    # El system prompt recibió el perfil y los constraints reales
    assert len(calls) == 1
    system = calls[0]["system"]
    assert "curiosa y analítica" in system
    assert "B2" in system
    assert "Canadá" in system
    assert calls[0]["feature"] == "hop_chat"
    assert calls[0]["session_id"] == str(user_id)
    # El último message es el del usuario
    assert calls[0]["messages"][-1] == {
        "role": "user",
        "content": "¿Qué carrera me recomiendas?",
    }


# ---------------------------------------------------------------------------
# (b) 503 cuando la IA devuelve (None, {...})
# ---------------------------------------------------------------------------

def test_chat_503_when_ai_down(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _, email = _student(SessionLocal)
    _mock_ai(monkeypatch, reply=None, metadata={"model": "claude-sonnet-4-5", "latency_ms": 100, "error_kind": "timeout"})

    client = TestClient(app)
    token = _login(client, email)
    r = _chat(client, token, {"message": "Hola"})

    assert r.status_code == 503, r.text
    assert r.json()["detail"] == (
        "Hop no puede responder en este momento. Intenta de nuevo en unos minutos."
    )


# ---------------------------------------------------------------------------
# (c) 422 con history de 21 items
# ---------------------------------------------------------------------------

def test_chat_422_history_21_items(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _, email = _student(SessionLocal)
    calls = _mock_ai(monkeypatch)

    client = TestClient(app)
    token = _login(client, email)
    history = [{"role": "user", "content": f"turno {i}"} for i in range(21)]
    r = _chat(client, token, {"message": "Hola", "history": history})

    assert r.status_code == 422, r.text
    assert calls == []  # nunca llegó a la IA


# ---------------------------------------------------------------------------
# (d) 422 con message vacío o >2000
# ---------------------------------------------------------------------------

def test_chat_422_message_empty_or_too_long(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _, email = _student(SessionLocal)
    calls = _mock_ai(monkeypatch)

    client = TestClient(app)
    token = _login(client, email)

    r = _chat(client, token, {"message": ""})
    assert r.status_code == 422, r.text

    r = _chat(client, token, {"message": "x" * 2001})
    assert r.status_code == 422, r.text

    assert calls == []


# ---------------------------------------------------------------------------
# (e) sin perfil cacheado → profile_used False + bloque de invitación
# ---------------------------------------------------------------------------

def test_chat_no_cached_profile_flag_false(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _, email = _student(SessionLocal)
    calls = _mock_ai(monkeypatch)

    client = TestClient(app)
    token = _login(client, email)
    r = _chat(client, token, {"message": "Hola Hop"})

    assert r.status_code == 200, r.text
    assert r.json()["profile_used"] is False
    assert "aún no tiene perfil consolidado" in calls[0]["system"]


# ---------------------------------------------------------------------------
# (f) oferta_id inexistente → 200 con oferta_context_used False
# ---------------------------------------------------------------------------

def test_chat_unknown_oferta_id_flag_false(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _, email = _student(SessionLocal)
    calls = _mock_ai(monkeypatch)

    client = TestClient(app)
    token = _login(client, email)
    r = _chat(client, token, {"message": "Hola", "oferta_id": str(uuid.uuid4())})

    assert r.status_code == 200, r.text
    assert r.json()["oferta_context_used"] is False
    assert "no está consultando ninguna oferta" in calls[0]["system"]

    # también con un slug inexistente (no-UUID)
    r = _chat(client, token, {"message": "Hola", "oferta_id": "slug-que-no-existe"})
    assert r.status_code == 200, r.text
    assert r.json()["oferta_context_used"] is False


# ---------------------------------------------------------------------------
# (g) oferta válida con financieros NULL → flag True + "a confirmar"
# ---------------------------------------------------------------------------

def test_chat_oferta_null_financials_a_confirmar(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _, email = _student(SessionLocal)
    program_uuid = _seed_program_null_financials(SessionLocal)
    calls = _mock_ai(monkeypatch)

    client = TestClient(app)
    token = _login(client, email)
    r = _chat(client, token, {"message": "¿Cuánto cuesta este programa?", "oferta_id": program_uuid})

    assert r.status_code == 200, r.text
    assert r.json()["oferta_context_used"] is True

    system = calls[0]["system"]
    assert "Pregrado en Ciencias" in system
    assert "Hop University" in system
    assert "Duración: a confirmar" in system
    assert "Costo total: a confirmar" in system
    assert "Requisito de idioma: a confirmar" in system
    assert "Beca para estudiantes LatAm: sin curar" in system


def test_chat_oferta_found_by_slug_and_program_id(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _, email = _student(SessionLocal)
    _seed_program_null_financials(SessionLocal)
    calls = _mock_ai(monkeypatch)

    client = TestClient(app)
    token = _login(client, email)

    r = _chat(client, token, {"message": "Hola", "oferta_id": "pregrado-ciencias-hop"})
    assert r.status_code == 200 and r.json()["oferta_context_used"] is True

    r = _chat(client, token, {"message": "Hola", "oferta_id": "P-HOP-1"})
    assert r.status_code == 200 and r.json()["oferta_context_used"] is True

    assert len(calls) == 2


# ---------------------------------------------------------------------------
# (h) historial de 20 se capa a 12 al llamar a la IA
# ---------------------------------------------------------------------------

def test_chat_history_capped_to_12(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _, email = _student(SessionLocal)
    calls = _mock_ai(monkeypatch)

    client = TestClient(app)
    token = _login(client, email)
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"turno {i}"}
        for i in range(20)
    ]
    r = _chat(client, token, {"message": "mensaje actual", "history": history})

    assert r.status_code == 200, r.text
    messages = calls[0]["messages"]
    # 12 turnos de historial + el mensaje actual
    assert len(messages) == 13
    # se conservan los ÚLTIMOS 12 (turnos 8..19)
    assert messages[0]["content"] == "turno 8"
    assert messages[-2]["content"] == "turno 19"
    assert messages[-1] == {"role": "user", "content": "mensaje actual"}


# ---------------------------------------------------------------------------
# (i) record_ai_usage se llamó (tracking M-001)
# ---------------------------------------------------------------------------

def test_chat_records_ai_usage(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    user_id, email = _student(SessionLocal)
    _mock_ai(monkeypatch)

    recorded = []

    def _spy(db, **kwargs):
        recorded.append(kwargs)

    from app.services import hop_chat_service
    monkeypatch.setattr(hop_chat_service, "record_ai_usage", _spy)

    client = TestClient(app)
    token = _login(client, email)
    r = _chat(client, token, {"message": "Hola"})

    assert r.status_code == 200, r.text
    assert len(recorded) == 1
    kw = recorded[0]
    assert kw["feature"] == "hop_chat"
    assert kw["provider"] == "anthropic"
    assert kw["tokens_input"] == 321
    assert kw["tokens_output"] == 87
    assert kw["latency_ms"] == 450
    assert kw["user_id"] == user_id


def test_chat_records_ai_usage_on_error_too(app_with_db, monkeypatch):
    """La firma lo permite (tokens opcionales) → se registra también el fallo."""
    app, SessionLocal = app_with_db
    _, email = _student(SessionLocal)
    _mock_ai(monkeypatch, reply=None, metadata={"model": "claude-sonnet-4-5", "latency_ms": 99, "error_kind": "server"})

    recorded = []

    def _spy(db, **kwargs):
        recorded.append(kwargs)

    from app.services import hop_chat_service
    monkeypatch.setattr(hop_chat_service, "record_ai_usage", _spy)

    client = TestClient(app)
    token = _login(client, email)
    r = _chat(client, token, {"message": "Hola"})

    assert r.status_code == 503
    assert len(recorded) == 1
    assert recorded[0]["feature"] == "hop_chat"
    assert recorded[0]["tokens_input"] is None
    assert recorded[0]["latency_ms"] == 99


# ---------------------------------------------------------------------------
# Auth: sin token → 401/403
# ---------------------------------------------------------------------------

def test_chat_requires_auth(app_with_db, monkeypatch):
    app, _ = app_with_db
    calls = _mock_ai(monkeypatch)

    client = TestClient(app)
    r = client.post("/api/v1/hop/chat", json={"message": "Hola"})
    assert r.status_code in (401, 403), r.text
    assert calls == []


# ---------------------------------------------------------------------------
# Unit: cost table M-001 tiene el modelo del proyecto
# ---------------------------------------------------------------------------

def test_cost_table_has_project_model():
    from app.services.ai_usage_service import estimate_cost_usd

    # 1000 in + 1000 out a (0.003, 0.015) → 0.018 USD
    assert estimate_cost_usd("claude-sonnet-4-5", 1000, 1000) == 0.018
