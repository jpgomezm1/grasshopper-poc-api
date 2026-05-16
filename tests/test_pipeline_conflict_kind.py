"""Tests para conflict_kind en 409 responses de PATCH /leads/{id}/status · F7.2b.

Cubre:
  1. PATCH con version stale → 409 + conflict_kind='stale' + current_version populated
  2. PATCH con transición inválida → 409 + conflict_kind='invalid_transition'
  3. PATCH válido → 200 (no conflict_kind en el response)
  4. conflict_kind='stale' incluye current_status actual
  5. conflict_kind='invalid_transition' incluye current_status
  6. PATCH sin expected_version → 200 backward-compat (state machine sigue validando)
  7. PATCH con transición inválida sin expected_version → 409 + conflict_kind='invalid_transition'
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# UUID patch para SQLite
# ---------------------------------------------------------------------------
try:
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler as _STC

    if not hasattr(_STC, "visit_UUID"):
        def _visit_UUID(self, type_, **kw):  # noqa: N802
            return "VARCHAR(36)"
        _STC.visit_UUID = _visit_UUID  # type: ignore[attr-defined]
except Exception:
    pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_with_db(monkeypatch):
    """FastAPI + SQLite in-memory para tests HTTP del CRM pipeline."""
    sqlite_url = "sqlite:///:memory:"
    engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SL = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    from app.db import database as dbmod

    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", SL)

    def _override_get_db():
        db = SL()
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

    # Reset KPI cache
    try:
        from app.api.v1.crm import _KPI_CACHE
        _KPI_CACHE["data"] = None
        _KPI_CACHE["ts"] = 0
    except ImportError:
        pass

    yield app, SL

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_super_admin(SL, email="admin@test.com"):
    from app.api.v1.auth import get_password_hash
    from app.db.models import User, UserRole

    db = SL()
    u = User(
        email=email,
        hashed_password=get_password_hash("testpass123"),
        name="Super Admin",
        role=UserRole.SUPER_ADMIN,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return uid


def _make_lead(SL, email="lead@student.com", pipeline_status=None, version=1):
    from app.api.v1.auth import get_password_hash
    from app.db.models import User, UserRole

    db = SL()
    u = User(
        email=email,
        hashed_password=get_password_hash("testpass123"),
        name="Lead Student",
        role=UserRole.STUDENT,
        lead_pipeline_status=pipeline_status,
        pipeline_status_version=version,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return uid


def _login(client, email, password="testpass123"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _get_db_version(SL, user_id):
    from app.db.models import User

    db = SL()
    u = db.query(User).filter(User.id == user_id).first()
    v = u.pipeline_status_version if u else 0
    db.close()
    return v


def _get_db_status(SL, user_id):
    from app.db.models import User

    db = SL()
    u = db.query(User).filter(User.id == user_id).first()
    s = u.lead_pipeline_status if u else None
    db.close()
    return s


# ---------------------------------------------------------------------------
# Test 1: PATCH con version stale → 409 + conflict_kind='stale' + current_version
# ---------------------------------------------------------------------------


def test_stale_version_returns_conflict_kind_stale(app_with_db):
    """Version stale → 409 con conflict_kind='stale' y current_version en el body."""
    app, SL = app_with_db
    _make_super_admin(SL)
    # Lead en versión 3 en DB; el cliente envía expected_version=1 (stale)
    lead_id = _make_lead(SL, pipeline_status=None, version=3)

    client = TestClient(app)
    token = _login(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch(
        f"/api/v1/admin/crm/leads/{lead_id}/status",
        json={"status": "pending", "expected_version": 1},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["conflict_kind"] == "stale", (
        f"conflict_kind esperado 'stale', recibido: {body.get('conflict_kind')!r}"
    )
    assert "current_version" in body
    assert body["current_version"] == 3, (
        f"current_version debe ser 3 (la version actual en DB), recibido: {body['current_version']}"
    )
    assert "detail" in body
    # Estado no debe haber cambiado
    assert _get_db_status(SL, lead_id) is None
    assert _get_db_version(SL, lead_id) == 3


# ---------------------------------------------------------------------------
# Test 2: PATCH con transición inválida → 409 + conflict_kind='invalid_transition'
# ---------------------------------------------------------------------------


def test_invalid_transition_returns_conflict_kind(app_with_db):
    """Transición inválida → 409 con conflict_kind='invalid_transition'."""
    app, SL = app_with_db
    _make_super_admin(SL)
    # Lead en 'converted' (estado terminal → solo se puede ir a 'declined')
    lead_id = _make_lead(SL, pipeline_status="converted", version=2)

    client = TestClient(app)
    token = _login(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch(
        f"/api/v1/admin/crm/leads/{lead_id}/status",
        json={"status": "pending", "expected_version": 2},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["conflict_kind"] == "invalid_transition", (
        f"conflict_kind esperado 'invalid_transition', recibido: {body.get('conflict_kind')!r}"
    )
    assert "detail" in body
    # Estado no debe haber cambiado
    assert _get_db_status(SL, lead_id) == "converted"
    assert _get_db_version(SL, lead_id) == 2


# ---------------------------------------------------------------------------
# Test 3: PATCH válido → 200 sin conflict_kind
# ---------------------------------------------------------------------------


def test_valid_patch_returns_200_no_conflict_kind(app_with_db):
    """PATCH válido → 200 · el body de success NO contiene conflict_kind."""
    app, SL = app_with_db
    _make_super_admin(SL)
    lead_id = _make_lead(SL, pipeline_status=None, version=1)

    client = TestClient(app)
    token = _login(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch(
        f"/api/v1/admin/crm/leads/{lead_id}/status",
        json={"status": "pending", "expected_version": 1},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "conflict_kind" not in body, (
        "El body de 200 no debe contener conflict_kind"
    )
    assert body["pipeline_status"] == "pending"


# ---------------------------------------------------------------------------
# Test 4: conflict_kind='stale' incluye current_status actual
# ---------------------------------------------------------------------------


def test_stale_conflict_includes_current_status(app_with_db):
    """El 409 stale incluye current_status con el estado actual en DB."""
    app, SL = app_with_db
    _make_super_admin(SL)
    lead_id = _make_lead(SL, pipeline_status="contacted", version=5)

    client = TestClient(app)
    token = _login(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch(
        f"/api/v1/admin/crm/leads/{lead_id}/status",
        json={"status": "qualified", "expected_version": 1},  # stale: DB tiene v5
        headers=headers,
    )
    assert r.status_code == 409
    body = r.json()
    assert body["conflict_kind"] == "stale"
    assert body["current_status"] == "contacted", (
        f"current_status debe ser 'contacted', recibido: {body.get('current_status')!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: conflict_kind='invalid_transition' incluye current_status
# ---------------------------------------------------------------------------


def test_invalid_transition_includes_current_status(app_with_db):
    """El 409 invalid_transition incluye current_status."""
    app, SL = app_with_db
    _make_super_admin(SL)
    lead_id = _make_lead(SL, pipeline_status="qualified", version=1)

    client = TestClient(app)
    token = _login(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    # qualified → pending no está permitido
    r = client.patch(
        f"/api/v1/admin/crm/leads/{lead_id}/status",
        json={"status": "pending", "expected_version": 1},
        headers=headers,
    )
    assert r.status_code == 409
    body = r.json()
    assert body["conflict_kind"] == "invalid_transition"
    assert body["current_status"] == "qualified"


# ---------------------------------------------------------------------------
# Test 6: PATCH sin expected_version → 200 backward-compat
# ---------------------------------------------------------------------------


def test_no_version_backward_compat_returns_200(app_with_db):
    """Cliente legacy sin expected_version → 200 (transición válida)."""
    app, SL = app_with_db
    _make_super_admin(SL)
    lead_id = _make_lead(SL, pipeline_status=None, version=1)

    client = TestClient(app)
    token = _login(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch(
        f"/api/v1/admin/crm/leads/{lead_id}/status",
        json={"status": "pending"},  # sin expected_version
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pipeline_status"] == "pending"


# ---------------------------------------------------------------------------
# Test 7: Transición inválida sin expected_version → 409 + conflict_kind
# ---------------------------------------------------------------------------


def test_invalid_transition_without_version_still_returns_conflict_kind(app_with_db):
    """State machine se valida incluso sin expected_version. El 409 incluye conflict_kind."""
    app, SL = app_with_db
    _make_super_admin(SL)
    # converted → pending: inválido sin importar si se envía version o no
    lead_id = _make_lead(SL, pipeline_status="converted", version=1)

    client = TestClient(app)
    token = _login(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch(
        f"/api/v1/admin/crm/leads/{lead_id}/status",
        json={"status": "pending"},  # sin expected_version
        headers=headers,
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["conflict_kind"] == "invalid_transition"
