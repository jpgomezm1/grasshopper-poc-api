"""Memoria entre años · `GET /api/v1/year-checkin` (fase 2 de 4 malla completa).

Cubre el contrato end-to-end (HTTP real, DB real vía SQLite, IA mockeada EN
LA FRONTERA — `call_claude_with_meta` dentro de `year_checkin_service`, nunca
la función que se está probando):

  (a) sin memoria → 200, has_memory False, checkin_message None, la IA NUNCA
      se llama (no tiene sentido gastar una llamada para un mensaje que no
      se va a usar).
  (b) memoria pero mismo grado → checkin_message None, IA tampoco se llama.
  (c) grado nuevo → checkin_message viene del mock, y el prompt real que le
      llegó a la IA trae el detalle concreto del año pasado (no placeholders
      sin reemplazar).
  (d) IA caída (None) en un caso de grado nuevo → NO 503 · cae a la plantilla
      determinista, que sigue mencionando el detalle concreto.
  (e) record_ai_usage se llama con feature="year_checkin" sólo cuando hubo
      llamada real a la IA.
  (f) requiere autenticación.
  (g) "hoy" en la respuesta HTTP refleja tests y rutas reales de la base
      (persistencia real, no un mock de esa parte).

Mismo patrón de fixture que tests/test_hop_chat.py.
"""
from __future__ import annotations

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

ONBOARDING_2025 = {
    "life_stage": "high_school_early",
    "voice_passion": "diseñar videojuegos",
    "voice_hobbies": "dibujar",
    "main_goal": ["discover"],
    "international_interest": "intl_maybe",
    "countries": ["usa"],
}


def _student(SessionLocal, email="student@x.com", grade=None, **extra):
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
            grade=grade,
            onboarding_answers=ONBOARDING_2025,
            **extra,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id, u.email
    finally:
        db.close()


def _seed_snapshot(SessionLocal, user_id, *, school_year=2025, grade=10, answers=None):
    from app.db.models import StudentYearSnapshot

    db = SessionLocal()
    try:
        db.add(StudentYearSnapshot(
            user_id=user_id, school_year=school_year, grade=grade,
            onboarding_answers_snapshot=answers or ONBOARDING_2025,
        ))
        db.commit()
    finally:
        db.close()


