"""La ficha académica · P3 de la revisión Sprint 2.

Verónica (Paso 3): *"para construir esto es importante preguntarle al
estudiante su GPA (promedio acumulado) … ¿tienes AP? ¿cuántas? ¿qué puntajes?
¿tienes SAT?"*.

## Por qué casi todo aquí es validación

Esta ficha alimenta decisiones de admisión. Un GPA de 42, un SAT de 95 o un IB
de 60 no son "datos imperfectos": son números que harían que el producto le
dijera a alguien que una universidad es alcanzable cuando no lo es. Y el
estudiante no tiene forma de detectarlo — el badge se vería igual de convincente.

  (a) ⭐ el GPA no entra sin su escala · un 4.2 no significa nada suelto
  (b) ⭐ escalas de fantasía se rechazan
  (c) ⭐ rangos imposibles se rechazan (GPA, SAT, AP, IB)
  (d) ⭐ o entra entera o no entra · nada de medio guardado
  (e) el porcentaje normaliza bien entre sistemas
  (f) las filas de AP vacías se descartan
  (g) actualizar no duplica la ficha
  (h) ⭐ sólo el dueño · un padre no puede
"""
from __future__ import annotations

import re
from datetime import date

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
RUTA = "/api/v1/me/academic-profile"


def _usuario(SessionLocal, email, rol="STUDENT"):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash(CLAVE),
            name="Camila",
            role=getattr(UserRole, rol),
            onboarding_status=OnboardingStatus.NOT_STARTED,
            grade=11,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _sesion(app, S, email="alumno@x.com", rol="STUDENT"):
    _usuario(S, email, rol)
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"email": email, "password": CLAVE})
    assert r.status_code == 200, r.text
    return client, {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# (a) (b) ⭐ el GPA y su escala
# ---------------------------------------------------------------------------

def test_un_gpa_sin_escala_no_entra(app_with_db):
    """⭐ Un 4.2 no significa nada suelto.

    Sobre 5.0 es notable; sobre 4.0 es imposible. Guardarlo sin la escala
    dejaría al clasificador comparando peras con manzanas.
    """
    app, S = app_with_db
    client, h = _sesion(app, S)

    r = client.put(RUTA, json={"gpa": 4.2}, headers=h)
    assert r.status_code == 422
    assert "escala" in r.json()["detail"].lower()


def test_una_escala_sin_gpa_tampoco(app_with_db):
    app, S = app_with_db
    client, h = _sesion(app, S)
    assert client.put(RUTA, json={"gpa_scale": 5.0}, headers=h).status_code == 422


def test_una_escala_inventada_se_rechaza(app_with_db):
    # "Sobre 7.3" no es una escala, es un error de dedo. Aceptarla haria que el
    # porcentaje normalizado saliera plausible y falso.
    app, S = app_with_db
    client, h = _sesion(app, S)

    r = client.put(RUTA, json={"gpa": 6.0, "gpa_scale": 7.3}, headers=h)
    assert r.status_code == 422
    assert "escala" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# (c) ⭐ rangos imposibles
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload,pista",
    [
        ({"gpa": 42, "gpa_scale": 5.0}, "promedio"),
        ({"sat_score": 95}, "sat"),
        ({"sat_score": 2400}, "sat"),
        ({"ib_predicted_total": 60}, "diploma"),
        ({"ap_scores": [{"materia": "Calculus AB", "puntaje": 9}]}, "ap"),
    ],
)
def test_numeros_imposibles_se_rechazan_con_su_motivo(app_with_db, payload, pista):
    app, S = app_with_db
    client, h = _sesion(app, S)

    r = client.put(RUTA, json=payload, headers=h)
    assert r.status_code == 422, f"{payload} deberia rechazarse"
    assert pista in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# (d) ⭐ todo o nada
# ---------------------------------------------------------------------------

