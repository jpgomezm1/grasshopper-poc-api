"""A9 · Ciudad y área de estudio, sobre HTTP real · cierre R6.

Lo que de verdad hay que probar aquí NO es que un PUT guarde un string. Es que
el dato **llegue a los tres sitios que llevaban meses leyéndolo sin recibirlo
nunca**: el dossier del asesor y los dos puntos del CRM. Ese era el defecto.

Por eso el test más importante de este archivo es
`test_la_ciudad_llega_al_dossier_del_asesor`, que no mira la respuesta del
endpoint sino lo que construye `dossier_service` — el camino incómodo.

Se corre contra SQLite en memoria: el `.env` local del backend apunta al mismo
Neon que usa producción, así que un e2e "de verdad" escribiría datos reales.
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


def _headers(client, email):
    r = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


BASE = "/api/v1/me/study-preferences"


# ---------------------------------------------------------------------------
# Lo básico · guardar y recuperar
# ---------------------------------------------------------------------------


def test_sin_responder_viene_vacio_y_no_revienta(app_with_db):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a9.vacio@grasshopper.dev")
    with TestClient(app) as client:
        h = _headers(client, "a9.vacio@grasshopper.dev")
        r = client.get(BASE, headers=h)
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert cuerpo["city"] is None
        assert cuerpo["preferred_cities"] == []
        assert cuerpo["study_area"] is None
        assert cuerpo["answered"] is False


def test_guardar_y_recuperar(app_with_db):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a9.uno@grasshopper.dev")
    with TestClient(app) as client:
        h = _headers(client, "a9.uno@grasshopper.dev")
        r = client.put(
            BASE,
            headers=h,
            json={
                "city": "Medellín",
                "preferred_cities": ["Toronto", "Melbourne"],
                "study_area": "health",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["answered"] is True

        # Sobrevive a un GET posterior · no se quedó sólo en la respuesta
        r2 = client.get(BASE, headers=h)
        cuerpo = r2.json()
        assert cuerpo["city"] == "Medellín"
        assert cuerpo["preferred_cities"] == ["Toronto", "Melbourne"]
        assert cuerpo["study_area"] == "health"


def test_se_puede_responder_a_medias_y_volver_despues(app_with_db):
    """Ella criticó la fatiga de cuestionarios: nada aquí es obligatorio."""
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a9.parcial@grasshopper.dev")
    with TestClient(app) as client:
        h = _headers(client, "a9.parcial@grasshopper.dev")

        client.put(BASE, headers=h, json={"study_area": "engineering"})
        client.put(BASE, headers=h, json={"city": "Bogotá"})

        cuerpo = client.get(BASE, headers=h).json()
        # El segundo PUT no borró lo del primero
        assert cuerpo["study_area"] == "engineering"
        assert cuerpo["city"] == "Bogotá"


def test_no_pisa_lo_que_ya_habia_respondido_en_el_onboarding(app_with_db):
    """El PUT escribe en el MISMO JSON del onboarding · no puede arrasarlo."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a9.merge@grasshopper.dev")

    from app.db.models import User
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == uid).first()
        u.onboarding_answers = {"lifeStage": "school", "countries": ["canada"]}
        db.commit()
    finally:
        db.close()

    with TestClient(app) as client:
        h = _headers(client, "a9.merge@grasshopper.dev")
        client.put(BASE, headers=h, json={"city": "Cali"})

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == uid).first()
        assert u.onboarding_answers["city"] == "Cali"
        assert u.onboarding_answers["lifeStage"] == "school"      # sigue ahí
        assert u.onboarding_answers["countries"] == ["canada"]    # sigue ahí
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Validación · este dato viaja al CRM, no puede entrar basura
# ---------------------------------------------------------------------------


def test_area_desconocida_se_rechaza(app_with_db):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a9.mala@grasshopper.dev")
    with TestClient(app) as client:
        h = _headers(client, "a9.mala@grasshopper.dev")
        r = client.put(BASE, headers=h, json={"study_area": "brujeria_aplicada"})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "unknown_study_area"


def test_no_se_todavia_es_una_respuesta_valida(app_with_db):
    """En orientación vocacional "no sé" es la respuesta honesta más común."""
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a9.nose@grasshopper.dev")
    with TestClient(app) as client:
        h = _headers(client, "a9.nose@grasshopper.dev")
        r = client.put(BASE, headers=h, json={"study_area": "undecided"})
        assert r.status_code == 200, r.text
        assert r.json()["study_area"] == "undecided"


