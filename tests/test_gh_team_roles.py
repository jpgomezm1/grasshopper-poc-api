"""GH-ROLES-001 · tests for the gh_advisor / gh_commercial roles + contact-request flow.

Covers:
  - POST /students/me/request-gh-contact (student-only · idempotent)
  - GET  /students/me/gh-contact-status
  - GET  /gh/students  (gh_advisor + super_admin · scope filter · isolation)
  - GET  /gh/students/{id}  (visibility gate · 403 for non-opted-in B2B)
  - GET  /gh/contact-requests  (advisor + commercial + super_admin)
  - PATCH /gh/contact-requests/{id}/status  (commercial + super_admin only)
  - 403 paths for school_admin / psychologist / wrong-team accesses.

SQLite + FastAPI TestClient · no Postgres needed.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------


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


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _make_user(SessionLocal, *, email, role, school_id=None, password="testpass123"):
    from app.db.models import User
    from app.api.v1.auth import get_password_hash
    db = SessionLocal()
    u = User(
        email=email,
        hashed_password=get_password_hash(password),
        name=email.split("@")[0],
        role=role,
        school_id=school_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


def _make_school(SessionLocal, name="Test School", slug="test-school"):
    from app.db.models import School
    db = SessionLocal()
    s = School(name=name, slug=slug)
    db.add(s)
    db.commit()
    db.refresh(s)
    school_id = s.id
    db.close()
    return school_id


def _login(client, email, password="testpass123"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ============================================================================
# Student-side: POST /students/me/request-gh-contact
# ============================================================================


def test_student_can_request_gh_contact(app_with_db):
    app, SessionLocal = app_with_db
    school_id = _make_school(SessionLocal)
    from app.db.models import UserRole
    _make_user(SessionLocal, email="alumno1@b2b.example.com", role=UserRole.STUDENT, school_id=school_id)

    with TestClient(app) as client:
        token = _login(client, "alumno1@b2b.example.com")
        H = {"Authorization": f"Bearer {token}"}

        r = client.post(
            "/api/v1/students/me/request-gh-contact",
            json={"message": "Quiero hablar con un orientador"},
            headers=H,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "pending"
        assert body["message"] == "Quiero hablar con un orientador"
        assert body["requested_at"] is not None

        # Re-read state
        r = client.get("/api/v1/students/me/gh-contact-status", headers=H)
        assert r.status_code == 200
        assert r.json()["status"] == "pending"


def test_student_gh_contact_idempotent_resets_to_pending(app_with_db):
    app, SessionLocal = app_with_db
    school_id = _make_school(SessionLocal)
    from app.db.models import UserRole, User
    _make_user(SessionLocal, email="alumno2@b2b.example.com", role=UserRole.STUDENT, school_id=school_id)

    # Manually mark as 'declined' to simulate a closed previous cycle
    db = SessionLocal()
    u = db.query(User).filter(User.email == "alumno2@b2b.example.com").first()
    from datetime import datetime
    u.gh_contact_requested_at = datetime.utcnow()
    u.gh_contact_status = "declined"
    db.commit()
    db.close()

    with TestClient(app) as client:
        token = _login(client, "alumno2@b2b.example.com")
        H = {"Authorization": f"Bearer {token}"}
        r = client.post(
            "/api/v1/students/me/request-gh-contact",
            json={"message": "Otra vez"},
            headers=H,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "pending"


def test_non_student_cannot_request_gh_contact(app_with_db):
    app, SessionLocal = app_with_db
    school_id = _make_school(SessionLocal)
    from app.db.models import UserRole
    _make_user(SessionLocal, email="psy@b2b.example.com", role=UserRole.PSYCHOLOGIST, school_id=school_id)

    with TestClient(app) as client:
        token = _login(client, "psy@b2b.example.com")
        H = {"Authorization": f"Bearer {token}"}
        r = client.post("/api/v1/students/me/request-gh-contact", json={}, headers=H)
        assert r.status_code == 403


def test_gh_contact_status_null_when_never_requested(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    _make_user(SessionLocal, email="b2c@gh.example.com", role=UserRole.STUDENT)

    with TestClient(app) as client:
        token = _login(client, "b2c@gh.example.com")
        H = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/v1/students/me/gh-contact-status", headers=H)
        assert r.status_code == 200
        assert r.json() is None


# ============================================================================
# GH-team: GET /gh/students (gh_advisor)
# ============================================================================


def test_gh_advisor_sees_b2c_and_optedin_b2b(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    school_id = _make_school(SessionLocal)
    _make_user(SessionLocal, email="advisor@gh.example.com", role=UserRole.GH_ADVISOR)
    _make_user(SessionLocal, email="b2c1@gh.example.com", role=UserRole.STUDENT)
    _make_user(SessionLocal, email="b2c2@gh.example.com", role=UserRole.STUDENT)
    _make_user(SessionLocal, email="b2b_silent@gh.example.com", role=UserRole.STUDENT, school_id=school_id)
    _make_user(SessionLocal, email="b2b_opted@gh.example.com", role=UserRole.STUDENT, school_id=school_id)

    # mark one as opted-in
    from app.db.models import User
    from datetime import datetime
    db = SessionLocal()
    u = db.query(User).filter(User.email == "b2b_opted@gh.example.com").first()
    u.gh_contact_requested_at = datetime.utcnow()
    u.gh_contact_status = "pending"
    u.gh_contact_message = "hola"
    db.commit()
    db.close()

    with TestClient(app) as client:
        token = _login(client, "advisor@gh.example.com")
        H = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/v1/gh/students", headers=H)
        assert r.status_code == 200, r.text
        body = r.json()
        emails = sorted(item["email"] for item in body["items"])
        assert emails == ["b2b_opted@gh.example.com", "b2c1@gh.example.com", "b2c2@gh.example.com"]
        assert body["total"] == 3


def test_gh_students_scope_filters(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole, User
    from datetime import datetime
    school_id = _make_school(SessionLocal)
    _make_user(SessionLocal, email="advisor@gh.example.com", role=UserRole.GH_ADVISOR)
    _make_user(SessionLocal, email="b2c@gh.example.com", role=UserRole.STUDENT)
    _make_user(SessionLocal, email="b2b_opted@gh.example.com", role=UserRole.STUDENT, school_id=school_id)
    db = SessionLocal()
    u = db.query(User).filter(User.email == "b2b_opted@gh.example.com").first()
    u.gh_contact_requested_at = datetime.utcnow()
    u.gh_contact_status = "pending"
    db.commit()
    db.close()

    with TestClient(app) as client:
        token = _login(client, "advisor@gh.example.com")
        H = {"Authorization": f"Bearer {token}"}

        r = client.get("/api/v1/gh/students?scope=b2c", headers=H)
        assert r.status_code == 200
        assert [i["email"] for i in r.json()["items"]] == ["b2c@gh.example.com"]

        r = client.get("/api/v1/gh/students?scope=contact_requested", headers=H)
        assert r.status_code == 200
        assert [i["email"] for i in r.json()["items"]] == ["b2b_opted@gh.example.com"]


def test_gh_advisor_cannot_see_silent_b2b_student(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole, User
    school_id = _make_school(SessionLocal)
    _make_user(SessionLocal, email="advisor@gh.example.com", role=UserRole.GH_ADVISOR)
    _make_user(SessionLocal, email="silent@b2b.example.com", role=UserRole.STUDENT, school_id=school_id)

    db = SessionLocal()
    silent_id = str(db.query(User).filter(User.email == "silent@b2b.example.com").first().id)
    db.close()

    with TestClient(app) as client:
        token = _login(client, "advisor@gh.example.com")
        H = {"Authorization": f"Bearer {token}"}
        r = client.get(f"/api/v1/gh/students/{silent_id}", headers=H)
        assert r.status_code == 403


def test_gh_commercial_blocked_from_gh_students_endpoint(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    _make_user(SessionLocal, email="commercial@gh.example.com", role=UserRole.GH_COMMERCIAL)

    with TestClient(app) as client:
        token = _login(client, "commercial@gh.example.com")
        H = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/v1/gh/students", headers=H)
        assert r.status_code == 403


def test_school_admin_blocked_from_gh_endpoints(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    school_id = _make_school(SessionLocal)
    _make_user(SessionLocal, email="schooladm@b2b.example.com", role=UserRole.SCHOOL_ADMIN, school_id=school_id)

    with TestClient(app) as client:
        token = _login(client, "schooladm@b2b.example.com")
        H = {"Authorization": f"Bearer {token}"}
        for path in ("/api/v1/gh/students", "/api/v1/gh/contact-requests"):
            r = client.get(path, headers=H)
            assert r.status_code == 403, f"{path} should be 403"


# ============================================================================
# GH-team: contact-requests list + status update
# ============================================================================


def test_contact_requests_list_visible_to_gh_team(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole, User
    from datetime import datetime
    school_id = _make_school(SessionLocal)
    _make_user(SessionLocal, email="advisor@gh.example.com", role=UserRole.GH_ADVISOR)
    _make_user(SessionLocal, email="commercial@gh.example.com", role=UserRole.GH_COMMERCIAL)
    _make_user(SessionLocal, email="opted@b2b.example.com", role=UserRole.STUDENT, school_id=school_id)

    db = SessionLocal()
    u = db.query(User).filter(User.email == "opted@b2b.example.com").first()
    u.gh_contact_requested_at = datetime.utcnow()
    u.gh_contact_status = "pending"
    u.gh_contact_message = "necesito orientacion"
    db.commit()
    db.close()

    with TestClient(app) as client:
        for actor in ("advisor@gh.example.com", "commercial@gh.example.com"):
            token = _login(client, actor)
            H = {"Authorization": f"Bearer {token}"}
            r = client.get("/api/v1/gh/contact-requests", headers=H)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total"] == 1
            assert body["items"][0]["email"] == "opted@b2b.example.com"


def test_only_commercial_or_super_can_change_status(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole, User
    from datetime import datetime
    school_id = _make_school(SessionLocal)
    _make_user(SessionLocal, email="advisor@gh.example.com", role=UserRole.GH_ADVISOR)
    _make_user(SessionLocal, email="commercial@gh.example.com", role=UserRole.GH_COMMERCIAL)
    _make_user(SessionLocal, email="opted@b2b.example.com", role=UserRole.STUDENT, school_id=school_id)
    db = SessionLocal()
    u = db.query(User).filter(User.email == "opted@b2b.example.com").first()
    u.gh_contact_requested_at = datetime.utcnow()
    u.gh_contact_status = "pending"
    target_id = str(u.id)
    db.commit()
    db.close()

    with TestClient(app) as client:
        # advisor → 403
        token = _login(client, "advisor@gh.example.com")
        r = client.patch(
            f"/api/v1/gh/contact-requests/{target_id}/status",
            json={"status": "in_progress"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

        # commercial → 200
        token = _login(client, "commercial@gh.example.com")
        r = client.patch(
            f"/api/v1/gh/contact-requests/{target_id}/status",
            json={"status": "in_progress"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["gh_contact_status"] == "in_progress"


def test_status_update_requires_active_request(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole, User
    school_id = _make_school(SessionLocal)
    _make_user(SessionLocal, email="commercial@gh.example.com", role=UserRole.GH_COMMERCIAL)
    _make_user(SessionLocal, email="silent@b2b.example.com", role=UserRole.STUDENT, school_id=school_id)
    db = SessionLocal()
    target_id = str(db.query(User).filter(User.email == "silent@b2b.example.com").first().id)
    db.close()

    with TestClient(app) as client:
        token = _login(client, "commercial@gh.example.com")
        r = client.patch(
            f"/api/v1/gh/contact-requests/{target_id}/status",
            json={"status": "converted"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 409


def test_invalid_status_rejected(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole, User
    from datetime import datetime
    school_id = _make_school(SessionLocal)
    _make_user(SessionLocal, email="commercial@gh.example.com", role=UserRole.GH_COMMERCIAL)
    _make_user(SessionLocal, email="opted@b2b.example.com", role=UserRole.STUDENT, school_id=school_id)
    db = SessionLocal()
    u = db.query(User).filter(User.email == "opted@b2b.example.com").first()
    u.gh_contact_requested_at = datetime.utcnow()
    u.gh_contact_status = "pending"
    target_id = str(u.id)
    db.commit()
    db.close()

    with TestClient(app) as client:
        token = _login(client, "commercial@gh.example.com")
        r = client.patch(
            f"/api/v1/gh/contact-requests/{target_id}/status",
            json={"status": "garbage"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Pydantic Literal rejects unknown value with 422
        assert r.status_code == 422


# ============================================================================
# Super-admin overrides
# ============================================================================


def test_super_admin_can_see_silent_b2b_via_gh_endpoint(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole, User
    school_id = _make_school(SessionLocal)
    _make_user(SessionLocal, email="root@gh.example.com", role=UserRole.SUPER_ADMIN)
    _make_user(SessionLocal, email="silent@b2b.example.com", role=UserRole.STUDENT, school_id=school_id)

    db = SessionLocal()
    target_id = str(db.query(User).filter(User.email == "silent@b2b.example.com").first().id)
    db.close()

    with TestClient(app) as client:
        token = _login(client, "root@gh.example.com")
        H = {"Authorization": f"Bearer {token}"}
        r = client.get(f"/api/v1/gh/students/{target_id}", headers=H)
        assert r.status_code == 200
        assert r.json()["email"] == "silent@b2b.example.com"
