"""B-02 · el Journey no vuelve a preguntar lo que el onboarding ya capturó.

Regresión del fix 2026-07-07 (ver Docs/QA/QA_REPORT.md § 2026-07-07):
- El seed (etapa de vida + horizonte) debe caer en la sesión VINCULADA al
  usuario —la que el Journey realmente usa— y NO en una sesión anónima.
- El flujo autenticado (getUserSession / POST /sessions) NO debe dar 403
  "Access denied" (antes la sesión anónima con user_id=NULL lo disparaba).
- El Journey debe SALTAR lifeStage y timeHorizon (skip-if-answered).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services.journey_service import seed_session_from_onboarding
from app.core.state_machine import get_next_step


@pytest.fixture()
def client(tmp_path, monkeypatch):
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
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _onboarded_student(client, email="b02.seed@example.com"):
    """Registra un estudiante y completa el onboarding con university/1_year."""
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "Test2026!", "name": "B02"})
    assert r.status_code in (200, 201), r.text
    token = r.json()["access_token"]
    H = {"Authorization": f"Bearer {token}"}
    r = client.put("/api/v1/auth/me/onboarding",
                   json={"answers": {"life_stage": "university", "timeline": "1_year"}}, headers=H)
    assert r.status_code < 400, r.text
    r = client.post("/api/v1/auth/me/complete-onboarding", headers=H)
    assert r.status_code < 400, r.text
    return H


def test_linked_session_is_seeded_and_not_403(client):
    """complete-onboarding siembra la sesión VINCULADA; leerla no da 403."""
    H = _onboarded_student(client)

    # getUserSession devuelve la sesión vinculada
    r = client.get("/api/v1/auth/me/session", headers=H)
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]

    # leer la sesión NO debe dar 403 (antes: sesión anónima → Access denied)
    r = client.get(f"/api/v1/sessions/{sid}", headers=H)
    assert r.status_code == 200, f"esperaba 200, fue {r.status_code}: {r.text}"

    preview = r.json()["side_panel"]["profile_preview"]
    assert preview["lifeStage"] == "En la universidad"
    assert preview["timeHorizon"] == "En 1 año"


def test_post_sessions_returns_linked_seeded_session(client):
    """POST /sessions autenticado devuelve la sesión vinculada sembrada, no anónima."""
    H = _onboarded_student(client, email="b02.post@example.com")
    r = client.get("/api/v1/auth/me/session", headers=H)
    linked_sid = r.json()["session_id"]

    r = client.post("/api/v1/sessions", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    # misma sesión vinculada (idempotente), no una nueva anónima
    assert str(body["session_id"]) == str(linked_sid)
    assert body["side_panel"]["profile_preview"]["lifeStage"] == "En la universidad"


def test_journey_skips_lifestage_and_timehorizon(client):
    """Enviar eventos no da 403 y el Journey salta lifeStage/timeHorizon."""
    H = _onboarded_student(client, email="b02.skip@example.com")
    sid = client.get("/api/v1/auth/me/session", headers=H).json()["session_id"]

    seen = []
    step = client.get(f"/api/v1/sessions/{sid}", headers=H).json()["step_id"]
    for _ in range(6):
        seen.append(step)
        r = client.post(f"/api/v1/sessions/{sid}/events", headers=H,
                        json={"event_type": "answer", "step_id": step, "payload": {"value": "x"}})
        assert r.status_code != 403, f"403 en step={step}"
        assert r.status_code < 400, f"{r.status_code} en step={step}: {r.text}"
        nxt = r.json()["step_id"]
        if nxt == step or step == "clarityLevel":
            break
        step = nxt
        if step == "clarityLevel":
            seen.append(step)
            break

    assert "lifeStage" not in seen, f"el Journey pidió lifeStage: {seen}"
    assert "timeHorizon" not in seen, f"el Journey pidió timeHorizon: {seen}"
    assert "clarityLevel" in seen, f"no llegó a clarityLevel saltando el seed: {seen}"


def test_seed_does_not_clobber_existing_journey_answers():
    """El seed solo rellena lo vacío: no pisa una respuesta del Journey ya dada."""
    class FakeSession:
        answers = {"lifeStage": "Ya trabajando"}  # el usuario ya respondió en el Journey
        completed_steps = ["lifeStage"]
        current_step = "welcome"  # R5 · el seed puede avanzar current_step
        current_stage = None

    s = FakeSession()
    changed = seed_session_from_onboarding(s, {"life_stage": "university", "timeline": "1_year"})
    assert changed is True  # timeHorizon sí se agrega
    assert s.answers["lifeStage"] == "Ya trabajando"  # NO se pisó
    assert s.answers["timeHorizon"] == "En 1 año"
    # y el skip respeta la respuesta real del usuario
    assert get_next_step("empathy", s.answers) == "clarityLevel"


def test_seed_noop_without_onboarding():
    class FakeSession:
        answers = {}
        completed_steps = []
    s = FakeSession()
    assert seed_session_from_onboarding(s, None) is False
    assert seed_session_from_onboarding(s, {"unrelated": "x"}) is False
    assert s.answers == {}


# ---------------------------------------------------------------------------
# R6-ON-1b · "Estoy en el colegio" vs "último año" (Sprint 3)
#
# Verónica lo pidió dos veces en la reunión del 21-07. No era redacción: el mapa
# traducía `high_school` a "Terminando el colegio", así que un estudiante de 9°
# le informaba a la IA que estaba a punto de graduarse.
# ---------------------------------------------------------------------------


def test_colegio_temprano_no_dice_que_esta_terminando():
    from app.services.journey_service import seed_answers_from_onboarding

    temprano = seed_answers_from_onboarding({"life_stage": "high_school_early"})
    assert temprano["lifeStage"] == "En el colegio"
    assert "Terminando" not in temprano["lifeStage"]

    ultimo = seed_answers_from_onboarding({"life_stage": "high_school"})
    assert ultimo["lifeStage"] == "Terminando el colegio"


def test_las_opciones_del_front_tienen_mapeo_en_el_backend():
    """Contrato con OnboardingPage.tsx · step 'life_stage'.

    Si el front agrega una etapa y no se mapea aquí, `seed_answers_from_onboarding`
    la ignora en silencio y el Journey vuelve a preguntar lo que ya se respondió
    (que es justo la redundancia que la clienta reclama).
    """
    from app.services.journey_service import _ONBOARDING_LIFE_STAGE_MAP

    assert set(_ONBOARDING_LIFE_STAGE_MAP) == {
        "high_school_early",
        "high_school",
        "university",
        "recent_grad",
        "working",
        "career_change",
    }


# ---------------------------------------------------------------------------
# Cimientos (migración 067) · el grado llega de punta a punta por HTTP.
#
# No basta con probar `_sync_onboarding_to_user_columns` como función pura
# (ver `tests/test_p1_3_onboarding_llega_a_la_ia.py`): esto prueba el camino
# REAL que usa el frontend — `PUT /auth/me/onboarding` con el grado, y que
# `GET /auth/me` (lo que `journey-compass` lee para `resolveStudentTrack`)
# efectivamente lo sirva. Es la frontera que un mock de la función pura no
# puede garantizar por sí sola.
# ---------------------------------------------------------------------------


def test_el_grado_dicho_en_onboarding_llega_a_auth_me(client):
    r = client.post("/api/v1/auth/register", json={
        "email": "grado.e2e@example.com", "password": "Test2026!", "name": "Grado E2E",
    })
    assert r.status_code in (200, 201), r.text
    token = r.json()["access_token"]
    H = {"Authorization": f"Bearer {token}"}

    r = client.put(
        "/api/v1/auth/me/onboarding",
        json={"answers": {
            "life_stage": "high_school_early",
            "grade": "9",
            "school_reported_last_grade": "11",
            "school_reported_accreditation": "ib",
        }},
        headers=H,
    )
    assert r.status_code < 400, r.text

    perfil = client.get("/api/v1/auth/me", headers=H)
    assert perfil.status_code == 200, perfil.text
    body = perfil.json()
    assert body["grade"] == 9
    assert body["school_reported_last_grade"] == 11
    assert body["school_reported_accreditation"] == "ib"
