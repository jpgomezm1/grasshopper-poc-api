"""A3 / P1-13 · Preguntas previas y edición de la Hoja de Vida · Sprint 3.

Feedback literal de la clienta:

    "Hoja de vida: antes de generarla debe preguntar QUÉ HAGO ACTUALMENTE y EN QUÉ
     COLEGIO ESTUDIO (si estoy en colegio). El resto (integrar perfiles + tests +
     lo subido) está muy chévere. Además DEBE PODER EDITARSE (habrá cosas que uno
     quiera quitar o mejorar)."

Son tres pedidos y cada uno tiene su forma de incumplirse sin que se note:

  1. "ANTES de generarla" → poner la pregunta como un aviso saltable y generar
     igual. Por eso el PDF responde 409 mientras falten respuestas.
  2. "SI estoy en colegio" → preguntar el colegio a todo el mundo, incluido a
     quien ya trabaja. Es condicional.
  3. "debe poder editarse … QUITAR o mejorar" → dejar reescribir textos pero no
     quitar nada. Se prueban las dos.

Y una cuarta, tácita: sobre el resto dijo "está muy chévere", así que integrar
perfil + tests + actividades **no debe cambiar**.
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
            name="Estudiante A3",
            role=UserRole.STUDENT,
            onboarding_status=OnboardingStatus.NOT_STARTED,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _headers(client, email):
    r = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


BASE = "/api/v1/me/cv"


# ---------------------------------------------------------------------------
# 1 · "ANTES de generarla debe preguntar"
# ---------------------------------------------------------------------------


def test_sin_responder_no_se_genera_el_pdf(app_with_db):
    """Es lo que la separa de un aviso decorativo: si el PDF sale igual, no se
    cumplió el "antes"."""
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a3.uno@grasshopper.dev")

    with TestClient(app) as client:
        h = _headers(client, "a3.uno@grasshopper.dev")
        r = client.get(BASE, headers=h)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "cv_profile_incomplete"
        assert "current_occupation" in r.json()["detail"]["missing"]


def test_el_front_sabe_que_falta_y_que_opciones_ofrecer(app_with_db):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a3.dos@grasshopper.dev")

    with TestClient(app) as client:
        h = _headers(client, "a3.dos@grasshopper.dev")
        r = client.get(f"{BASE}/profile", headers=h)
        assert r.status_code == 200
        data = r.json()
        assert data["ready"] is False
        assert data["missing"] == ["current_occupation"]
        # Y viene la lista de opciones para poder preguntarlo.
        valores = {o["value"] for o in data["occupation_choices"]}
        assert "school" in valores and "working" in valores


def test_responder_habilita_la_generacion(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a3.tres@grasshopper.dev")

    from app.services import cv_pdf_service

    # `**_variante` absorbe estandar/estilo/incluir_foto (migración 063).
    monkeypatch.setattr(
        cv_pdf_service, "render_cv_pdf", lambda _cv, **_variante: b"%PDF-1.4 fake"
    )

    with TestClient(app) as client:
        h = _headers(client, "a3.tres@grasshopper.dev")
        r = client.put(
            f"{BASE}/profile",
            json={"current_occupation": "working", "occupation_detail": "Panadería"},
            headers=h,
        )
        assert r.status_code == 200
        assert r.json()["ready"] is True

        assert client.get(BASE, headers=h).status_code == 200


# ---------------------------------------------------------------------------
# 2 · "si estoy en colegio" · la segunda pregunta es CONDICIONAL
# ---------------------------------------------------------------------------


def test_al_estudiante_de_colegio_se_le_pide_el_colegio(app_with_db):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a3.cuatro@grasshopper.dev")

    with TestClient(app) as client:
        h = _headers(client, "a3.cuatro@grasshopper.dev")
        r = client.put(
            f"{BASE}/profile", json={"current_occupation": "school"}, headers=h
        )
        data = r.json()
        assert data["requires_school"] is True
        assert data["ready"] is False
        assert data["missing"] == ["school_name"]

        # Con el colegio ya queda completo.
        r = client.put(
            f"{BASE}/profile", json={"school_name": "Colegio Cumbres"}, headers=h
        )
        assert r.json()["ready"] is True


def test_a_quien_trabaja_NO_se_le_pide_colegio(app_with_db):
    """Ella escribió "(si estoy en colegio)". Preguntarle el colegio a alguien que
    ya trabaja es la clase de pregunta sin sentido que criticó Sandra."""
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a3.cinco@grasshopper.dev")

    with TestClient(app) as client:
        h = _headers(client, "a3.cinco@grasshopper.dev")
        r = client.put(
            f"{BASE}/profile", json={"current_occupation": "working"}, headers=h
        )
        data = r.json()
        assert data["requires_school"] is False
        assert data["ready"] is True
        assert data["missing"] == []


def test_cambiar_de_colegio_a_trabajar_no_deja_el_colegio_viejo(app_with_db):
    """Si no, el PDF sale diciendo que estudia en un colegio que ya dejó."""
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a3.seis@grasshopper.dev")

    with TestClient(app) as client:
        h = _headers(client, "a3.seis@grasshopper.dev")
        client.put(
            f"{BASE}/profile",
            json={"current_occupation": "school", "school_name": "Colegio Cumbres"},
            headers=h,
        )
        r = client.put(
            f"{BASE}/profile", json={"current_occupation": "working"}, headers=h
        )
        assert r.json()["school_name"] is None


def test_una_ocupacion_inventada_se_rechaza(app_with_db):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a3.siete@grasshopper.dev")

    with TestClient(app) as client:
        h = _headers(client, "a3.siete@grasshopper.dev")
        r = client.put(
            f"{BASE}/profile", json={"current_occupation": "astronauta"}, headers=h
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# 3 · "debe poder editarse … quitar o mejorar"
# ---------------------------------------------------------------------------


def _con_perfil(SessionLocal, user_id):
    """Deja un perfil consolidado cacheado para tener contenido que editar."""
    from app.db.models import ConsolidatedProfileCache

    db = SessionLocal()
    try:
        db.add(
            ConsolidatedProfileCache(
                user_id=user_id,
                profile_hash="h",
                profile_data={
                    "summary_narrative": "Resumen generado por la IA.",
                    "strengths": ["Analítica", "Constante", "Curiosa"],
                    "interests": ["Diseño", "Biología"],
                    "values": ["Autonomía"],
                    "suggested_career_paths": ["Diseño industrial", "Bioingeniería"],
                },
                recommendations_data=[],
            )
        )
        db.commit()
    finally:
        db.close()


def test_puede_mejorar_el_texto(app_with_db):
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a3.ocho@grasshopper.dev")
    _con_perfil(SessionLocal, uid)

    with TestClient(app) as client:
        h = _headers(client, "a3.ocho@grasshopper.dev")
        client.put(f"{BASE}/profile", json={"current_occupation": "working"}, headers=h)

        r = client.get(f"{BASE}/profile", headers=h)
        assert r.json()["content"]["summary"] == "Resumen generado por la IA."

        r = client.put(
            f"{BASE}/profile",
            json={"overrides": {"summary": "Lo escribo con mis palabras."}},
            headers=h,
        )
        assert r.json()["content"]["summary"] == "Lo escribo con mis palabras."

        # Y persiste.
        r = client.get(f"{BASE}/profile", headers=h)
        assert r.json()["content"]["summary"] == "Lo escribo con mis palabras."


def test_puede_quitar_una_seccion_entera(app_with_db):
    """"Habrá cosas que uno quiera QUITAR": una cadena vacía es una decisión, no
    un error de validación."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a3.nueve@grasshopper.dev")
    _con_perfil(SessionLocal, uid)

    with TestClient(app) as client:
        h = _headers(client, "a3.nueve@grasshopper.dev")
        client.put(f"{BASE}/profile", json={"current_occupation": "working"}, headers=h)
        r = client.put(
            f"{BASE}/profile", json={"overrides": {"summary": ""}}, headers=h
        )
        assert r.json()["content"]["summary"] is None


