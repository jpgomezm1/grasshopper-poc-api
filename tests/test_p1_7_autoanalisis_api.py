"""P1-7 / A6 · Los endpoints del autoanálisis, sobre HTTP real · Sprint 3.

`test_p1_7_autoanalisis.py` cubre la lógica pura (formateo, orden, hash). Esto cubre
el contrato HTTP contra una base de verdad: que se persista, que sobreviva a un
GET posterior, que el pre-llenado desde OTRO test funcione, y que nadie pueda leer
ni escribir el autoanálisis de otra persona.

Se corre contra SQLite en memoria. NO se toca la base compartida: el `.env` local
del backend apunta al mismo Neon que usa producción, así que cualquier e2e "de
verdad" contra ese servidor escribiría datos reales.
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


def _student(SessionLocal, email):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash("testpass123"),
            name="Estudiante",
            role=UserRole.STUDENT,
            onboarding_status=OnboardingStatus.NOT_STARTED,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _test_result(SessionLocal, user_id, test_id="holland"):
    from app.db.models import VocationalTestResult

    db = SessionLocal()
    try:
        r = VocationalTestResult(
            user_id=user_id,
            test_id=test_id,
            answers={"q1": "a"},  # NOT NULL en el modelo
            scores={"A": 80, "E": 70, "S": 62},
            source="internal",
        )
        db.add(r)
        db.commit()
    finally:
        db.close()


def _headers(client, email):
    r = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


BASE = "/api/v1/vocational-tests"


# ---------------------------------------------------------------------------
# Guardar y recuperar
# ---------------------------------------------------------------------------


def test_guardar_y_recuperar_el_top3(app_with_db):
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a6.uno@grasshopper.dev")
    _test_result(SessionLocal, uid)

    with TestClient(app) as client:
        h = _headers(client, "a6.uno@grasshopper.dev")

        # Antes de responder: vacío, no 404.
        r = client.get(f"{BASE}/holland/self-assessment", headers=h)
        assert r.status_code == 200
        assert r.json()["careers"] == []
        assert r.json()["answered_at"] is None

        r = client.put(
            f"{BASE}/holland/self-assessment",
            json={"careers": ["Diseño industrial", "Arquitectura", "Publicidad"]},
            headers=h,
        )
        assert r.status_code == 200, r.text
        assert r.json()["careers"] == [
            "Diseño industrial", "Arquitectura", "Publicidad",
        ]
        assert r.json()["answered_at"]

        # Y sobrevive · esto es lo que el estudiante ve al recargar la pantalla.
        r = client.get(f"{BASE}/holland/self-assessment", headers=h)
        assert r.json()["careers"] == [
            "Diseño industrial", "Arquitectura", "Publicidad",
        ]


def test_se_puede_corregir_la_respuesta(app_with_db):
    """El botón "Ajustar mi respuesta": la autopercepción cambia, es el punto."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a6.dos@grasshopper.dev")
    _test_result(SessionLocal, uid)

    with TestClient(app) as client:
        h = _headers(client, "a6.dos@grasshopper.dev")
        client.put(
            f"{BASE}/holland/self-assessment",
            json={"careers": ["Contabilidad"]}, headers=h,
        )
        client.put(
            f"{BASE}/holland/self-assessment",
            json={"careers": ["Diseño gráfico", "Publicidad"]}, headers=h,
        )
        r = client.get(f"{BASE}/holland/self-assessment", headers=h)
        assert r.json()["careers"] == ["Diseño gráfico", "Publicidad"]


def test_se_recortan_espacios_y_se_ignoran_vacios(app_with_db):
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a6.tres@grasshopper.dev")
    _test_result(SessionLocal, uid)

    with TestClient(app) as client:
        h = _headers(client, "a6.tres@grasshopper.dev")
        r = client.put(
            f"{BASE}/holland/self-assessment",
            json={"careers": ["  Medicina  ", "", "   ", "Biología"]},
            headers=h,
        )
        assert r.json()["careers"] == ["Medicina", "Biología"]


def test_maximo_tres_opciones(app_with_db):
    """Ella pidió 3. Un cliente que mande más no debe ensanchar el dato."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a6.cuatro@grasshopper.dev")
    _test_result(SessionLocal, uid)

    with TestClient(app) as client:
        h = _headers(client, "a6.cuatro@grasshopper.dev")
        r = client.put(
            f"{BASE}/holland/self-assessment",
            json={"careers": ["A", "B", "C", "D", "E"]}, headers=h,
        )
        assert r.json()["careers"] == ["A", "B", "C"]


def test_no_se_puede_guardar_vacio(app_with_db):
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a6.cinco@grasshopper.dev")
    _test_result(SessionLocal, uid)

    with TestClient(app) as client:
        h = _headers(client, "a6.cinco@grasshopper.dev")
        r = client.put(
            f"{BASE}/holland/self-assessment",
            json={"careers": ["", "  "]}, headers=h,
        )
        assert r.status_code == 400


def test_sin_haber_hecho_el_test_da_404(app_with_db):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a6.seis@grasshopper.dev")

    with TestClient(app) as client:
        h = _headers(client, "a6.seis@grasshopper.dev")
        assert client.get(f"{BASE}/holland/self-assessment", headers=h).status_code == 404
        r = client.put(
            f"{BASE}/holland/self-assessment",
            json={"careers": ["Medicina"]}, headers=h,
        )
        assert r.status_code == 404


def test_requiere_estar_autenticado(app_with_db):
    app, SessionLocal = app_with_db
    with TestClient(app) as client:
        r = client.get(f"{BASE}/holland/self-assessment")
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Pre-llenado entre tests · la queja de fatiga de cuestionarios
# ---------------------------------------------------------------------------


def test_el_segundo_test_viene_prellenado_con_el_primero(app_with_db):
    """Esta pregunta aparece después de CADA test. Si en el octavo lo obligamos a
    escribir tres carreras desde cero, reproducimos la fatiga que ella criticó."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a6.siete@grasshopper.dev")
    _test_result(SessionLocal, uid, "holland")
    _test_result(SessionLocal, uid, "bigfive")

    with TestClient(app) as client:
        h = _headers(client, "a6.siete@grasshopper.dev")
        client.put(
            f"{BASE}/holland/self-assessment",
            json={"careers": ["Diseño industrial", "Arquitectura"]}, headers=h,
        )

        r = client.get(f"{BASE}/bigfive/self-assessment", headers=h)
        assert r.json()["careers"] == []  # todavía no respondió ESTE
        assert r.json()["previous_careers"] == ["Diseño industrial", "Arquitectura"]


