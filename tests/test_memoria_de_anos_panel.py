"""La consejera ve la memoria entre años de SU estudiante · cierra P1.

Verónica (Grado 10, Paso 1) pidió el "Check-in de Evolución" para el
estudiante. Esto es su otra mitad: que la consejera también lo vea, que es lo
que convierte "el sistema recuerda" en "la persona que te acompaña recuerda".

## Por qué estos tests son casi todos de acceso

`GET /year-checkin` se escribió sin superficie IDOR a propósito — su propio
docstring dice *"opera siempre sobre `current_user` … no hay superficie IDOR
que verificar"*. Este endpoint SÍ recibe un `user_id` ajeno, así que introduce
exactamente la superficie que aquel evitaba. Si la guarda falla, un colegio lee
lo que un menor de otro colegio contó sobre sí mismo.

  (a) ⭐ la psicóloga ve a su estudiante
  (b) ⭐ un colegio NO ve al estudiante de otro · 404, no 403
  (c) ⭐ un estudiante no puede leer el panel
  (d) sin token, nada
  (e) sin memoria responde honesto, no revienta
  (f) ⭐ NO trae el mensaje redactado para el estudiante
"""
from __future__ import annotations

import re

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


CLAVE = "testpass123"


def _colegio(S, nombre):
    from app.db.models import School

    db = S()
    try:
        s = School(name=nombre, slug=re.sub(r"[^a-z0-9]+", "-", nombre.lower()).strip("-"))
        db.add(s)
        db.commit()
        db.refresh(s)
        return s.id
    finally:
        db.close()


def _usuario(S, email, rol, school_id=None, grade=None, answers=None):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = S()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash(CLAVE),
            name="Persona",
            role=getattr(UserRole, rol),
            onboarding_status=OnboardingStatus.NOT_STARTED,
            school_id=school_id,
            grade=grade,
            onboarding_answers=answers,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _snapshot(S, user_id, *, school_year, grade, answers):
    from app.db.models import StudentYearSnapshot

    db = S()
    try:
        db.add(
            StudentYearSnapshot(
                user_id=user_id,
                school_year=school_year,
                grade=grade,
                onboarding_answers_snapshot=answers,
            )
        )
        db.commit()
    finally:
        db.close()


def _login(client, email):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": CLAVE})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _ruta(uid):
    return f"/api/v1/school/me/students/{uid}/memoria-de-anos"


# ---------------------------------------------------------------------------
# (a) ⭐ lo que sí puede
# ---------------------------------------------------------------------------

def test_la_psicologa_ve_la_memoria_de_su_estudiante(app_with_db):
    app, S = app_with_db
    colegio = _colegio(S, "Cumbres")
    alumno = _usuario(
        S, "alumno@x.com", "STUDENT", colegio, grade=10,
        answers={"voice_passion": "ahora quiero medicina"},
    )
    _snapshot(S, alumno, school_year=2026, grade=9,
              answers={"voice_passion": "diseñar videojuegos"})
    _usuario(S, "psy@x.com", "PSYCHOLOGIST", colegio)

    client = TestClient(app)
    r = client.get(_ruta(alumno), headers=_login(client, "psy@x.com"))

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["has_memory"] is True
    assert cuerpo["is_new_grade"] is True
    assert cuerpo["previous"]["grade"] == 9
    assert cuerpo["previous"]["perfil"]["pasion"] == "diseñar videojuegos"
    assert cuerpo["today"]["perfil"]["pasion"] == "ahora quiero medicina"
    assert len(cuerpo["changed_fields"]) == 1


# ---------------------------------------------------------------------------
# (b) (c) (d) ⭐ lo que no
# ---------------------------------------------------------------------------

def test_un_colegio_no_ve_al_estudiante_de_otro(app_with_db):
    """⭐ La guarda que de verdad importa.

    404 y no 403: un 403 confirmaría que ese estudiante existe, que ya es
    información que no le toca.
    """
    app, S = app_with_db
    cumbres = _colegio(S, "Cumbres")
    campestre = _colegio(S, "Campestre")
    ajeno = _usuario(S, "ajeno@x.com", "STUDENT", campestre, grade=10)
    _usuario(S, "psy@x.com", "PSYCHOLOGIST", cumbres)

    client = TestClient(app)
    r = client.get(_ruta(ajeno), headers=_login(client, "psy@x.com"))

    assert r.status_code == 404


def test_un_estudiante_no_entra_al_panel(app_with_db):
    app, S = app_with_db
    colegio = _colegio(S, "Cumbres")
    otro = _usuario(S, "otro@x.com", "STUDENT", colegio, grade=10)
    _usuario(S, "alumno@x.com", "STUDENT", colegio, grade=10)

    client = TestClient(app)
    r = client.get(_ruta(otro), headers=_login(client, "alumno@x.com"))

    assert r.status_code in (403, 404)


def test_sin_token_no_se_puede(app_with_db):
    app, S = app_with_db
    colegio = _colegio(S, "Cumbres")
    alumno = _usuario(S, "alumno@x.com", "STUDENT", colegio, grade=10)

    assert TestClient(app).get(_ruta(alumno)).status_code in (401, 403)


# ---------------------------------------------------------------------------
# (e) (f) el contenido
# ---------------------------------------------------------------------------

def test_sin_memoria_responde_honesto(app_with_db):
    # Un estudiante que nunca paso de anio no tiene con que compararse. Eso se
    # dice, no se inventa un anio anterior.
    app, S = app_with_db
    colegio = _colegio(S, "Cumbres")
    alumno = _usuario(S, "alumno@x.com", "STUDENT", colegio, grade=9)
    _usuario(S, "psy@x.com", "PSYCHOLOGIST", colegio)

    client = TestClient(app)
    cuerpo = client.get(_ruta(alumno), headers=_login(client, "psy@x.com")).json()

    assert cuerpo["has_memory"] is False
    assert cuerpo["previous"] is None
    assert cuerpo["today"]["grade"] == 9


def test_no_trae_el_mensaje_escrito_para_el_estudiante(app_with_db):
    """⭐ El `checkin_message` habla en segunda persona.

    "El año pasado me dijiste que…" está escrito para el estudiante.
    Enseñárselo a la consejera sería ponerle en la boca una conversación que no
    tuvo. Ella recibe los HECHOS.
    """
    app, S = app_with_db
    colegio = _colegio(S, "Cumbres")
    alumno = _usuario(S, "alumno@x.com", "STUDENT", colegio, grade=10)
    _snapshot(S, alumno, school_year=2026, grade=9, answers={"voice_passion": "x"})
    _usuario(S, "psy@x.com", "PSYCHOLOGIST", colegio)

    client = TestClient(app)
    cuerpo = client.get(_ruta(alumno), headers=_login(client, "psy@x.com")).json()

    assert "checkin_message" not in cuerpo