def test_puede_quitar_items_de_una_lista(app_with_db):
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a3.diez@grasshopper.dev")
    _con_perfil(SessionLocal, uid)

    with TestClient(app) as client:
        h = _headers(client, "a3.diez@grasshopper.dev")
        client.put(f"{BASE}/profile", json={"current_occupation": "working"}, headers=h)
        r = client.put(
            f"{BASE}/profile",
            json={"overrides": {"strengths": ["Analítica"]}},
            headers=h,
        )
        assert r.json()["content"]["strengths"] == ["Analítica"]


def test_editar_una_cosa_no_pisa_las_otras(app_with_db):
    """La pantalla guarda por partes; si cada PUT borrara lo anterior, el
    estudiante perdería sus ediciones sin enterarse."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a3.once@grasshopper.dev")
    _con_perfil(SessionLocal, uid)

    with TestClient(app) as client:
        h = _headers(client, "a3.once@grasshopper.dev")
        client.put(f"{BASE}/profile", json={"current_occupation": "working"}, headers=h)
        client.put(f"{BASE}/profile", json={"overrides": {"summary": "Mío."}}, headers=h)
        r = client.put(
            f"{BASE}/profile", json={"overrides": {"headline": "Mi titular."}}, headers=h
        )
        assert r.json()["content"]["summary"] == "Mío."
        assert r.json()["content"]["headline"] == "Mi titular."

        # Y responder de nuevo una pregunta tampoco borra las ediciones.
        r = client.put(
            f"{BASE}/profile", json={"occupation_detail": "Panadería"}, headers=h
        )
        assert r.json()["content"]["summary"] == "Mío."


def test_lo_editado_es_lo_que_sale_en_el_pdf(app_with_db, monkeypatch):
    """La vista previa y la descarga comparten el mismo armado. Si no, el
    estudiante edita una cosa y descarga otra."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a3.doce@grasshopper.dev")
    _con_perfil(SessionLocal, uid)

    from app.services import cv_pdf_service

    capturado = {}

    def _fake(cv, **_variante):
        capturado["summary"] = cv.summary
        capturado["ocupacion"] = cv.current_occupation
        return b"%PDF-1.4 fake"

    monkeypatch.setattr(cv_pdf_service, "render_cv_pdf", _fake)

    with TestClient(app) as client:
        h = _headers(client, "a3.doce@grasshopper.dev")
        client.put(
            f"{BASE}/profile",
            json={"current_occupation": "working", "occupation_detail": "Panadería"},
            headers=h,
        )
        client.put(
            f"{BASE}/profile",
            json={"overrides": {"summary": "Editado por mí."}},
            headers=h,
        )
        assert client.get(BASE, headers=h).status_code == 200

    assert capturado["summary"] == "Editado por mí."
    # Y la respuesta a "qué haces actualmente" llega al PDF.
    assert "Panadería" in capturado["ocupacion"]