def test_ciudades_se_limpian_deduplican_y_se_cortan_a_tres(app_with_db):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a9.sucias@grasshopper.dev")
    with TestClient(app) as client:
        h = _headers(client, "a9.sucias@grasshopper.dev")
        r = client.put(
            BASE,
            headers=h,
            json={
                "preferred_cities": [
                    "  Toronto  ", "", "toronto", "Berlín", "Lisboa", "Madrid",
                ]
            },
        )
        assert r.status_code == 200, r.text
        # Sin vacíos, sin el duplicado que sólo cambia en mayúsculas, máximo 3
        assert r.json()["preferred_cities"] == ["Toronto", "Berlín", "Lisboa"]


def test_mandar_vacio_borra_la_respuesta(app_with_db):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a9.borrar@grasshopper.dev")
    with TestClient(app) as client:
        h = _headers(client, "a9.borrar@grasshopper.dev")
        client.put(BASE, headers=h, json={"city": "Pereira"})
        client.put(BASE, headers=h, json={"city": ""})
        assert client.get(BASE, headers=h).json()["city"] is None


# ---------------------------------------------------------------------------
# Privacidad
# ---------------------------------------------------------------------------


def test_sin_sesion_no_se_puede_leer_ni_escribir(app_with_db):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a9.priv@grasshopper.dev")
    with TestClient(app) as client:
        assert client.get(BASE).status_code in (401, 403)
        assert client.put(BASE, json={"city": "Quito"}).status_code in (401, 403)


def test_cada_quien_ve_solo_lo_suyo(app_with_db):
    app, SessionLocal = app_with_db
    _student(SessionLocal, "a9.ana@grasshopper.dev")
    _student(SessionLocal, "a9.beto@grasshopper.dev")
    with TestClient(app) as client:
        ha = _headers(client, "a9.ana@grasshopper.dev")
        client.put(BASE, headers=ha, json={"city": "Manizales"})

        hb = _headers(client, "a9.beto@grasshopper.dev")
        assert client.get(BASE, headers=hb).json()["city"] is None


# ---------------------------------------------------------------------------
# EL CAMINO INCÓMODO · que el dato llegue a quien lo estaba esperando
# ---------------------------------------------------------------------------


def test_la_ciudad_llega_al_dossier_del_asesor(app_with_db):
    """`dossier_service.py:100` leía `answers["city"]` y SIEMPRE recibía vacío.

    Este es el test que importa: no comprueba el endpoint, comprueba el sitio
    donde el defecto se veía — un campo "Ciudad" en blanco en la pantalla del
    asesor.
    """
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a9.dossier@grasshopper.dev")

    with TestClient(app) as client:
        h = _headers(client, "a9.dossier@grasshopper.dev")
        client.put(BASE, headers=h, json={"city": "Barranquilla"})

    from app.services import dossier_service
    from app.db.models import User

    db = SessionLocal()
    try:
        student = db.query(User).filter(User.id == uid).first()
        demo = dossier_service._build_demographics(db, student, None)
        assert demo.city == "Barranquilla"
    finally:
        db.close()


def test_la_ciudad_llega_al_crm(app_with_db):
    """`crm_service.py:725` construye el bloque Demographics del lead."""
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a9.crm@grasshopper.dev")

    with TestClient(app) as client:
        h = _headers(client, "a9.crm@grasshopper.dev")
        client.put(BASE, headers=h, json={"city": "Bucaramanga"})

    from app.services import crm_service
    from app.db.models import User

    db = SessionLocal()
    try:
        student = db.query(User).filter(User.id == uid).first()
        demo = crm_service._build_demographics(student)
        assert demo.city == "Bucaramanga"
    finally:
        db.close()


def test_la_ciudad_de_destino_no_contamina_la_de_residencia(app_with_db):
    """El error que se evitó: "Toronto" en el dossier de quien vive en Medellín.

    Si alguien "simplifica" esto a un solo campo, este test falla — y debe
    fallar: un asesor leyendo la ciudad equivocada decide mal.
    """
    app, SessionLocal = app_with_db
    uid = _student(SessionLocal, "a9.nocontamina@grasshopper.dev")

    with TestClient(app) as client:
        h = _headers(client, "a9.nocontamina@grasshopper.dev")
        client.put(
            BASE,
            headers=h,
            json={"city": "Medellín", "preferred_cities": ["Toronto", "Madrid"]},
        )

    from app.services import dossier_service
    from app.db.models import User

    db = SessionLocal()
    try:
        student = db.query(User).filter(User.id == uid).first()
        demo = dossier_service._build_demographics(db, student, None)
        assert demo.city == "Medellín"
        assert "Toronto" not in (demo.city or "")
    finally:
        db.close()
