"""RM-1 · el consentimiento se toma al crear la cuenta.

## Por qué existe este archivo

El 2026-08-18 se encendió el acompañamiento periódico en producción y la primera
corrida real devolvió: **36 candidatos, 36 sin consentimiento, 0 enviados**.

La causa no era el permiso de comunicaciones. Era que el registro **no tomaba
ningún consentimiento**: `can_send_communications()` fallaba en su PRIMER
candado (`no_data_processing_consent`) para el 100% de la base, y la única
pantalla capaz de otorgar algo —Preferencias— sólo manda `communications` y está
a tres clics de profundidad (sidebar → usuario → Configuración → Preferencias).

Lo que fijan estos tests, en orden de importancia:

 1. **Que desmarcar la casilla NO registre el permiso.** Es la diferencia entre
    una casilla marcada por defecto (legítima: la persona la ve y puede
    desmarcarla) y un permiso tomado en silencio (que no es consentimiento).
 2. Que crear la cuenta sí registre el tratamiento de datos, que es lo que
    destrabó el caso real.
 3. Que quede **fila de auditoría** por cada consentimiento: sin eso no se puede
    responder "¿quién autorizó esto y cuándo?".
 4. Que esto **no le abra la puerta a un menor**: el candado parental es
    independiente y sigue mandando.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def app_with_db(monkeypatch):
    """Misma receta que `test_consent_gate.py` · SQLite en memoria, sin red."""
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


def _registrar(client, email, **extra):
    payload = {"email": email, "password": "testpass123", "name": "Test"}
    payload.update(extra)
    return client.post("/api/v1/auth/register", json=payload)


def _usuario(SessionLocal, email):
    from app.db.models import User

    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).first()
    finally:
        db.close()


def _eventos(SessionLocal, user_id):
    from app.db.models import ConsentAuditLog

    db = SessionLocal()
    try:
        filas = (
            db.query(ConsentAuditLog)
            .filter(ConsentAuditLog.user_id == user_id)
            .all()
        )
        return sorted(f.event for f in filas)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1 · el caso que destraba el bug real
# ---------------------------------------------------------------------------


def test_registro_por_defecto_otorga_los_dos_consentimientos(app_with_db):
    app, SessionLocal = app_with_db
    client = TestClient(app)

    r = _registrar(client, "default@test.com")
    assert r.status_code == 201, r.text

    u = _usuario(SessionLocal, "default@test.com")
    assert u.consent_data_processing_at is not None, (
        "sin esto `can_send_communications` falla en su primer candado y el "
        "acompanamiento periodico nunca le escribe a nadie"
    )
    assert u.consent_communications_at is not None
    assert u.consent_data_processing_version, "la version de la politica se sella"


def test_el_registro_deja_rastro_de_auditoria(app_with_db):
    app, SessionLocal = app_with_db
    client = TestClient(app)

    _registrar(client, "auditoria@test.com")
    u = _usuario(SessionLocal, "auditoria@test.com")

    assert _eventos(SessionLocal, u.id) == [
        "communications.granted",
        "data_processing.granted",
    ]


# ---------------------------------------------------------------------------
# 2 · lo que separa una casilla marcada de un permiso tomado en silencio
# ---------------------------------------------------------------------------


def test_desmarcar_la_casilla_no_registra_el_permiso(app_with_db):
    app, SessionLocal = app_with_db
    client = TestClient(app)

    r = _registrar(client, "sinpermiso@test.com", acepta_comunicaciones=False)
    assert r.status_code == 201, r.text

    u = _usuario(SessionLocal, "sinpermiso@test.com")
    assert u.consent_communications_at is None, (
        "si la persona desmarca la casilla no se registra el permiso · lo "
        "contrario convertiria un default en un consentimiento fabricado"
    )
    # El tratamiento de datos sí, que es lo que permite tener la cuenta.
    assert u.consent_data_processing_at is not None
    assert _eventos(SessionLocal, u.id) == ["data_processing.granted"]


def test_quien_desmarca_no_recibe_mensajes(app_with_db):
    """El puente entre el registro y el motor de RM-1."""
    app, SessionLocal = app_with_db
    client = TestClient(app)

    _registrar(client, "nomeescribas@test.com", acepta_comunicaciones=False)
    u = _usuario(SessionLocal, "nomeescribas@test.com")

    from app.services.consent_service import can_send_communications

    puede, motivo = can_send_communications(u)
    assert puede is False
    assert motivo == "no_communications_consent"


# ---------------------------------------------------------------------------
# 3 · esto no puede convertirse en una puerta trasera para menores
# ---------------------------------------------------------------------------


def test_un_menor_recien_registrado_sigue_bloqueado(app_with_db):
    """Aceptar la casilla no reemplaza el consentimiento de los papás.

    Ojo con el detalle: al registrarse nadie da su fecha de nacimiento, y
    `is_minor` devuelve True cuando no la hay. O sea que **todo recién
    registrado se trata como menor** hasta que se sepa su edad · y eso es lo
    correcto: ante la duda, no se manda nada.
    """
    app, SessionLocal = app_with_db
    client = TestClient(app)

    _registrar(client, "menor@test.com")  # casilla marcada por defecto
    u = _usuario(SessionLocal, "menor@test.com")

    from app.services.consent_service import can_send_communications

    puede, motivo = can_send_communications(u)
    assert puede is False
    assert motivo == "no_parental_consent"


def test_con_edad_de_adulto_y_casilla_marcada_si_puede_recibir(app_with_db):
    """El caso que hace que el acompañamiento sirva de algo."""
    from datetime import date, timedelta

    app, SessionLocal = app_with_db
    client = TestClient(app)

    _registrar(client, "adulto@test.com")

    from app.db.models import User

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "adulto@test.com").first()
        u.birthdate = date.today() - timedelta(days=365 * 30)
        db.commit()
        db.refresh(u)

        from app.services.consent_service import can_send_communications

        puede, motivo = can_send_communications(u)
        assert puede is True
        assert motivo is None
    finally:
        db.close()