# ---------------------------------------------------------------------------
# 4 · Lo que NO debía cambiar · "el resto está muy chévere"
# ---------------------------------------------------------------------------


def test_sigue_siendo_solo_para_estudiantes(app_with_db):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    app, SessionLocal = app_with_db
    db = SessionLocal()
    try:
        db.add(
            User(
                email="a3.advisor@grasshopper.dev",
                hashed_password=get_password_hash("testpass123"),
                name="Advisor",
                role=UserRole.GH_ADVISOR,
                onboarding_status=OnboardingStatus.NOT_STARTED,
            )
        )
        db.commit()
    finally:
        db.close()

    with TestClient(app) as client:
        h = _headers(client, "a3.advisor@grasshopper.dev")
        assert client.get(f"{BASE}/profile", headers=h).status_code == 403
        assert client.put(f"{BASE}/profile", json={}, headers=h).status_code == 403


def test_requiere_autenticacion(app_with_db):
    app, _ = app_with_db
    with TestClient(app) as client:
        assert client.get(f"{BASE}/profile").status_code in (401, 403)


def test_el_contenido_generado_sigue_llegando_sin_editar_nada(app_with_db):
    """Sobre integrar perfil + tests + lo subido dijo "está muy chévere": eso no
    se tocó, y sin overrides tiene que verse igual que antes."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a3.trece@grasshopper.dev")
    _con_perfil(SessionLocal, uid)

    with TestClient(app) as client:
        h = _headers(client, "a3.trece@grasshopper.dev")
        client.put(f"{BASE}/profile", json={"current_occupation": "working"}, headers=h)
        contenido = client.get(f"{BASE}/profile", headers=h).json()["content"]

    assert contenido["summary"] == "Resumen generado por la IA."
    assert contenido["strengths"] == ["Analítica", "Constante", "Curiosa"]
    assert contenido["career_paths"] == ["Diseño industrial", "Bioingeniería"]
