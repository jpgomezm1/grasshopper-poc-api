"""Endpoint tests · GET /me/cv (F-001 · hardening 2026-06-05).

Cubren la lógica del endpoint que los tests unitarios no tocaban:
  - autorización student-only (403 para otros roles)
  - el path 503 NO filtra el detalle interno de GTK al cliente
  - el filename del Content-Disposition se sanea (header injection vía `name`)

El render real a PDF se monkeypatchea (no requiere WeasyPrint/GTK), así los
tests son deterministas en cualquier plataforma.
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


def _make_user(SessionLocal, email, *, role="student", name=None):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash("testpass123"),
            name=name or email.split("@")[0],
            role=UserRole(role),
            onboarding_status=OnboardingStatus.NOT_STARTED,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id, u.email
    finally:
        db.close()


def _login(client, email, password="testpass123"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_cv_requires_auth(app_with_db):
    app, _ = app_with_db
    client = TestClient(app)
    r = client.get("/api/v1/me/cv")
    assert r.status_code in (401, 403)


def test_cv_forbidden_for_non_student(app_with_db):
    """Un advisor (no estudiante) no puede descargar el endpoint student-only."""
    app, SessionLocal = app_with_db
    _, email = _make_user(SessionLocal, "advisor@x.com", role="gh_advisor")
    client = TestClient(app)
    token = _login(client, email)
    r = client.get("/api/v1/me/cv", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text


def test_cv_503_does_not_leak_internal_error(app_with_db, monkeypatch):
    """Cuando el render falla (GTK ausente), el cliente recibe un 503 genérico
    SIN las rutas internas de librerías del host."""
    app, SessionLocal = app_with_db
    _, email = _make_user(SessionLocal, "student503@x.com", role="student")
    client = TestClient(app)
    token = _login(client, email)

    from app.services import cv_pdf_service

    secret = "/usr/lib/x86_64-linux-gnu/libgobject-2.0.so.0 SECRET-PATH"

    def _boom(_cv):
        raise RuntimeError(f"GTK missing. Underlying error: {secret}")

    monkeypatch.setattr(cv_pdf_service, "render_cv_pdf", _boom)

    r = client.get("/api/v1/me/cv", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 503, r.text
    assert secret not in r.text
    assert "SECRET-PATH" not in r.text


def test_cv_filename_sanitized_against_header_injection(app_with_db, monkeypatch):
    """`name` editable por el usuario con comillas/CRLF no debe romper el header
    Content-Disposition (header injection)."""
    app, SessionLocal = app_with_db
    _, email = _make_user(
        SessionLocal,
        "evil@x.com",
        role="student",
        name='Juan" attachment; x="\r\nSet-Cookie: a=b',
    )
    client = TestClient(app)
    token = _login(client, email)

    from app.services import cv_pdf_service

    monkeypatch.setattr(cv_pdf_service, "render_cv_pdf", lambda _cv: b"%PDF-1.4 fake")

    r = client.get("/api/v1/me/cv", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    cd = r.headers["content-disposition"]
    # Lo que rompe el header (CRLF para inyectar otra cabecera · comillas para
    # salirse del filename) NO debe sobrevivir. Texto literal como "Set-Cookie"
    # dentro del filename es inofensivo (no hay CRLF que abra una cabecera).
    assert "\r" not in cd and "\n" not in cd
    # Exactamente un par de comillas (las del propio filename="..."), ninguna interna
    assert cd.count('"') == 2
    # El filename queda como un slug ASCII seguro derivado del nombre
    assert cd.startswith('attachment; filename="CV-Juan')
