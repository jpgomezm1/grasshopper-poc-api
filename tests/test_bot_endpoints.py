"""Endpoints del bot perfilador · HTTP → motor → scoring → DB, en SQLite.

Ejercita el stack completo. La frontera que se mockea es la IA (`responder`,
que es lo que llama a Claude); todo lo demás corre de verdad: FastAPI, los
schemas, el scoring y la persistencia.

⚠️ Nunca contra la base real. El `.env` local apunta al MISMO Neon que
producción, así que estos tests montan SQLite en memoria y sobreescriben
`get_db`, igual que el resto de la suite.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

START = "/api/v1/bot/start"
TURN = "/api/v1/bot/turn"
LEADS = "/api/v1/bot/leads"


@pytest.fixture
def app_with_db(monkeypatch):
    sqlite_url = "sqlite:///:memory:"
    engine = create_engine(
        sqlite_url, connect_args={"check_same_thread": False}, poolclass=StaticPool
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


def _mock_motor(monkeypatch, *, respuesta="¿Y a qué destino?", hechos=None):
    """Sustituye la llamada a la IA · el resto del stack corre de verdad."""
    from app.api.v1 import bot as bot_router

    def _fake(mensaje, historial, recolectados, *, session_id, db=None):
        return respuesta, {**recolectados, **(hechos or {})}, []

    monkeypatch.setattr(bot_router, "responder", _fake)


def _usuario(SessionLocal, email, rol):
    from app.api.v1.auth import get_password_hash
    from app.db.models import OnboardingStatus, User, UserRole

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash("testpass123"),
            name="Equipo",
            role=rol if isinstance(rol, UserRole) else UserRole(rol),
            onboarding_status=OnboardingStatus.NOT_STARTED,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


def _headers(client, email):
    r = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Público · sin cuenta
# ---------------------------------------------------------------------------


def test_start_abre_conversacion_sin_autenticacion(app_with_db):
    app, _ = app_with_db
    with TestClient(app) as client:
        r = client.post(START, json={})

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["conversation_id"]
    assert cuerpo["message"]  # saludo estático · sin llamada de IA


def test_turn_persiste_hechos_y_veredicto(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _mock_motor(
        monkeypatch,
        hechos={
            "nombre": "Ana",
            "correo": "ana@x.co",
            "celular": "300",
            "inversion": "15k_30k",
            "cuando_viajar": "asap",
            "destino_interes": ["canada"],
            "pasaporte": "yes",
            "tipo_experiencia": "pregrado",
            "ocupacion": "high_school",
            "visa_usa_negada": False,
        },
    )
    with TestClient(app) as client:
        cid = client.post(START, json={}).json()["conversation_id"]
        r = client.post(TURN, json={"conversation_id": cid, "message": "hola"})

    assert r.status_code == 200, r.text
    assert r.json()["completed"] is True

    from app.db.models import BotConversation

    db = SessionLocal()
    try:
        fila = db.query(BotConversation).one()
        assert fila.name == "Ana"
        assert fila.email == "ana@x.co"
        assert fila.route == "asesor"
        assert fila.score and fila.score >= 70
        assert fila.score_rationale, "el porqué del score tiene que quedar guardado"
        # transcript = saludo + turno de la persona + respuesta del bot
        assert len(fila.transcript) == 3
    finally:
        db.close()


def test_el_lead_incompleto_igual_queda_puntuado(app_with_db, monkeypatch):
    """Mucha gente abandona a mitad · sin esto, abandonar = desaparecer."""
    app, SessionLocal = app_with_db
    _mock_motor(monkeypatch, hechos={"nombre": "Ana", "inversion": "15k_30k"})
    with TestClient(app) as client:
        cid = client.post(START, json={}).json()["conversation_id"]
        r = client.post(TURN, json={"conversation_id": cid, "message": "hola"})

    assert r.json()["completed"] is False

    from app.db.models import BotConversation

    db = SessionLocal()
    try:
        fila = db.query(BotConversation).one()
        assert fila.route is not None, "un lead a medias sigue sirviéndole al equipo"
        assert fila.is_completed is False
    finally:
        db.close()


def test_las_alarmas_se_guardan(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _mock_motor(monkeypatch, hechos={"inversion": "under_5k", "visa_usa_negada": True})
    with TestClient(app) as client:
        cid = client.post(START, json={}).json()["conversation_id"]
        client.post(TURN, json={"conversation_id": cid, "message": "mil dólares"})

    from app.db.models import BotConversation

    db = SessionLocal()
    try:
        fila = db.query(BotConversation).one()
        assert fila.route == "descartar"
        assert len(fila.alarms) == 2
    finally:
        db.close()


def test_turn_con_conversacion_inexistente_da_404(app_with_db):
    app, _ = app_with_db
    with TestClient(app) as client:
        r = client.post(
            TURN,
            json={
                "conversation_id": "00000000-0000-0000-0000-000000000000",
                "message": "hola",
            },
        )

    assert r.status_code == 404


def test_mensaje_demasiado_largo_se_rechaza(app_with_db):
    """Un mensaje de 50KB infla el prompt de cada turno · y cada turno cuesta."""
    app, _ = app_with_db
    with TestClient(app) as client:
        cid = client.post(START, json={}).json()["conversation_id"]
        r = client.post(TURN, json={"conversation_id": cid, "message": "x" * 5000})

    assert r.status_code == 422


def test_conversacion_interminable_se_corta(app_with_db, monkeypatch):
    """Endpoint público + IA = vector de gasto. Sin tope es una factura abierta."""
    app, SessionLocal = app_with_db
    _mock_motor(monkeypatch)
    from app.api.v1.bot import MAX_TURNOS
    from app.db.models import BotConversation

    with TestClient(app) as client:
        cid = client.post(START, json={}).json()["conversation_id"]

        db = SessionLocal()
        try:
            fila = db.query(BotConversation).one()
            fila.transcript = [{"role": "user", "content": "x"}] * (MAX_TURNOS * 2)
            db.commit()
        finally:
            db.close()

        r = client.post(TURN, json={"conversation_id": cid, "message": "otra vez"})

    assert r.status_code == 429


# ---------------------------------------------------------------------------
# Bandeja · solo el equipo
# ---------------------------------------------------------------------------


def test_la_bandeja_exige_rol_de_equipo(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    _usuario(SessionLocal, "alumno.bot@grasshopper.dev", UserRole.STUDENT)
    with TestClient(app) as client:
        h = _headers(client, "alumno.bot@grasshopper.dev")
        r = client.get(LEADS, headers=h)

    assert r.status_code == 403


def test_la_bandeja_sin_token_no_expone_leads(app_with_db):
    app, _ = app_with_db
    with TestClient(app) as client:
        r = client.get(LEADS)

    assert r.status_code in (401, 403)


def test_el_equipo_ve_los_leads_y_puede_filtrar(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    _usuario(SessionLocal, "comercial.bot@grasshopper.dev", UserRole.GH_COMMERCIAL)
    _mock_motor(monkeypatch, hechos={"inversion": "under_5k"})

    with TestClient(app) as client:
        cid = client.post(START, json={}).json()["conversation_id"]
        client.post(TURN, json={"conversation_id": cid, "message": "mil dólares"})

        h = _headers(client, "comercial.bot@grasshopper.dev")
        todos = client.get(LEADS, headers=h)
        descartados = client.get(f"{LEADS}?route=descartar", headers=h)
        asesor = client.get(f"{LEADS}?route=asesor", headers=h)

    assert todos.status_code == 200, todos.text
    assert len(todos.json()) == 1
    assert len(descartados.json()) == 1
    assert len(asesor.json()) == 0
    assert descartados.json()[0]["alarms"], "el asesor necesita ver la alarma"
