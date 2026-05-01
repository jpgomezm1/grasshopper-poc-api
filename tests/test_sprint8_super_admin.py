"""Sprint 8 · super admin panel · DB-backed integration tests.

Covers:
  - schools CRUD + soft delete + restore + super_admin/school_admin RBAC
  - licenses create/update + tier validation + status flip
  - programs CRUD + filter by country/budget_tier + active flag
  - audit_logs row created on each mutation
  - admin/stats/overview cached + super_admin only
  - license_service: seats enforcement + archived school block

Uses a temporary SQLite DB (no Postgres needed).
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def app_with_db(tmp_path, monkeypatch):
    """Boot FastAPI app against a per-test SQLite db.

    Each test creates a fresh in-memory engine + StaticPool, points the app's
    `get_db` dependency override at it, and clears module-level caches that
    would otherwise leak across tests.
    """
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

    # Recreate schema on the fresh engine
    from app.db.models import Base
    Base.metadata.create_all(bind=engine)

    from app.main import app
    # Override the EXACT callable that FastAPI captured at import time.
    app.dependency_overrides[dbmod.get_db] = _override_get_db

    # Reset stats cache so each test starts fresh
    from app.api.v1 import admin as admin_mod
    admin_mod._STATS_CACHE["data"] = None
    admin_mod._STATS_CACHE["ts"] = 0.0

    # GH-S11 · reset rate limiter buckets between tests
    from app.core.rate_limiter import limiter as gh_limiter
    gh_limiter.reset()

    yield app, TestingSessionLocal

    # cleanup
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _make_super_admin(SessionLocal):
    from app.db.models import User, UserRole
    from app.api.v1.auth import get_password_hash
    db = SessionLocal()
    u = User(
        email="root@grasshopper.example.com",
        hashed_password=get_password_hash("rootpass123"),
        name="Root",
        role=UserRole.SUPER_ADMIN,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


def _make_school_admin(SessionLocal, school_id, email="sadmin@school.example.com"):
    from uuid import UUID
    from app.db.models import User, UserRole
    from app.api.v1.auth import get_password_hash
    db = SessionLocal()
    sid = UUID(str(school_id)) if not isinstance(school_id, UUID) else school_id
    u = User(
        email=email,
        hashed_password=get_password_hash("schoolpass123"),
        name="School Admin",
        role=UserRole.SCHOOL_ADMIN,
        school_id=sid,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


def _login(client, email, password):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ============================================================================
# Schools CRUD + RBAC
# ============================================================================


def test_super_admin_can_create_list_update_archive_school(app_with_db):
    app, SessionLocal = app_with_db
    _make_super_admin(SessionLocal)
    client = TestClient(app)
    token = _login(client, "root@grasshopper.example.com", "rootpass123")
    H = {"Authorization": f"Bearer {token}"}

    # create
    r = client.post(
        "/api/v1/schools",
        json={"name": "Colegio Andino", "slug": "colegio-andino"},
        headers=H,
    )
    assert r.status_code == 201, r.text
    school = r.json()
    school_id = school["id"]
    assert school["slug"] == "colegio-andino"

    # list paginated
    r = client.get("/api/v1/schools?page=1&page_size=10", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["students_count"] == 0

    # patch
    r = client.patch(f"/api/v1/schools/{school_id}", json={"name": "Colegio Andino S.A."}, headers=H)
    assert r.status_code == 200
    assert r.json()["name"] == "Colegio Andino S.A."

    # soft-delete (archive)
    r = client.delete(f"/api/v1/schools/{school_id}", headers=H)
    assert r.status_code == 200
    assert r.json()["archived_at"]

    # archived school no longer in default list
    r = client.get("/api/v1/schools", headers=H)
    assert r.json()["total"] == 0

    # but visible with include_archived=true
    r = client.get("/api/v1/schools?include_archived=true", headers=H)
    assert r.json()["total"] == 1

    # restore
    r = client.post(f"/api/v1/schools/{school_id}/restore", headers=H)
    assert r.status_code == 200
    assert r.json()["archived_at"] is None


def test_school_admin_cannot_list_other_schools(app_with_db):
    app, SessionLocal = app_with_db
    _make_super_admin(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@grasshopper.example.com", "rootpass123")
    H_super = {"Authorization": f"Bearer {super_token}"}

    r = client.post("/api/v1/schools", json={"name": "Mine", "slug": "mine"}, headers=H_super)
    school_a = r.json()
    r = client.post("/api/v1/schools", json={"name": "Other", "slug": "other"}, headers=H_super)
    school_b = r.json()

    _make_school_admin(SessionLocal, school_a["id"], email="admin-a@mine.example.com")
    a_token = _login(client, "admin-a@mine.example.com", "schoolpass123")
    H_a = {"Authorization": f"Bearer {a_token}"}

    # list returns only own school
    r = client.get("/api/v1/schools", headers=H_a)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == school_a["id"]

    # cannot read other school
    r = client.get(f"/api/v1/schools/{school_b['id']}", headers=H_a)
    assert r.status_code == 403


def test_school_admin_cannot_create_school(app_with_db):
    app, SessionLocal = app_with_db
    _make_super_admin(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@grasshopper.example.com", "rootpass123")
    r = client.post("/api/v1/schools", json={"name": "S1", "slug": "s1"}, headers={"Authorization": f"Bearer {super_token}"})
    school_id = r.json()["id"]

    _make_school_admin(SessionLocal, school_id, email="sadmin1@school.example.com")
    a_token = _login(client, "sadmin1@school.example.com", "schoolpass123")
    H = {"Authorization": f"Bearer {a_token}"}
    r = client.post("/api/v1/schools", json={"name": "Try", "slug": "try"}, headers=H)
    assert r.status_code == 403


def test_archived_school_users_cannot_login(app_with_db):
    app, SessionLocal = app_with_db
    _make_super_admin(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@grasshopper.example.com", "rootpass123")
    r = client.post("/api/v1/schools", json={"name": "Zeta", "slug": "zeta"}, headers={"Authorization": f"Bearer {super_token}"})
    school_id = r.json()["id"]

    _make_school_admin(SessionLocal, school_id, email="zadmin@z.example.com")
    # archive school
    client.delete(f"/api/v1/schools/{school_id}", headers={"Authorization": f"Bearer {super_token}"})

    r = client.post("/api/v1/auth/login", json={"email": "zadmin@z.example.com", "password": "schoolpass123"})
    assert r.status_code == 403
    assert "archivado" in r.json()["detail"].lower()


# ============================================================================
# Licenses
# ============================================================================


def test_license_lifecycle(app_with_db):
    app, SessionLocal = app_with_db
    _make_super_admin(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@grasshopper.example.com", "rootpass123")
    H = {"Authorization": f"Bearer {super_token}"}

    r = client.post("/api/v1/schools", json={"name": "L1", "slug": "l1"}, headers=H)
    school_id = r.json()["id"]

    # create license
    r = client.post(
        f"/api/v1/schools/{school_id}/licenses",
        json={"tier": "pro", "seats": 100, "expires_at": (datetime.utcnow() + timedelta(days=365)).isoformat()},
        headers=H,
    )
    assert r.status_code == 201, r.text
    lic = r.json()
    assert lic["tier"] == "pro"
    assert lic["seats"] == 100

    # invalid tier rejected
    r = client.post(
        f"/api/v1/schools/{school_id}/licenses",
        json={"tier": "ultra", "seats": 1},
        headers=H,
    )
    assert r.status_code == 422

    # update license
    r = client.patch(f"/api/v1/licenses/{lic['id']}", json={"seats": 200}, headers=H)
    assert r.status_code == 200
    assert r.json()["seats"] == 200

    # cancel
    r = client.patch(f"/api/v1/licenses/{lic['id']}", json={"status": "cancelled"}, headers=H)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_license_seats_enforced_at_invite(app_with_db):
    app, SessionLocal = app_with_db
    _make_super_admin(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@grasshopper.example.com", "rootpass123")
    H_super = {"Authorization": f"Bearer {super_token}"}

    r = client.post("/api/v1/schools", json={"name": "Seat", "slug": "seat"}, headers=H_super)
    school_id = r.json()["id"]

    # license with only 1 seat
    client.post(
        f"/api/v1/schools/{school_id}/licenses",
        json={"tier": "starter", "seats": 1},
        headers=H_super,
    )

    _make_school_admin(SessionLocal, school_id, email="seatadmin@s.example.com")
    a_token = _login(client, "seatadmin@s.example.com", "schoolpass123")
    H = {"Authorization": f"Bearer {a_token}"}

    # 1st invite OK
    r = client.post(
        "/api/v1/auth/invite-student",
        json={"email": "kid1@s.example.com", "password": "kid12345"},
        headers=H,
    )
    assert r.status_code == 201

    # 2nd invite blocked (seats=1)
    r = client.post(
        "/api/v1/auth/invite-student",
        json={"email": "kid2@s.example.com", "password": "kid22345"},
        headers=H,
    )
    assert r.status_code == 403
    assert "cupo" in r.json()["detail"].lower()


# ============================================================================
# Programs catalogue
# ============================================================================


def test_super_admin_program_crud_and_filters(app_with_db):
    app, SessionLocal = app_with_db
    _make_super_admin(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@grasshopper.example.com", "rootpass123")
    H = {"Authorization": f"Bearer {super_token}"}

    # create
    payload = {
        "program_id": "PRG-001",
        "name": "BSc Computer Science",
        "slug": "bsc-cs-canada",
        "country": "Canadá",
        "city": "Toronto",
        "institution": "Univ. de Toronto",
        "type": "pregrado",
        "area": "tecnologia",
        "subject": "computer science",
        "duration_months": 48,
        "cost_total": 25000,
        "currency": "CAD",
        "budget_tier": "high",
        "alliance_type": "estandar",
        "active": True,
    }
    r = client.post("/api/v1/programs", json=payload, headers=H)
    assert r.status_code == 201, r.text
    program_id = r.json()["id"]

    # filter by country
    r = client.get("/api/v1/programs?country=Canad%C3%A1", headers=H)
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # filter by budget_tier
    r = client.get("/api/v1/programs?budget_tier=low", headers=H)
    assert r.json()["total"] == 0

    # update
    r = client.patch(f"/api/v1/programs/{program_id}", json={"cost_total": 26000}, headers=H)
    assert r.status_code == 200
    assert r.json()["cost_total"] == 26000

    # soft delete
    r = client.delete(f"/api/v1/programs/{program_id}", headers=H)
    assert r.status_code == 200
    assert r.json()["deactivated"] is True

    # super_admin still sees inactive in list with active=false
    r = client.get("/api/v1/programs?active=false", headers=H)
    assert r.json()["total"] == 1


def test_school_admin_cannot_mutate_catalog(app_with_db):
    app, SessionLocal = app_with_db
    _make_super_admin(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@grasshopper.example.com", "rootpass123")
    H_super = {"Authorization": f"Bearer {super_token}"}

    r = client.post("/api/v1/schools", json={"name": "Catalog Test", "slug": "cat-test"}, headers=H_super)
    school_id = r.json()["id"]
    _make_school_admin(SessionLocal, school_id, email="catadmin@c.example.com")
    a_token = _login(client, "catadmin@c.example.com", "schoolpass123")
    H = {"Authorization": f"Bearer {a_token}"}

    # cannot create
    r = client.post(
        "/api/v1/programs",
        json={
            "program_id": "X-1",
            "name": "Xprog",
            "slug": "x-1",
            "country": "Canadá",
            "institution": "Univ",
            "type": "pregrado",
            "duration_months": 12,
            "cost_total": 1000,
            "budget_tier": "low",
            "active": True,
        },
        headers=H,
    )
    assert r.status_code == 403


# ============================================================================
# Admin stats + audit log
# ============================================================================


def test_admin_stats_and_audit(app_with_db):
    app, SessionLocal = app_with_db
    _make_super_admin(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@grasshopper.example.com", "rootpass123")
    H = {"Authorization": f"Bearer {super_token}"}

    # mutate to populate audit log
    r = client.post("/api/v1/schools", json={"name": "Stats School", "slug": "stats-school"}, headers=H)
    school_id = r.json()["id"]

    # stats
    r = client.get("/api/v1/admin/stats/overview", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["total_schools"] == 1
    assert body["active_schools"] == 1
    assert "cached_at" in body

    # audit log returns the school.create event
    r = client.get("/api/v1/admin/audit-log", headers=H)
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["action"] == "school.create" for i in items)

    # filter by action
    r = client.get("/api/v1/admin/audit-log?action=school.create", headers=H)
    assert r.json()["total"] >= 1


def test_audit_log_super_admin_only(app_with_db):
    app, SessionLocal = app_with_db
    _make_super_admin(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@grasshopper.example.com", "rootpass123")
    H_super = {"Authorization": f"Bearer {super_token}"}
    r = client.post("/api/v1/schools", json={"name": "Q-school", "slug": "qschool"}, headers=H_super)
    school_id = r.json()["id"]
    _make_school_admin(SessionLocal, school_id, email="qadmin@q.example.com")
    a_token = _login(client, "qadmin@q.example.com", "schoolpass123")
    r = client.get("/api/v1/admin/audit-log", headers={"Authorization": f"Bearer {a_token}"})
    assert r.status_code == 403


# ============================================================================
# license_service unit
# ============================================================================


def test_license_service_archived_school_blocked(app_with_db):
    app, SessionLocal = app_with_db
    _make_super_admin(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@grasshopper.example.com", "rootpass123")
    H = {"Authorization": f"Bearer {super_token}"}
    r = client.post("/api/v1/schools", json={"name": "ARC", "slug": "arc"}, headers=H)
    school_id = r.json()["id"]
    client.post(f"/api/v1/schools/{school_id}/licenses", json={"tier": "starter", "seats": 100}, headers=H)
    client.delete(f"/api/v1/schools/{school_id}", headers=H)

    from app.services.license_service import can_register_student
    from uuid import UUID
    db = SessionLocal()
    ok, reason = can_register_student(db, UUID(school_id))
    db.close()
    assert ok is False
    assert reason == "school_archived"
