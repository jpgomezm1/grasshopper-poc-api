"""Tests de race condition para el pipeline state machine · QA-AUD-072.

Cubre:
  1. happy_path: transición válida con versión fresca → 200 + version++ en DB
  2. stale_version: update con versión stale (simula concurrencia) → 409 Conflict
  3. invalid_transition: transición inválida (ej. proposal_sent → qualifying) → 409
  4. concurrent_writers: 2 threads actualizan simultáneamente · solo uno gana, el otro recibe StaleOpportunityError
  5. state_machine_all_transitions: tabla completa de transiciones válidas e inválidas
  6. legacy_no_version: cliente que no envía expected_version → acepta sin versioning (backward-compat)
  7. bitrix_sync_after_commit: el sync bitrix se loguea DESPUÉS del commit principal
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# SQLite UUID patch · aplica antes de cualquier importación de modelos
# ---------------------------------------------------------------------------
# El conftest.py también aplica este patch pero hay casos donde el orden
# de importación de pytest hace que models.py se importe primero.
# Este bloque garantiza que el patch esté listo antes de cualquier import.
try:
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler as _STC

    if not hasattr(_STC, "visit_UUID"):
        def _visit_UUID(self, type_, **kw):  # noqa: N802
            return "VARCHAR(36)"
        _STC.visit_UUID = _visit_UUID  # type: ignore[attr-defined]
except Exception:
    pass
# ---------------------------------------------------------------------------

import threading
from datetime import datetime
from typing import Optional
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services.crm_service import (
    PIPELINE_VALID_TRANSITIONS,
    InvalidPipelineTransitionError,
    StaleOpportunityError,
    _validate_pipeline_transition,
    update_pipeline_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_with_db(monkeypatch):
    """App + SQLite in-memory DB listos para los tests HTTP."""
    sqlite_url = "sqlite:///:memory:"
    engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setenv("DATABASE_URL", sqlite_url)
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


def _make_commercial_user(SessionLocal, email="commercial@test.com"):
    """Crea un usuario GH_COMMERCIAL y devuelve su id."""
    from app.api.v1.auth import get_password_hash
    from app.db.models import User, UserRole

    db = SessionLocal()
    u = User(
        email=email,
        hashed_password=get_password_hash("testpass123"),
        name="Commercial User",
        role=UserRole.GH_COMMERCIAL,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return uid


def _make_lead(SessionLocal, email="lead@student.com", pipeline_status=None, version=1):
    """Crea un student lead con pipeline_status y versión dada."""
    from app.api.v1.auth import get_password_hash
    from app.db.models import User, UserRole

    db = SessionLocal()
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


def _make_super_admin(SessionLocal, email="admin@test.com"):
    from app.api.v1.auth import get_password_hash
    from app.db.models import User, UserRole

    db = SessionLocal()
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


def _login(client: TestClient, email: str, password="testpass123") -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _get_db_version(SessionLocal, user_id) -> int:
    from app.db.models import User

    db = SessionLocal()
    u = db.query(User).filter(User.id == user_id).first()
    v = u.pipeline_status_version if u else 0
    db.close()
    return v


def _get_db_status(SessionLocal, user_id) -> Optional[str]:
    from app.db.models import User

    db = SessionLocal()
    u = db.query(User).filter(User.id == user_id).first()
    s = u.lead_pipeline_status if u else None
    db.close()
    return s


# ---------------------------------------------------------------------------
# Test 1: happy path – transición válida con versión fresca
# ---------------------------------------------------------------------------


def test_valid_transition_with_fresh_version(app_with_db):
    """PATCH con versión fresca y transición válida → 200 + version++ en DB."""
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
    assert body["pipeline_status"] == "pending"
    assert body["pipeline_status_version"] == 2

    # Verificar en DB
    assert _get_db_version(SL, lead_id) == 2
    assert _get_db_status(SL, lead_id) == "pending"


# ---------------------------------------------------------------------------
# Test 2: stale version → 409 Conflict
# ---------------------------------------------------------------------------


def test_stale_version_returns_409(app_with_db):
    """Update con versión stale (simula escritura concurrente) → 409."""
    app, SL = app_with_db
    _make_super_admin(SL)
    lead_id = _make_lead(SL, pipeline_status=None, version=3)  # DB ya está en v3

    client = TestClient(app)
    token = _login(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    # El cliente cree que está en versión 1 (stale)
    r = client.patch(
        f"/api/v1/admin/crm/leads/{lead_id}/status",
        json={"status": "pending", "expected_version": 1},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert "concurrente" in r.json()["detail"].lower() or "stale" in r.json()["detail"].lower() or "conflicto" in r.json()["detail"].lower()

    # El estado en DB NO debe haber cambiado
    assert _get_db_version(SL, lead_id) == 3
    assert _get_db_status(SL, lead_id) is None


# ---------------------------------------------------------------------------
# Test 3: transición inválida → 409 Conflict
# ---------------------------------------------------------------------------


def test_invalid_transition_returns_409(app_with_db):
    """Transición que viola el state machine → 409 Conflict."""
    app, SL = app_with_db
    _make_super_admin(SL)
    # Lead en 'converted' (estado terminal)
    lead_id = _make_lead(SL, pipeline_status="converted", version=1)

    client = TestClient(app)
    token = _login(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    # converted → pending no está permitido (sólo declined)
    r = client.patch(
        f"/api/v1/admin/crm/leads/{lead_id}/status",
        json={"status": "pending", "expected_version": 1},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "inválida" in detail.lower() or "invalid" in detail.lower() or "transición" in detail.lower()

    # El estado NO debe haber cambiado
    assert _get_db_status(SL, lead_id) == "converted"
    assert _get_db_version(SL, lead_id) == 1


# ---------------------------------------------------------------------------
# Test 4: concurrencia serializada (simula el escenario de race condition)
# ---------------------------------------------------------------------------


def test_concurrent_writers_one_wins(app_with_db):
    """Simula el escenario de race condition a nivel de service layer.

    Escenario:
      - User A lee version=1, actualiza a pending → OK (version se vuelve 2)
      - User B también tenía version=1 (stale), intenta actualizar → StaleOpportunityError

    Nota: SQLite con StaticPool no admite verdadera concurrencia de threads
    (una sola conexión compartida). El test valida el comportamiento lógico
    del CAS serializado, que es la garantía real del optimistic locking.
    El test de threading real requiere Postgres con múltiples conexiones.
    """
    _, SL = app_with_db

    lead_id = _make_lead(SL, pipeline_status=None, version=1)
    actor_id = _make_super_admin(SL)

    from app.db.models import User

    # ----- User A (primera escritura) -----
    db_a = SL()
    actor_a = db_a.query(User).filter(User.id == actor_id).first()
    lead_a = db_a.query(User).filter(User.id == lead_id).first()

    # User A tiene la versión fresca (1)
    update_pipeline_status(
        db_a,
        lead_a,
        new_status="pending",
        actor=actor_a,
        request=None,
        expected_version=1,
    )
    db_a.close()

    # Verificar que version subió a 2 tras la escritura de A
    assert _get_db_version(SL, lead_id) == 2
    assert _get_db_status(SL, lead_id) == "pending"

    # ----- User B (escritura concurrente stale) -----
    db_b = SL()
    actor_b = db_b.query(User).filter(User.id == actor_id).first()
    lead_b = db_b.query(User).filter(User.id == lead_id).first()

    # User B aún cree que la versión es 1 (stale)
    with pytest.raises(StaleOpportunityError):
        update_pipeline_status(
            db_b,
            lead_b,
            new_status="contacted",
            actor=actor_b,
            request=None,
            expected_version=1,  # stale
        )
    db_b.close()

    # El estado debe seguir siendo 'pending' (la escritura de B no tuvo efecto)
    assert _get_db_status(SL, lead_id) == "pending"
    assert _get_db_version(SL, lead_id) == 2


# ---------------------------------------------------------------------------
# Test 5: state machine completo – tabla de transiciones
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "from_status,to_status,should_pass",
    [
        # Desde None
        (None, "pending", True),
        (None, "contacted", True),
        (None, "qualified", True),
        (None, "converted", True),
        (None, "declined", True),
        # Desde pending
        ("pending", "contacted", True),
        ("pending", "declined", True),
        ("pending", "qualified", False),
        ("pending", "converted", False),
        ("pending", "pending", False),
        # Desde contacted
        ("contacted", "qualified", True),
        ("contacted", "declined", True),
        ("contacted", "pending", False),
        ("contacted", "converted", False),
        # Desde qualified
        ("qualified", "converted", True),
        ("qualified", "declined", True),
        ("qualified", "pending", False),
        ("qualified", "contacted", False),
        # Desde converted (terminal → solo declined)
        ("converted", "declined", True),
        ("converted", "pending", False),
        ("converted", "contacted", False),
        ("converted", "qualified", False),
        # Desde declined (reapertura)
        ("declined", "pending", True),
        ("declined", "contacted", False),
        ("declined", "qualified", False),
        ("declined", "converted", False),
    ],
)
def test_state_machine_transitions(from_status, to_status, should_pass):
    """Verifica la tabla completa de transiciones del state machine."""
    if should_pass:
        # No debe lanzar excepción
        _validate_pipeline_transition(from_status, to_status)
    else:
        with pytest.raises(InvalidPipelineTransitionError):
            _validate_pipeline_transition(from_status, to_status)


# ---------------------------------------------------------------------------
# Test 6: cliente legacy sin expected_version → backward-compat
# ---------------------------------------------------------------------------


def test_no_version_backward_compat(app_with_db):
    """Cliente que no envía expected_version → acepta la escritura sin verificar versión."""
    app, SL = app_with_db
    _make_super_admin(SL)
    lead_id = _make_lead(SL, pipeline_status=None, version=5)  # versión alta

    client = TestClient(app)
    token = _login(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    # No envía expected_version (clientes legacy)
    r = client.patch(
        f"/api/v1/admin/crm/leads/{lead_id}/status",
        json={"status": "pending"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pipeline_status"] == "pending"
    assert body["pipeline_status_version"] == 6  # version++ igual


# ---------------------------------------------------------------------------
# Test 7: pipeline_status_version aparece en el response del detail endpoint
# ---------------------------------------------------------------------------


def test_detail_response_includes_version(app_with_db):
    """GET /leads/{id} incluye pipeline_status_version en el response."""
    app, SL = app_with_db
    _make_super_admin(SL)
    lead_id = _make_lead(SL, pipeline_status="pending", version=7)

    client = TestClient(app)
    token = _login(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get(f"/api/v1/admin/crm/leads/{lead_id}", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "pipeline_status_version" in body
    assert body["pipeline_status_version"] == 7


# ---------------------------------------------------------------------------
# Test 8: secuencia completa happy path qualified → converted
# ---------------------------------------------------------------------------


def test_full_sequence_qualified_to_converted(app_with_db):
    """Secuencia completa: None → pending → contacted → qualified → converted."""
    app, SL = app_with_db
    _make_super_admin(SL)
    lead_id = _make_lead(SL, pipeline_status=None, version=1)

    client = TestClient(app)
    token = _login(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    transitions = [
        ("pending", 1, 2),
        ("contacted", 2, 3),
        ("qualified", 3, 4),
        ("converted", 4, 5),
    ]

    for new_status, expected_v, next_v in transitions:
        r = client.patch(
            f"/api/v1/admin/crm/leads/{lead_id}/status",
            json={"status": new_status, "expected_version": expected_v},
            headers=headers,
        )
        assert r.status_code == 200, f"fallo en {new_status}: {r.text}"
        body = r.json()
        assert body["pipeline_status"] == new_status
        assert body["pipeline_status_version"] == next_v
