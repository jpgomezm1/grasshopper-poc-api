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