def test_si_un_campo_es_invalido_no_se_guarda_ninguno(app_with_db):
    """⭐ Nada de fichas a medio llenar.

    Si el SAT es válido pero el IB no, guardar el SAT dejaría al estudiante
    creyendo que corrigió cuando sólo entró la mitad.
    """
    app, S = app_with_db
    client, h = _sesion(app, S)

    r = client.put(RUTA, json={"sat_score": 1200, "ib_predicted_total": 99}, headers=h)
    assert r.status_code == 422

    assert client.get(RUTA, headers=h).json()["sat_score"] is None


# ---------------------------------------------------------------------------
# (e) el porcentaje · lo único comparable entre sistemas
# ---------------------------------------------------------------------------

def test_el_porcentaje_traduce_entre_escalas(app_with_db):
    app, S = app_with_db
    client, h = _sesion(app, S)

    colombiano = client.put(RUTA, json={"gpa": 4.2, "gpa_scale": 5.0}, headers=h).json()
    assert colombiano["gpa_porcentaje"] == 84.0

    gringo = client.put(RUTA, json={"gpa": 3.8, "gpa_scale": 4.0}, headers=h).json()
    assert gringo["gpa_porcentaje"] == 95.0

    # Y aqui esta el porque de todo esto: crudos, 4.2 > 3.8. Normalizados es al
    # reves. Comparar sin traducir clasificaria al contrario.
    assert 4.2 > 3.8
    assert colombiano["gpa_porcentaje"] < gringo["gpa_porcentaje"]


# ---------------------------------------------------------------------------
# (f) (g) higiene
# ---------------------------------------------------------------------------

def test_las_filas_de_ap_vacias_no_se_guardan(app_with_db):
    # Una entrada que el estudiante abrio y no lleno no es un dato · guardarla
    # ensuciaria el CV y el reporte al colegio con lineas en blanco.
    app, S = app_with_db
    client, h = _sesion(app, S)

    r = client.put(
        RUTA,
        json={"ap_scores": [{"materia": "Biology", "puntaje": 4}, {"materia": "   "}]},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["ap_scores"] == [{"materia": "Biology", "puntaje": 4}]


def test_actualizar_no_duplica_la_ficha(app_with_db):
    app, S = app_with_db
    client, h = _sesion(app, S)

    client.put(RUTA, json={"sat_score": 1200}, headers=h)
    client.put(RUTA, json={"sat_score": 1310}, headers=h)

    assert client.get(RUTA, headers=h).json()["sat_score"] == 1310

    from app.db.models import StudentAcademicProfile
    db = S()
    try:
        assert db.query(StudentAcademicProfile).count() == 1
    finally:
        db.close()


def test_la_ficha_vacia_se_lee_sin_reventar(app_with_db):
    # El vacio explicito (claves en None) y no ausente: "existe y esta sin
    # llenar" es distinto de "esto no aplica".
    app, S = app_with_db
    client, h = _sesion(app, S)

    r = client.get(RUTA, headers=h)
    assert r.status_code == 200
    assert r.json()["gpa"] is None
    assert r.json()["ap_scores"] == []
    assert r.json()["listo_para_clasificar"] is False


def test_con_gpa_completo_queda_listo_para_clasificar(app_with_db):
    app, S = app_with_db
    client, h = _sesion(app, S)

    r = client.put(RUTA, json={"gpa": 4.2, "gpa_scale": 5.0}, headers=h)
    assert r.json()["listo_para_clasificar"] is True


# ---------------------------------------------------------------------------
# (h) ⭐ sólo el dueño
# ---------------------------------------------------------------------------

def test_un_padre_no_puede_tocar_la_ficha(app_with_db):
    app, S = app_with_db
    client, h = _sesion(app, S, email="papa@x.com", rol="PARENT")

    assert client.get(RUTA, headers=h).status_code == 403
    assert client.put(RUTA, json={"sat_score": 1600}, headers=h).status_code == 403


def test_sin_token_no_se_puede(app_with_db):
    app, _ = app_with_db
    assert TestClient(app).get(RUTA).status_code in (401, 403)
