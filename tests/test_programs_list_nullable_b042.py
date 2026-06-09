"""B-042 · GET /programs con catálogo real (financieros NULL) no debe dar 500.

El catálogo importado de los convenios (migración 048) deja `duration_months`,
`cost_total` y `budget_tier` en NULL = "a confirmar". `ProgramResponse`
heredaba esos campos como requeridos de `ProgramBase` → cada página de
`GET /programs` lanzaba ValidationError → 500 y el catálogo del admin quedó
caído en prod para todos los roles (feedback humano ronda 1, 2026-06-09).

Usa SQLite + TestClient (sin Postgres).
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


def _user(SessionLocal, email, role):
    from app.db.models import User, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash("testpass123"),
            name="U",
            role=role,
            onboarding_status=OnboardingStatus.NOT_STARTED,
        )
        db.add(u)
        db.commit()
        return u.email
    finally:
        db.close()


def _login(client, email, password="testpass123"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _seed_catalog_real(SessionLocal):
    """Inserta programas con el shape EXACTO del importador del catálogo real:
    duration_months / cost_total / budget_tier en NULL."""
    from app.db.models import Program

    db = SessionLocal()
    try:
        for i in range(3):
            db.add(
                Program(
                    program_id=f"real-inst-{i}",
                    name=f"Institución Real {i}",
                    slug=f"real-inst-{i}",
                    country="Canada",
                    city="Toronto",
                    institution=f"Institución Real {i}",
                    type="curso_corto",
                    duration_months=None,
                    cost_total=None,
                    currency="USD",
                    budget_tier=None,
                    alliance_type="estandar",
                    active=True,
                )
            )
        # uno del seed viejo con valores completos (mezcla realista)
        db.add(
            Program(
                program_id="seed-completo",
                name="Programa Seed",
                slug="seed-completo",
                country="Spain",
                institution="Inst Seed",
                type="pregrado",
                duration_months=48,
                cost_total=9000,
                currency="USD",
                budget_tier="medium",
                alliance_type="estandar",
                active=True,
            )
        )
        db.commit()
    finally:
        db.close()


def test_list_programs_with_null_financials_returns_200_super_admin(app_with_db):
    from app.db.models import UserRole

    app, SessionLocal = app_with_db
    _seed_catalog_real(SessionLocal)
    email = _user(SessionLocal, "sa@x.com", UserRole.SUPER_ADMIN)
    client = TestClient(app)
    token = _login(client, email)

    r = client.get(
        "/api/v1/programs?page=1&page_size=25&active=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 4
    nulls = [it for it in body["items"] if it["cost_total"] is None]
    assert len(nulls) == 3
    assert all(it["duration_months"] is None and it["budget_tier"] is None for it in nulls)


def test_list_programs_with_null_financials_returns_200_psychologist(app_with_db):
    """El tester vio el catálogo caído como psy/comercial/super admin."""
    from app.db.models import UserRole

    app, SessionLocal = app_with_db
    _seed_catalog_real(SessionLocal)
    email = _user(SessionLocal, "psy@x.com", UserRole.PSYCHOLOGIST)
    client = TestClient(app)
    token = _login(client, email)

    r = client.get(
        "/api/v1/programs?page=1&page_size=25",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 4  # no-super_admin ve solo activos (todos lo son)


def test_program_detail_with_null_financials_returns_200(app_with_db):
    from app.db.models import UserRole

    app, SessionLocal = app_with_db
    _seed_catalog_real(SessionLocal)
    email = _user(SessionLocal, "sa2@x.com", UserRole.SUPER_ADMIN)
    client = TestClient(app)
    token = _login(client, email)

    r = client.get(
        "/api/v1/programs?page=1&page_size=1&search=real-inst-0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    pid = r.json()["items"][0]["id"]

    r2 = client.get(
        f"/api/v1/programs/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["cost_total"] is None
