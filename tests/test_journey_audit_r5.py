"""R5 · regresión de la auditoría profunda del Journey (2026-07-08).

Cubre los hallazgos confirmados por la auditoría multi-agente:
- CRÍTICO: la selección de ruta se compara contra las rutas PERSISTIDAS que
  la usuaria vio (antes se regeneraban con otra llamada IA → keys distintas →
  elección perdida en silencio y sesión "completada" sin ruta).
- El contenido IA se genera UNA vez por paso (cache en session.ai_content).
- step_id arbitrario ya no salta pasos ni completa el journey vacío.
- Journal sin duplicados y la síntesis del diario = la que se mostró.
- Truncation de texto libre; usuario inactivo → 401; birthdate inmutable;
  Habeas Data borra uploads externos y PDFs de storage.
- E2E: journey completo welcome→nextStep por la API (gap de cobertura).
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.schemas.ai_outputs import (
    EmpathyReflectionOutput,
    GeneratedRoute,
    RouteSuggestionOutput,
    SynthesisChip,
    SynthesisOutput,
)


FAKE_ROUTES = RouteSuggestionOutput(
    routes=[
        GeneratedRoute(
            key="RUTA_TEST_A",
            name="Ruta A",
            why="why A",
            what_it_looks_like="look A",
            next_step="next A",
        ),
        GeneratedRoute(
            key="RUTA_TEST_B",
            name="Ruta B",
            why="why B",
            what_it_looks_like="look B",
            next_step="next B",
        ),
    ]
)

FAKE_SYNTHESIS = SynthesisOutput(
    text="Veo a alguien explorando. ¿Te refleja esto?",
    chips=[SynthesisChip(label="Etapa", value="x")],
    key_motivations=["Exploración"],
    constraints=[],
)


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

    # IA falsa y CONTABLE en el namespace de journey_service
    from app.services import journey_service as js
    calls = {"routes": 0, "synthesis": 0, "reflection": 0}

    monkeypatch.setattr(
        js, "generate_routes",
        lambda *a, **k: calls.__setitem__("routes", calls["routes"] + 1) or FAKE_ROUTES,
    )
    monkeypatch.setattr(
        js, "generate_synthesis",
        lambda *a, **k: calls.__setitem__("synthesis", calls["synthesis"] + 1) or FAKE_SYNTHESIS,
    )
    monkeypatch.setattr(
        js, "generate_empathy_reflection",
        lambda *a, **k: calls.__setitem__("reflection", calls["reflection"] + 1)
        or EmpathyReflectionOutput(text="Te entiendo.", detected_emotion=None),
    )

    with TestClient(app) as client:
        yield client, TestingSessionLocal, calls
    app.dependency_overrides.clear()


def _student(client, email):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Test2026!", "name": "R5"},
    )
    assert r.status_code in (200, 201), r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _session_id(client, H):
    r = client.get("/api/v1/auth/me/session", headers=H)
    assert r.status_code == 200
    return r.json()["session_id"]


def _answer(client, H, sid, step_id, payload):
    return client.post(
        f"/api/v1/sessions/{sid}/events",
        headers=H,
        json={"event_type": "answer", "step_id": step_id, "payload": payload},
    )


def _walk_to_routes(client, H, sid):
    """Avanza el journey respondiendo genéricamente hasta el paso 'routes'."""
    for _ in range(20):
        r = client.get(f"/api/v1/sessions/{sid}", headers=H)
        assert r.status_code == 200, r.text
        state = r.json()
        step, view = state["step_id"], state["view_type"]
        if step == "routes":
            return state
        if view == "OPEN_TEXT":
            payload = {"value": "respuesta de prueba"}
        elif view == "SINGLE_CHOICE":
            payload = {"value": (state.get("options") or ["x"])[0]}
        elif view == "MULTI_CHOICE":
            payload = {"value": [(state.get("options") or ["x"])[0]]}
        else:  # WELCOME / REFLECTION / PARTIAL_SUMMARY
            payload = {}
        rr = _answer(client, H, sid, step, payload)
        assert rr.status_code == 200, f"{step}: {rr.text}"
    raise AssertionError("no llegó a routes en 20 pasos")


# ── CRÍTICO · selección de ruta ─────────────────────────────────────────────

def test_journey_e2e_y_seleccion_usa_rutas_persistidas(env):
    client, SL, calls = env
    H = _student(client, "r5.critico@example.com")
    sid = _session_id(client, H)

    state = _walk_to_routes(client, H, sid)
    shown = state["suggested_routes"]
    assert [r["key"] for r in shown] == ["RUTA_TEST_A", "RUTA_TEST_B"]
    routes_calls_al_mostrar = calls["routes"]
    assert routes_calls_al_mostrar == 1  # una sola generación al mostrar

    # refrescar el paso NO regenera (cache) → mismas rutas
    r = client.get(f"/api/v1/sessions/{sid}", headers=H)
    assert [x["key"] for x in r.json()["suggested_routes"]] == ["RUTA_TEST_A", "RUTA_TEST_B"]
    assert calls["routes"] == routes_calls_al_mostrar

    # seleccionar la ruta QUE SE MOSTRÓ → se registra sin regenerar
    r = client.post(
        f"/api/v1/sessions/{sid}/events",
        headers=H,
        json={"event_type": "selection", "step_id": "routes", "payload": {"route_key": "RUTA_TEST_B"}},
    )
    assert r.status_code == 200
    assert calls["routes"] == routes_calls_al_mostrar  # CERO llamadas extra

    from app.db.models import Route, Session as JS
    db = SL()
    sess = db.query(JS).filter(JS.id == UUID(sid)).first()
    routes = db.query(Route).filter(Route.session_id == UUID(sid)).all()
    assert sess.is_completed is True
    assert sess.selected_routes == ["RUTA_TEST_B"]
    assert len(routes) == 1 and routes[0].key == "RUTA_TEST_B" and routes[0].is_primary
    assert routes[0].name == "Ruta B"  # el contenido guardado = el que VIO
    db.close()


def test_seleccion_con_key_desconocida_no_completa(env):
    client, SL, calls = env
    H = _student(client, "r5.badkey@example.com")
    sid = _session_id(client, H)
    _walk_to_routes(client, H, sid)

    r = client.post(
        f"/api/v1/sessions/{sid}/events",
        headers=H,
        json={"event_type": "selection", "step_id": "routes", "payload": {"route_key": "NO_EXISTE"}},
    )
    assert r.status_code == 200  # no-op idempotente, el front se re-sincroniza
    from app.db.models import Route, Session as JS
    db = SL()
    sess = db.query(JS).filter(JS.id == UUID(sid)).first()
    assert sess.is_completed is False
    assert sess.current_step == "routes"  # NO avanzó
    assert db.query(Route).filter(Route.session_id == UUID(sid)).count() == 0
    db.close()


def test_seleccion_repetida_no_duplica_rutas_ni_journal(env):
    client, SL, calls = env
    H = _student(client, "r5.dupsel@example.com")
    sid = _session_id(client, H)
    _walk_to_routes(client, H, sid)

    for _ in range(2):
        client.post(
            f"/api/v1/sessions/{sid}/events",
            headers=H,
            json={"event_type": "selection", "step_id": "routes", "payload": {"route_key": "RUTA_TEST_A"}},
        )
    # tras completar, un tercer intento con estado viejo (step_id=routes) es no-op
    from app.db.models import JournalEntry, Route
    db = SL()
    assert db.query(Route).filter(Route.session_id == UUID(sid)).count() == 1
    decisiones = [
        e for e in db.query(JournalEntry).filter(JournalEntry.session_id == UUID(sid)).all()
        if "ruta" in (e.tags or [])
    ]
    assert len(decisiones) == 1
    db.close()


# ── step_id arbitrario ──────────────────────────────────────────────────────

def test_step_id_arbitrario_es_noop(env):
    client, SL, calls = env
    H = _student(client, "r5.skip@example.com")
    sid = _session_id(client, H)

    # sesión recién creada (welcome) · intentar completar el journey saltando
    r = _answer(client, H, sid, "routes", None)
    assert r.status_code == 200
    from app.db.models import Session as JS
    db = SL()
    sess = db.query(JS).filter(JS.id == UUID(sid)).first()
    assert sess.is_completed is False
    assert sess.current_step == "welcome"  # ni se movió
    db.close()


def test_answer_sobre_routes_no_lo_completa(env):
    """Incluso estando EN routes, un 'answer' no lo salta (solo 'selection')."""
    client, SL, calls = env
    H = _student(client, "r5.routesanswer@example.com")
    sid = _session_id(client, H)
    _walk_to_routes(client, H, sid)

    r = _answer(client, H, sid, "routes", {})
    assert r.status_code == 200
    from app.db.models import Session as JS
    db = SL()
    sess = db.query(JS).filter(JS.id == UUID(sid)).first()
    assert sess.current_step == "routes"
    assert sess.is_completed is False
    db.close()


# ── contenido IA · cache y journal ──────────────────────────────────────────

def test_journal_sintesis_reusa_lo_mostrado_y_no_duplica(env):
    client, SL, calls = env
    H = _student(client, "r5.journal@example.com")
    sid = _session_id(client, H)
    _walk_to_routes(client, H, sid)

    synth_calls = calls["synthesis"]
    assert synth_calls == 1  # una sola generación en todo el camino

    from app.db.models import JournalEntry
    db = SL()
    entradas = db.query(JournalEntry).filter(JournalEntry.session_id == UUID(sid)).all()
    sintesis = [e for e in entradas if "sintesis" in (e.tags or [])]
    assert len(sintesis) == 1
    assert sintesis[0].content == FAKE_SYNTHESIS.text  # el diario = lo que vio
    inicio = [e for e in entradas if "inicio" in (e.tags or [])]
    assert len(inicio) == 1  # empathy journal sin duplicados
    db.close()


def test_open_text_se_trunca(env):
    client, SL, calls = env
    H = _student(client, "r5.trunca@example.com")
    sid = _session_id(client, H)
    # welcome → whyHere
    _answer(client, H, sid, "welcome", {})
    r = _answer(client, H, sid, "whyHere", {"value": "x" * 6000})
    assert r.status_code == 200
    from app.db.models import Session as JS
    db = SL()
    sess = db.query(JS).filter(JS.id == UUID(sid)).first()
    assert len(sess.answers["whyHere"]) == 5000
    db.close()


# ── auth / privacidad ───────────────────────────────────────────────────────

def test_usuario_inactivo_401(env):
    client, SL, calls = env
    H = _student(client, "r5.inactive@example.com")
    from app.db.models import User
    db = SL()
    u = db.query(User).filter(User.email == "r5.inactive@example.com").first()
    u.is_active = False
    db.commit()
    db.close()
    r = client.get("/api/v1/auth/me", headers=H)
    assert r.status_code == 401


def test_birthdate_inmutable_via_onboarding(env):
    client, SL, calls = env
    H = _student(client, "r5.bd@example.com")
    r = client.put("/api/v1/auth/me/onboarding", headers=H, json={"answers": {"birthdate": "2015-01-01"}})
    assert r.status_code == 200
    # intento de "volverse mayor" reescribiendo la fecha
    client.put("/api/v1/auth/me/onboarding", headers=H, json={"answers": {"birthdate": "1990-01-01"}})
    from app.db.models import User
    db = SL()
    u = db.query(User).filter(User.email == "r5.bd@example.com").first()
    assert str(u.birthdate) == "2015-01-01"
    db.close()


def test_habeas_data_borra_uploads_y_pdfs(env, monkeypatch):
    client, SL, calls = env
    H = _student(client, "r5.habeas@example.com")

    from app.db.models import ExternalTestUpload, Report, User
    db = SL()
    u = db.query(User).filter(User.email == "r5.habeas@example.com").first()
    db.add(ExternalTestUpload(user_id=u.id, test_type="mbti", file_path="u/x/upload.pdf", raw_text="PII"))
    db.add(Report(user_id=u.id, file_path=f"{u.id}/reports/r.pdf"))
    db.commit()
    uid = u.id
    db.close()

    deleted_paths = []
    import app.services.storage_service as storage
    monkeypatch.setattr(storage, "delete_file", lambda p: deleted_paths.append(p) or True)

    r = client.request("DELETE", "/api/v1/me/data", headers=H)
    assert r.status_code == 200

    db = SL()
    assert db.query(ExternalTestUpload).filter(ExternalTestUpload.user_id == uid).count() == 0
    assert db.query(Report).filter(Report.user_id == uid).count() == 0
    db.close()
    assert set(deleted_paths) == {"u/x/upload.pdf", f"{uid}/reports/r.pdf"}


# ── fallbacks des-sesgados ──────────────────────────────────────────────────

def test_fallback_routes_sin_sesgo_internacional():
    from app.services.ai_service import FALLBACK_ROUTES

    texto = " ".join(
        f"{r['name']} {r['why']} {r['what_it_looks_like']}" for r in FALLBACK_ROUTES
    ).lower()
    # lo internacional puede aparecer como OPCIÓN, pero no como único marco
    assert "descubrir tu vocación" in texto or "vocacion" in texto
    assert "afuera" not in texto  # la vieja "carrera afuera" ya no enmarca
