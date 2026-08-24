"""RM-1 · La cadena completa, por HTTP real.

Los tests de `test_rm1_acompanamiento.py` prueban las piezas llamando a los
servicios directo. Este recorre lo mismo **por los endpoints**, que es el camino
que va a ejecutar Heroku Scheduler:

    POST /v1/me/consents  →  POST /v1/outreach/run  →  fila en outreach_logs

Existe porque el repo ya se quemó con eso: el 05-08 once tests en verde
convivían con una funcionalidad rota al 100%, porque ninguno tocaba el camino
real. Un servicio que funciona y un router que no lo llama bien se ven idénticos
desde los tests unitarios.

Cubre además el caso que sólo aparece cruzando capas: que el consentimiento
otorgado por la API sea el que el motor de envío lee después.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SECRETO = "secreto-de-prueba-rm1"


@pytest.fixture()
def entorno(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Maker = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.db import database as dbmod

    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Maker)

    def _get_db():
        db = Maker()
        try:
            yield db
        finally:
            db.close()

    from app.db.models import Base

    Base.metadata.create_all(bind=engine)

    from app.main import app
    from app.core.rate_limiter import limiter

    app.dependency_overrides[dbmod.get_db] = _get_db
    limiter.reset()

    # Frontera del modelo mockeada · no se llama a Claude en un test.
    from app.services import outreach_writer

    monkeypatch.setattr(
        outreach_writer,
        "call_claude_tool",
        lambda *a, **k: (
            {"cuerpo": "Vi que dejaste tu proceso a medias y quería recordártelo.",
             "cta": "Continuar"},
            {},
        ),
    )

    # Frontera del correo · se captura en vez de enviarse.
    enviados = []
    from app.services import email_service

    class _Ok:
        provider = "stub"
        delivered = True
        reason = None

    monkeypatch.setattr(
        email_service, "send_email", lambda **k: enviados.append(k) or _Ok()
    )

    from app.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    monkeypatch.setattr(s, "outreach_cron_secret", SECRETO, raising=False)
    monkeypatch.setattr(s, "outreach_enabled", True, raising=False)

    from app.services import recommendation_service as rs

    monkeypatch.setattr(rs, "user_has_tests", lambda db, user: False)

    with TestClient(app) as client:
        yield client, Maker, enviados

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _estudiante(client, Maker, email="e2e@test.com", acepta_comunicaciones=False):
    """Registra por la API y lo envejece para que califique como estancado.

    Se registra **desmarcando la casilla** por defecto: desde el 2026-08-18 el
    registro otorga el permiso de comunicaciones si viene marcada, así que un
    alta normal ya sale con permiso. Este helper representa a la persona que
    todavía NO lo dio, que es el punto de partida de la cadena que se prueba
    abajo. El camino contrario tiene su propio test.
    """
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Test2026!",
            "name": "Ana Ruiz",
            "acepta_comunicaciones": acepta_comunicaciones,
        },
    )
    assert r.status_code in (200, 201), r.text
    token = r.json()["access_token"]

    from app.db.models import User

    db = Maker()
    u = db.query(User).filter(User.email == email).first()
    u.created_at = datetime.utcnow() - timedelta(days=40)
    u.birthdate = datetime(2000, 1, 1).date()
    u.consent_data_processing_at = datetime.utcnow() - timedelta(days=40)
    db.commit()
    uid = u.id
    db.close()
    return {"Authorization": f"Bearer {token}"}, uid


def _correr(client):
    return client.post(
        "/api/v1/outreach/run", headers={"X-Outreach-Secret": SECRETO}
    )


def test_la_cadena_completa_por_http(entorno):
    """De otorgar el permiso a que salga el correo, sin saltarse ninguna capa."""
    client, Maker, enviados = entorno
    H, uid = _estudiante(client, Maker)

    # 1 · Sin permiso, la corrida no manda nada.
    r = _correr(client)
    assert r.status_code == 200, r.text
    assert r.json()["enviados"] == 0
    assert r.json()["sin_consentimiento"] == 1
    assert enviados == []

    # 2 · La persona lo otorga desde la pantalla de preferencias.
    r = client.post("/api/v1/me/consents", headers=H, json={"communications": True})
    assert r.status_code == 200, r.text
    assert r.json()["communications"]["granted"] is True

    # 3 · Ahora sí sale · y es EL correo de esa persona.
    r = _correr(client)
    assert r.status_code == 200, r.text
    assert r.json()["enviados"] == 1
    assert len(enviados) == 1
    assert enviados[0]["to"] == "e2e@test.com"

    # 4 · Queda registrado como enviado.
    from app.db.models import OutreachLog

    db = Maker()
    fila = (
        db.query(OutreachLog)
        .filter(OutreachLog.user_id == uid, OutreachLog.resultado == "enviado")
        .one()
    )
    assert fila.motivo == "sin_tests"
    db.close()


def test_quien_acepto_al_registrarse_recibe_sin_pasar_por_preferencias(entorno):
    """El camino nuevo · la razón por la que se movió el permiso al registro.

    Medido en producción el 2026-08-18: la primera corrida real revisó 36
    personas y no le escribió a ninguna, porque el permiso sólo se podía dar en
    una pantalla a tres clics de profundidad. Este test fija que, aceptando en
    el registro, la cadena completa funciona **sin visitar Preferencias**.
    """
    client, Maker, enviados = entorno
    _estudiante(client, Maker, email="acepto@test.com", acepta_comunicaciones=True)

    r = _correr(client)

    assert r.status_code == 200, r.text
    assert r.json()["enviados"] == 1
    assert r.json()["sin_consentimiento"] == 0
    assert [e["to"] for e in enviados] == ["acepto@test.com"]


def test_correr_dos_veces_no_manda_dos_veces(entorno):
    """Idempotencia · Heroku Scheduler puede disparar de más, o alguien puede
    llamar el endpoint a mano."""
    client, Maker, enviados = entorno
    H, _ = _estudiante(client, Maker)
    client.post("/api/v1/me/consents", headers=H, json={"communications": True})

    assert _correr(client).json()["enviados"] == 1
    assert _correr(client).json()["enviados"] == 0
    assert len(enviados) == 1


def test_revocar_el_permiso_corta_el_envio(entorno):
    """Derecho del titular (Ley 1581 art. 8.e) · y tiene que surtir efecto ya,
    no en la próxima quincena."""
    client, Maker, enviados = entorno
    H, uid = _estudiante(client, Maker)
    client.post("/api/v1/me/consents", headers=H, json={"communications": True})
    assert _correr(client).json()["enviados"] == 1

    r = client.post("/api/v1/me/consents", headers=H, json={"communications": False})
    assert r.json()["communications"]["granted"] is False

    # Se limpia el tope de frecuencia para aislar el efecto de la revocación.
    from app.db.models import OutreachLog

    db = Maker()
    db.query(OutreachLog).delete()
    db.commit()
    db.close()

    assert _correr(client).json()["enviados"] == 0
    assert len(enviados) == 1


def test_el_endpoint_exige_el_secreto(entorno):
    client, _, enviados = entorno

    assert client.post("/api/v1/outreach/run").status_code == 401
    assert client.post(
        "/api/v1/outreach/run", headers={"X-Outreach-Secret": "malo"}
    ).status_code == 401
    assert enviados == []


def test_el_preview_no_manda_nada(entorno):
    """Es lo que se le muestra a la clienta antes de prender el interruptor:
    si mandara algo, el paso previo a autorizar sería el envío."""
    client, Maker, enviados = entorno
    H, uid = _estudiante(client, Maker)
    client.post("/api/v1/me/consents", headers=H, json={"communications": True})

    # El preview es sólo para super_admin.
    assert client.get("/api/v1/outreach/preview", headers=H).status_code == 403

    from app.db.models import User, UserRole

    db = Maker()
    db.query(User).filter(User.id == uid).update({"role": UserRole.SUPER_ADMIN})
    db.commit()
    db.close()

    r = client.get("/api/v1/outreach/preview", headers=H)
    assert r.status_code == 200, r.text
    assert enviados == [], "el preview mandó correo"


def test_un_menor_sin_permiso_parental_no_recibe_nada_por_http(entorno):
    """La protección más importante, verificada por el camino real."""
    client, Maker, enviados = entorno
    H, uid = _estudiante(client, Maker, email="menor@test.com")

    from app.db.models import User

    db = Maker()
    db.query(User).filter(User.id == uid).update(
        {"birthdate": (datetime.utcnow() - timedelta(days=365 * 14)).date()}
    )
    db.commit()
    db.close()

    client.post("/api/v1/me/consents", headers=H, json={"communications": True})

    r = _correr(client)
    assert r.json()["enviados"] == 0
    assert r.json()["sin_consentimiento"] == 1
    assert enviados == []