def test_el_propio_no_se_confunde_con_el_previo(app_with_db):
    """Ya respondido este test: `previous_careers` no debe pisar lo suyo."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a6.ocho@grasshopper.dev")
    _test_result(SessionLocal, uid, "holland")
    _test_result(SessionLocal, uid, "bigfive")

    with TestClient(app) as client:
        h = _headers(client, "a6.ocho@grasshopper.dev")
        client.put(
            f"{BASE}/holland/self-assessment",
            json={"careers": ["Contabilidad"]}, headers=h,
        )
        client.put(
            f"{BASE}/bigfive/self-assessment",
            json={"careers": ["Psicología"]}, headers=h,
        )
        r = client.get(f"{BASE}/bigfive/self-assessment", headers=h)
        assert r.json()["careers"] == ["Psicología"]


# ---------------------------------------------------------------------------
# Aislamiento entre usuarios
# ---------------------------------------------------------------------------


def test_nadie_ve_el_autoanalisis_de_otro(app_with_db):
    app, SessionLocal = app_with_db
    uid_a = _student(SessionLocal, "a6.ana@grasshopper.dev")
    _student(SessionLocal, "a6.beto@grasshopper.dev")
    _test_result(SessionLocal, uid_a, "holland")

    with TestClient(app) as client:
        ha = _headers(client, "a6.ana@grasshopper.dev")
        client.put(
            f"{BASE}/holland/self-assessment",
            json={"careers": ["Medicina"]}, headers=ha,
        )

        # Beto no hizo el test: no existe ese resultado PARA ÉL.
        hb = _headers(client, "a6.beto@grasshopper.dev")
        r = client.get(f"{BASE}/holland/self-assessment", headers=hb)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Lo declarado llega al perfil · la mitad del pedido que es fácil incumplir
# ---------------------------------------------------------------------------


def test_lo_declarado_entra_a_los_inputs_del_perfil(app_with_db):
    """Ella no pidió solo la pregunta: pidió que el sistema ofrezca opciones
    "según su top-3". Si `gather_user_inputs` no lo recoge, el formulario es
    decorativo y el reclamo sigue abierto."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a6.nueve@grasshopper.dev")
    _test_result(SessionLocal, uid, "holland")

    with TestClient(app) as client:
        h = _headers(client, "a6.nueve@grasshopper.dev")
        client.put(
            f"{BASE}/holland/self-assessment",
            json={"careers": ["Diseño industrial", "Arquitectura"]}, headers=h,
        )

    from app.db.models import User
    from app.services import consolidation_service as cs

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == uid).first()
        inputs = cs.gather_user_inputs(db, user)
        assert inputs["tests"][0]["self_assessment"] == [
            "Diseño industrial", "Arquitectura",
        ]
        # Y aterriza en el texto que ve el modelo, con el orden intacto.
        bloque = cs._format_tests_block(inputs["tests"])
        assert "1. Diseño industrial" in bloque
        assert "2. Arquitectura" in bloque
    finally:
        db.close()


def test_responder_invalida_la_cache_del_perfil(app_with_db):
    """Si la caché de 24h sobrevive, el estudiante ve un perfil que ignora lo que
    acaba de escribir — exactamente lo que se está corrigiendo."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a6.diez@grasshopper.dev")
    _test_result(SessionLocal, uid, "holland")

    from app.db.models import ConsolidatedProfileCache

    db = SessionLocal()
    try:
        db.add(
            ConsolidatedProfileCache(
                user_id=uid,
                profile_hash="hash-viejo",
                profile_data={"summary_narrative": "perfil previo"},
                recommendations_data=[],
                invalidated_at=None,
            )
        )
        db.commit()
    finally:
        db.close()

    with TestClient(app) as client:
        h = _headers(client, "a6.diez@grasshopper.dev")
        r = client.put(
            f"{BASE}/holland/self-assessment",
            json={"careers": ["Diseño industrial"]}, headers=h,
        )
        assert r.status_code == 200

    db = SessionLocal()
    try:
        row = (
            db.query(ConsolidatedProfileCache)
            .filter(ConsolidatedProfileCache.user_id == uid)
            .first()
        )
        assert row.invalidated_at is not None
    finally:
        db.close()