def _login(client, email, password="testpass123"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _mock_ai(monkeypatch, reply="Hola de nuevo, ¿sigue igual tu pasión?", metadata=None):
    """Mockea call_claude_with_meta EN EL MÓDULO DEL SERVICIO (la frontera)."""
    calls = []

    def _fake(prompt, *, session_id, feature, max_tokens=2000, temperature=0.3,
               prompt_version=None, timeout=120.0):
        calls.append({"prompt": prompt, "session_id": session_id, "feature": feature})
        meta = metadata or {
            "model": "claude-sonnet-4-5", "tokens_input": 200,
            "tokens_output": 40, "latency_ms": 300,
        }
        return reply, meta

    from app.services import year_checkin_service
    monkeypatch.setattr(year_checkin_service, "call_claude_with_meta", _fake)
    return calls


def _get(client, token):
    return client.get("/api/v1/year-checkin", headers={"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# (a) sin memoria · no hay snapshot todavía
# ---------------------------------------------------------------------------

def test_sin_memoria_no_llama_ia(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _, email = _student(SessionLocal, grade=10)
    calls = _mock_ai(monkeypatch)

    client = TestClient(app)
    token = _login(client, email)
    r = _get(client, token)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_memory"] is False
    assert body["is_new_grade"] is False
    assert body["previous"] is None
    assert body["checkin_message"] is None
    assert calls == []


# ---------------------------------------------------------------------------
# (b) memoria pero mismo grado · tampoco llama IA
# ---------------------------------------------------------------------------

def test_memoria_mismo_grado_no_llama_ia(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    user_id, email = _student(SessionLocal, grade=10)
    _seed_snapshot(SessionLocal, user_id, school_year=2025, grade=10)
    calls = _mock_ai(monkeypatch)

    client = TestClient(app)
    token = _login(client, email)
    r = _get(client, token)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_memory"] is True
    assert body["is_new_grade"] is False
    assert body["checkin_message"] is None
    assert calls == []


# ---------------------------------------------------------------------------
# (c) grado nuevo · genera el check-in y el prompt trae el detalle real
# ---------------------------------------------------------------------------

def test_grado_nuevo_genera_checkin_con_detalle_real(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    user_id, email = _student(SessionLocal, grade=11)
    _seed_snapshot(SessionLocal, user_id, school_year=2025, grade=10)
    calls = _mock_ai(monkeypatch, reply="¿Sigue siendo diseñar videojuegos tu pasión ahora en 11°?")

    client = TestClient(app)
    token = _login(client, email)
    r = _get(client, token)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_new_grade"] is True
    assert body["previous"]["grade"] == 10
    assert body["previous"]["perfil"]["pasion"] == "diseñar videojuegos"
    assert body["today"]["grade"] == 11
    assert body["checkin_message"] == "¿Sigue siendo diseñar videojuegos tu pasión ahora en 11°?"

    assert len(calls) == 1
    prompt = calls[0]["prompt"]
    # El detalle concreto del año pasado sí llegó a la IA · no quedaron
    # placeholders sin reemplazar.
    assert "diseñar videojuegos" in prompt
    assert "grado 10" in prompt
    assert "grado 11" in prompt
    assert "{grado_anterior}" not in prompt
    assert "{resumen_anterior}" not in prompt
    assert calls[0]["feature"] == "year_checkin"


# ---------------------------------------------------------------------------
# (d) IA caída en caso de grado nuevo · fallback determinista, no 503
# ---------------------------------------------------------------------------

def test_ia_caida_usa_plantilla_determinista(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    user_id, email = _student(SessionLocal, grade=12)
    _seed_snapshot(SessionLocal, user_id, school_year=2025, grade=11)
    _mock_ai(monkeypatch, reply=None, metadata={
        "model": "claude-sonnet-4-5", "latency_ms": 90, "error_kind": "timeout",
    })

    client = TestClient(app)
    token = _login(client, email)
    r = _get(client, token)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_new_grade"] is True
    assert body["checkin_message"] is not None
    # La plantilla determinista sigue usando el dato concreto, no un genérico.
    assert "diseñar videojuegos" in body["checkin_message"]


# ---------------------------------------------------------------------------
# (e) record_ai_usage sólo cuando hubo llamada real
# ---------------------------------------------------------------------------

def test_record_ai_usage_solo_si_hubo_llamada(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    user_id, email = _student(SessionLocal, grade=11)
    _seed_snapshot(SessionLocal, user_id, school_year=2025, grade=10)
    _mock_ai(monkeypatch)

    recorded = []

    def _spy(db, **kwargs):
        recorded.append(kwargs)

    from app.services import year_checkin_service
    monkeypatch.setattr(year_checkin_service, "record_ai_usage", _spy)

    client = TestClient(app)
    token = _login(client, email)
    r = _get(client, token)

    assert r.status_code == 200, r.text
    assert len(recorded) == 1
    assert recorded[0]["feature"] == "year_checkin"
    assert recorded[0]["user_id"] == user_id


def test_record_ai_usage_no_se_llama_sin_grado_nuevo(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _, email = _student(SessionLocal, grade=10)  # sin snapshot · sin memoria
    _mock_ai(monkeypatch)

    recorded = []
    from app.services import year_checkin_service
    monkeypatch.setattr(year_checkin_service, "record_ai_usage",
                          lambda db, **kw: recorded.append(kw))

    client = TestClient(app)
    token = _login(client, email)
    r = _get(client, token)

    assert r.status_code == 200, r.text
    assert recorded == []


# ---------------------------------------------------------------------------
# (f) requiere autenticación
# ---------------------------------------------------------------------------

def test_requiere_autenticacion(app_with_db, monkeypatch):
    app, _ = app_with_db
    calls = _mock_ai(monkeypatch)

    client = TestClient(app)
    r = client.get("/api/v1/year-checkin")
    assert r.status_code in (401, 403), r.text
    assert calls == []


# ---------------------------------------------------------------------------
# (g) "hoy" refleja tests y rutas reales de la base (persistencia real)
# ---------------------------------------------------------------------------

def test_hoy_refleja_tests_y_rutas_reales(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    user_id, email = _student(SessionLocal, grade=11)
    _mock_ai(monkeypatch)

    db = SessionLocal()
    try:
        from app.db.models import (
            Route, RouteStatus, Session as JourneySession, VocationalTestResult,
        )
        db.add(VocationalTestResult(
            user_id=user_id, test_id="riasec", answers={}, scores={"R": 90},
        ))
        sess = JourneySession(user_id=user_id)
        db.add(sess)
        db.commit()
        db.add(Route(
            session_id=sess.id, key="stem", name="Ingeniería de Software",
            why="x", what_it_looks_like="x", next_step="x",
            status=RouteStatus.ACTIVE,
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    token = _login(client, email)
    r = _get(client, token)

    assert r.status_code == 200, r.text
    body = r.json()
    assert [t["test_id"] for t in body["today"]["tests_taken"]] == ["riasec"]
    assert body["today"]["active_routes"] == ["Ingeniería de Software"]
