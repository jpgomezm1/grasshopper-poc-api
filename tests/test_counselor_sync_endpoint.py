"""Counselor Sync · el contrato HTTP y sus permisos (P2).

`test_counselor_sync.py` prueba el servicio. Esto prueba lo que de verdad
expone la aplicación: las rutas, sus guardas de rol y sus códigos.

Importa hacerlo aparte porque **los permisos viven en el router**, no en el
servicio. Un servicio impecable detrás de un endpoint sin guarda deja el avance
de un menor al alcance de cualquiera que sepa la URL.

  (a) hay que estar autenticado
  (b) ⭐ sólo un estudiante envía · un padre o un asesor no
  (c) ⭐ el estudiante NO elige destinatario · va a su colegio y punto
  (d) un B2C sin colegio recibe 409 (no aplica), no 500 (se rompió)
  (e) ⭐ la psicóloga ve SÓLO lo de su colegio
  (f) ⭐ un estudiante no puede leer el buzón del colegio
  (g) marcar leído un reporte de otro colegio da 404, no 403 · confirmar que
      existe pero es ajeno ya filtra información

SQLite in-memory + TestClient · mismo patrón que `test_year_checkin_endpoint.py`.
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


def _colegio(SessionLocal, nombre):
    from app.db.models import School

    db = SessionLocal()
    try:
        s = School(name=nombre, slug=re.sub(r"[^a-z0-9]+", "-", nombre.lower()).strip("-"))
        db.add(s)
        db.commit()
        db.refresh(s)
        return s.id
    finally:
        db.close()


def _usuario(SessionLocal, email, rol, *, school_id=None, **extra):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash(CLAVE),
            name="Persona",
            role=getattr(UserRole, rol),
            onboarding_status=OnboardingStatus.NOT_STARTED,
            school_id=school_id,
            onboarding_answers={"voice_passion": "diseñar videojuegos"},
            **extra,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _login(client, email):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": CLAVE})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# (a) autenticación
# ---------------------------------------------------------------------------

def test_sin_token_no_se_puede_ni_mirar(app_with_db):
    app, _ = app_with_db
    client = TestClient(app)

    assert client.get("/api/v1/me/counselor-sync/preview").status_code in (401, 403)
    assert client.get("/api/v1/school/counselor-sync").status_code in (401, 403)


# ---------------------------------------------------------------------------
# (b) y (c) ⭐ sólo el estudiante, y sólo lo suyo
# ---------------------------------------------------------------------------

def test_un_estudiante_envia_su_avance_a_su_colegio(app_with_db):
    app, S = app_with_db
    colegio = _colegio(S, "Cumbres")
    _usuario(S, "alumno@x.com", "STUDENT", school_id=colegio, grade=10)
    client = TestClient(app)
    t = _login(client, "alumno@x.com")

    previa = client.get("/api/v1/me/counselor-sync/preview", headers=_h(t))
    assert previa.status_code == 200
    assert previa.json()["puede_enviar"] is True

    envio = client.post("/api/v1/me/counselor-sync", json={"nota": "Tengo dudas."}, headers=_h(t))
    assert envio.status_code == 201, envio.text
    assert envio.json()["student_note"] == "Tengo dudas."
    # El contenido va congelado en la respuesta · no una promesa de calcularlo.
    assert "que_le_falta" in envio.json()["content"]


def test_un_padre_no_puede_enviar_avances(app_with_db):
    app, S = app_with_db
    colegio = _colegio(S, "Cumbres")
    _usuario(S, "papa@x.com", "PARENT", school_id=colegio)
    client = TestClient(app)
    t = _login(client, "papa@x.com")

    assert client.post("/api/v1/me/counselor-sync", json={}, headers=_h(t)).status_code == 403


def test_el_cuerpo_no_admite_destinatario(app_with_db):
    """⭐ No hay a quién mandárselo: va al colegio del que envía.

    Si el endpoint aceptara un `student_id` o un `school_id`, sería una
    invitación a mandar el avance de otro. Se comprueba mandando basura: se
    ignora, no se obedece.
    """
    app, S = app_with_db
    cumbres = _colegio(S, "Cumbres")
    otro = _colegio(S, "Otro Colegio")
    _usuario(S, "alumno@x.com", "STUDENT", school_id=cumbres, grade=10)
    client = TestClient(app)
    t = _login(client, "alumno@x.com")

    r = client.post(
        "/api/v1/me/counselor-sync",
        json={"nota": "hola", "school_id": str(otro), "student_id": "cualquiera"},
        headers=_h(t),
    )
    assert r.status_code == 201

    # Llegó a SU colegio, no al que pidió el cuerpo.
    from app.db.models import CounselorSyncReport
    db = S()
    try:
        fila = db.query(CounselorSyncReport).one()
        assert str(fila.school_id) == str(cumbres)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# (d) sin colegio · un no claro
# ---------------------------------------------------------------------------

def test_estudiante_sin_colegio_recibe_409_no_500(app_with_db):
    app, S = app_with_db
    _usuario(S, "b2c@x.com", "STUDENT", school_id=None, grade=10)
    client = TestClient(app)
    t = _login(client, "b2c@x.com")

    assert client.get("/api/v1/me/counselor-sync/preview", headers=_h(t)).json()["puede_enviar"] is False
    r = client.post("/api/v1/me/counselor-sync", json={}, headers=_h(t))
    assert r.status_code == 409, r.text


# ---------------------------------------------------------------------------
# (e) (f) (g) ⭐ el buzón y sus fronteras
# ---------------------------------------------------------------------------

def test_la_psicologa_ve_solo_lo_de_su_colegio(app_with_db):
    app, S = app_with_db
    cumbres = _colegio(S, "Cumbres")
    campestre = _colegio(S, "Campestre")

    _usuario(S, "a@x.com", "STUDENT", school_id=cumbres, grade=10)
    _usuario(S, "b@x.com", "STUDENT", school_id=campestre, grade=10)
    _usuario(S, "psy@x.com", "PSYCHOLOGIST", school_id=cumbres)

    client = TestClient(app)
    client.post("/api/v1/me/counselor-sync", json={}, headers=_h(_login(client, "a@x.com")))
    client.post("/api/v1/me/counselor-sync", json={}, headers=_h(_login(client, "b@x.com")))

    buzon = client.get("/api/v1/school/counselor-sync", headers=_h(_login(client, "psy@x.com")))
    assert buzon.status_code == 200
    assert len(buzon.json()) == 1


def test_un_estudiante_no_puede_leer_el_buzon(app_with_db):
    app, S = app_with_db
    colegio = _colegio(S, "Cumbres")
    _usuario(S, "alumno@x.com", "STUDENT", school_id=colegio, grade=10)
    client = TestClient(app)
    t = _login(client, "alumno@x.com")

    assert client.get("/api/v1/school/counselor-sync", headers=_h(t)).status_code == 403


def test_marcar_leido_uno_de_otro_colegio_da_404(app_with_db):
    # 404 y no 403: confirmar que existe pero es ajeno ya filtra informacion.
    app, S = app_with_db
    cumbres = _colegio(S, "Cumbres")
    campestre = _colegio(S, "Campestre")
    _usuario(S, "a@x.com", "STUDENT", school_id=cumbres, grade=10)
    _usuario(S, "psy@x.com", "PSYCHOLOGIST", school_id=campestre)

    client = TestClient(app)
    envio = client.post(
        "/api/v1/me/counselor-sync", json={}, headers=_h(_login(client, "a@x.com"))
    ).json()

    r = client.post(
        f"/api/v1/school/counselor-sync/{envio['id']}/leido",
        headers=_h(_login(client, "psy@x.com")),
    )
    assert r.status_code == 404
