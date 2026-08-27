# -*- coding: utf-8 -*-
"""El correo de bienvenida · que salga, y que no pueda tumbar el registro.

## Por qué existe

Hasta el 2026-08-27 alguien se registraba en una plataforma de orientación
—dando su correo, y siendo a veces menor de edad— y **no recibía nada**. Ni
acuse, ni de dónde venía el mensaje si más tarde le llegaba otro. Se detectó
probando el registro en producción: la cuenta se creaba y la bandeja quedaba
vacía.

## Lo que fijan estos tests

 1. Que registrarse dispare **un** envío, con destinatario y asunto reales.
 2. Que un fallo del proveedor **no** tumbe el registro. La cuenta ya existe: si
    el correo no sale, la persona igual tiene que poder entrar.
 3. Que `enviar_bienvenida` reporte lo que de verdad pasó. El servicio devuelve
    `delivered`, no `ok` — leer un campo que no existe con un `getattr(..., True)`
    de respaldo hacía que el backend de prueba, que nunca entrega nada, se
    reportara como éxito.

Se mockea **la frontera** (el backend de correo que habla con Resend), no
`enviar_bienvenida`, que es justo lo que se está probando.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def app_with_db(monkeypatch):
    """Misma receta que `test_rm1_consentimiento_en_registro.py`."""
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


class _BackendFalso:
    """La frontera. Registra la llamada en vez de salir a la red."""

    def __init__(self, entregado=True, revienta=False):
        self.entregado = entregado
        self.revienta = revienta
        self.enviados = []

    def send_html(self, *, to, subject, html, text=None):
        if self.revienta:
            raise RuntimeError("proveedor caido")
        self.enviados.append({"to": to, "subject": subject, "html": html, "text": text})
        from app.services.email_service import EmailSendResult

        return EmailSendResult(
            provider="falso",
            delivered=self.entregado,
            message_id="msg_1" if self.entregado else None,
            reason=None if self.entregado else "rechazado",
        )


def _registrar(client, email="bienvenida@test.com"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "testpass123",
            "name": "Ana Ruiz",
            "acepta_tratamiento_datos": True,
        },
    )


# ---------------------------------------------------------------------------
# 1 · sale
# ---------------------------------------------------------------------------


def test_registrarse_dispara_el_correo(app_with_db, monkeypatch):
    app, _ = app_with_db
    backend = _BackendFalso()

    from app.services import email_service

    monkeypatch.setattr(email_service, "get_backend", lambda: backend)

    r = _registrar(TestClient(app))
    assert r.status_code == 201, r.text

    assert len(backend.enviados) == 1, "un registro, un correo"
    enviado = backend.enviados[0]
    assert enviado["to"] == "bienvenida@test.com"
    assert enviado["subject"] == "Bienvenido a Mentoring"
    assert "Ana" in enviado["html"], "saluda por el primer nombre, no por el completo"
    assert enviado["text"], "sin texto plano el correo puntua peor en los filtros de spam"


def test_el_correo_habla_de_mento_y_no_promete_nada(app_with_db, monkeypatch):
    """El brandbook prohibe prometer cupos, becas o fechas · y un correo de
    bienvenida es justo donde mas tienta hacerlo."""
    app, _ = app_with_db
    backend = _BackendFalso()

    from app.services import email_service

    monkeypatch.setattr(email_service, "get_backend", lambda: backend)
    _registrar(TestClient(app))

    cuerpo = backend.enviados[0]["html"].lower()
    assert "mento" in cuerpo
    for prohibida in ("beca", "cupo", "garantiza", "admision asegurada"):
        assert prohibida not in cuerpo, "el correo promete: %s" % prohibida


# ---------------------------------------------------------------------------
# 2 · no puede tumbar el registro
# ---------------------------------------------------------------------------


def test_si_el_proveedor_revienta_la_cuenta_igual_se_crea(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db

    from app.services import email_service

    monkeypatch.setattr(email_service, "get_backend", lambda: _BackendFalso(revienta=True))

    r = _registrar(TestClient(app), "conproveedorcaido@test.com")
    assert r.status_code == 201, (
        "la cuenta ya existe cuando se manda el correo · un fallo del proveedor "
        "no puede dejar a la persona sin poder entrar"
    )
    assert r.json().get("access_token")

    from app.db.models import User

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == "conproveedorcaido@test.com").first()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 3 · reporta lo que de verdad paso
# ---------------------------------------------------------------------------


def test_un_rechazo_del_proveedor_no_se_reporta_como_exito(app_with_db, monkeypatch):
    """Prueba al reves: con `getattr(r, "ok", True)` esto devolvia True.

    El campo del servicio se llama `delivered`. Leer uno inexistente con un
    respaldo optimista convertia todo rechazo en un exito silencioso — incluido
    el backend de prueba, que NUNCA entrega nada.
    """
    app, SessionLocal = app_with_db

    from app.services import email_service, welcome_email

    monkeypatch.setattr(email_service, "get_backend", lambda: _BackendFalso(entregado=False))

    _registrar(TestClient(app), "rechazado@test.com")

    from app.db.models import User

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "rechazado@test.com").first()
        assert welcome_email.enviar_bienvenida(u) is False
    finally:
        db.close()


def test_una_entrega_real_si_se_reporta_como_exito(app_with_db, monkeypatch):
    """El otro lado del anterior · si no, `False` constante tambien pasaria."""
    app, SessionLocal = app_with_db

    from app.services import email_service, welcome_email

    monkeypatch.setattr(email_service, "get_backend", lambda: _BackendFalso(entregado=True))

    _registrar(TestClient(app), "entregado@test.com")

    from app.db.models import User

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "entregado@test.com").first()
        assert welcome_email.enviar_bienvenida(u) is True
    finally:
        db.close()
