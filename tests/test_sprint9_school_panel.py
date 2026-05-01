"""Sprint 9 · School panel · DB-backed integration tests.

Covers:
  - GET /school/me + /dashboard + /reports + /students + /students/{id}
  - GET /school/me/students/export.csv
  - POST /school/me/logo (school_admin only)
  - POST /school/me/invitations (school_admin: any role · psychologist: students only)
  - GET /school/me/invitations + DELETE revoke
  - POST /invitations/{token}/accept
  - IDOR isolation (cross-school 404, no leak)
  - Read-only marker for psychologist
  - Classification logic (decidido / en_progreso / no_iniciado / perdido)

Uses a temporary SQLite DB (no Postgres needed). Email service stubs
gracefully when Resend is not configured.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ============================================================================
# Fixtures · same scaffold as sprint 8 tests
# ============================================================================


@pytest.fixture()
def app_with_db(tmp_path, monkeypatch):
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

    # Reset stats caches so each test starts fresh
    from app.api.v1 import admin as admin_mod
    admin_mod._STATS_CACHE["data"] = None
    admin_mod._STATS_CACHE["ts"] = 0.0
    from app.services import school_panel_service as sps
    sps._DASHBOARD_CACHE.clear()
    sps._REPORTS_CACHE.clear()

    # GH-S11 · reset rate limiter buckets between tests
    from app.core.rate_limiter import limiter as gh_limiter
    gh_limiter.reset()

    yield app, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _login(client, email, password):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _make_super(SessionLocal, email="root@gh.example.com"):
    from app.db.models import User, UserRole
    from app.api.v1.auth import get_password_hash
    db = SessionLocal()
    u = User(
        email=email,
        hashed_password=get_password_hash("rootpass123"),
        name="Root",
        role=UserRole.SUPER_ADMIN,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


def _make_school(client, super_token, name, slug, seats=50):
    H = {"Authorization": f"Bearer {super_token}"}
    r = client.post("/api/v1/schools", json={"name": name, "slug": slug}, headers=H)
    assert r.status_code == 201, r.text
    school_id = r.json()["id"]
    # license required so seats enforcement is satisfied
    r = client.post(
        f"/api/v1/schools/{school_id}/licenses",
        json={
            "tier": "pro",
            "seats": seats,
            "expires_at": (datetime.utcnow() + timedelta(days=365)).isoformat(),
        },
        headers=H,
    )
    assert r.status_code == 201, r.text
    return school_id


def _make_school_user(SessionLocal, school_id, email, role):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash
    db = SessionLocal()
    u = User(
        email=email,
        hashed_password=get_password_hash("schoolpass123"),
        name=email.split("@")[0],
        role=UserRole(role),
        school_id=UUID(str(school_id)),
        onboarding_status=OnboardingStatus.COMPLETED,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


def _seed_student(
    SessionLocal,
    school_id,
    email,
    *,
    onboarding="not_started",
    tests=0,
    has_profile=False,
    has_report=False,
    last_active_offset_days=None,
):
    """Create a student with synthetic signals for classification tests."""
    from app.db.models import (
        ConsolidatedProfileCache,
        OnboardingStatus,
        Report,
        User,
        UserRole,
        VocationalTestResult,
    )
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    u = User(
        email=email,
        hashed_password=get_password_hash("studentpass123"),
        name=email.split("@")[0],
        role=UserRole.STUDENT,
        school_id=UUID(str(school_id)),
        onboarding_status=OnboardingStatus(onboarding),
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    # tests
    for i in range(tests):
        db.add(
            VocationalTestResult(
                user_id=u.id,
                test_id=f"riasec" if i == 0 else f"mbti_{i}",
                answers={"a": 1},
                scores=(
                    {"R": 12, "I": 10, "A": 5, "S": 8, "E": 4, "C": 6}
                    if i == 0
                    else {"type": "INTJ"}
                ),
                source="internal",
            )
        )
    if has_profile:
        db.add(
            ConsolidatedProfileCache(
                user_id=u.id,
                profile_hash="abc",
                profile_data={"summary": "ok"},
                recommendations_data=[
                    {"program_id": "p1", "name": "Ing. Sistemas", "fit_score": 88, "rationale": "fit"}
                ],
            )
        )
    if has_report:
        db.add(Report(user_id=u.id, file_path=f"{u.id}/reports/x.pdf"))
    db.commit()

    if last_active_offset_days is not None:
        u_db = db.query(User).filter(User.id == u.id).first()
        u_db.updated_at = datetime.utcnow() - timedelta(days=last_active_offset_days)
        db.commit()
    user_id = u.id  # capture before close
    db.close()
    # Return a small struct with the id (avoids DetachedInstance issues)
    class _StudentHandle:
        pass
    h = _StudentHandle()
    h.id = user_id
    h.email = email
    return h


# ============================================================================
# Tests
# ============================================================================


def test_school_admin_dashboard_kpis_reflect_cohort(app_with_db):
    """GH-S9-BE-01 + GH-S9-BE-04 · KPIs computed correctly."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")

    school_a = _make_school(client, super_token, "Andino", "andino")
    _make_school_user(SessionLocal, school_a, "admin@andino.com", "school_admin")

    # 1 decidido, 1 en_progreso, 1 no_iniciado, 1 perdido
    _seed_student(
        SessionLocal, school_a, "decidido@andino.com",
        onboarding="completed", tests=5, has_profile=True, has_report=True,
    )
    _seed_student(
        SessionLocal, school_a, "progreso@andino.com",
        onboarding="completed", tests=2, has_profile=False, has_report=False,
    )
    _seed_student(
        SessionLocal, school_a, "no_iniciado@andino.com",
        onboarding="not_started", tests=0, has_profile=False, has_report=False,
    )
    _seed_student(
        SessionLocal, school_a, "perdido@andino.com",
        onboarding="completed", tests=1, has_profile=False, has_report=False,
        last_active_offset_days=40,
    )

    token = _login(client, "admin@andino.com", "schoolpass123")
    H = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/school/me/dashboard", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_students"] == 4
    assert body["students_completado"] == 1
    assert body["students_en_progreso"] == 1
    assert body["students_no_iniciado"] == 1
    assert body["students_perdido"] == 1
    assert body["active_license"]["tier"] == "pro"
    assert body["active_license"]["seats_total"] == 50


def test_school_admin_lists_only_its_school_students(app_with_db):
    """GH-S9-QA-01 · IDOR · school A admin must NOT see students from school B."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")

    school_a = _make_school(client, super_token, "AlphaA", "alpha-a")
    school_b = _make_school(client, super_token, "BetaB", "beta-b")
    _make_school_user(SessionLocal, school_a, "ad-a@a.com", "school_admin")
    _make_school_user(SessionLocal, school_b, "ad-b@b.com", "school_admin")

    s_a = _seed_student(SessionLocal, school_a, "alice@a.com", onboarding="completed", tests=2)
    s_b = _seed_student(SessionLocal, school_b, "bob@b.com", onboarding="completed", tests=2)

    token_a = _login(client, "ad-a@a.com", "schoolpass123")
    H_a = {"Authorization": f"Bearer {token_a}"}

    # list shows only its own
    r = client.get("/api/v1/school/me/students?page_size=50", headers=H_a)
    assert r.status_code == 200
    body = r.json()
    emails = {item["email"] for item in body["items"]}
    assert "alice@a.com" in emails
    assert "bob@b.com" not in emails

    # IDOR · cannot fetch student of school B by id (404, no leak)
    r = client.get(f"/api/v1/school/me/students/{s_b.id}", headers=H_a)
    assert r.status_code == 404


def test_psychologist_is_read_only_marker(app_with_db):
    """GH-S9-BE-03 · psychologist gets read_only_for_caller=True."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")

    school = _make_school(client, super_token, "PsySchool", "psy-school")
    _make_school_user(SessionLocal, school, "psy@psy.com", "psychologist")
    student = _seed_student(SessionLocal, school, "stu@psy.com", onboarding="completed", tests=1)

    token = _login(client, "psy@psy.com", "schoolpass123")
    H = {"Authorization": f"Bearer {token}"}

    r = client.get(f"/api/v1/school/me/students/{student.id}", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["read_only_for_caller"] is True


def test_psychologist_cannot_invite_psychologist(app_with_db):
    """GH-S9 · permission matrix · psychologist may invite student only."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school = _make_school(client, super_token, "S1", "s1")
    _make_school_user(SessionLocal, school, "psy@s1.com", "psychologist")

    token = _login(client, "psy@s1.com", "schoolpass123")
    H = {"Authorization": f"Bearer {token}"}

    # student → ok
    r = client.post(
        "/api/v1/school/me/invitations",
        json={"email": "newstu@s1.com", "role": "student"},
        headers=H,
    )
    assert r.status_code == 201, r.text

    # psychologist → 403
    r = client.post(
        "/api/v1/school/me/invitations",
        json={"email": "newpsy@s1.com", "role": "psychologist"},
        headers=H,
    )
    assert r.status_code == 403


def test_invitation_accept_flow_creates_student_and_isolates_school(app_with_db):
    """GH-S9 · public accept · creates user + binds school + returns token."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school = _make_school(client, super_token, "Open", "open-school")
    _make_school_user(SessionLocal, school, "ad@open.com", "school_admin")

    token = _login(client, "ad@open.com", "schoolpass123")
    H = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/api/v1/school/me/invitations",
        json={"email": "valeria@open.com", "role": "student"},
        headers=H,
    )
    assert r.status_code == 201
    invite = r.json()
    accept_url = invite["accept_url"]
    assert accept_url and "/invite/" in accept_url
    # extract token from url
    invite_token = accept_url.rsplit("/", 1)[-1]

    # Public lookup OK
    r = client.get(f"/api/v1/invitations/{invite_token}")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["role"] == "student"

    # Public accept OK
    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "MyStrongPass1", "name": "Valeria"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "student"
    assert UUID(body["school_id"]) == UUID(school)

    # Re-using the token fails
    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "Whatever123", "name": "Anyone"},
    )
    assert r.status_code in (404, 410)


def test_invitation_revoke_blocks_accept(app_with_db):
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school = _make_school(client, super_token, "Rev", "rev")
    _make_school_user(SessionLocal, school, "ad@rev.com", "school_admin")

    token = _login(client, "ad@rev.com", "schoolpass123")
    H = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/api/v1/school/me/invitations",
        json={"email": "revoked@rev.com", "role": "student"},
        headers=H,
    )
    inv = r.json()
    invite_token = inv["accept_url"].rsplit("/", 1)[-1]

    # revoke
    r = client.delete(f"/api/v1/school/me/invitations/{inv['id']}", headers=H)
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"

    # accept now 410
    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "Whatever123"},
    )
    assert r.status_code == 410


def test_csv_export_only_own_school(app_with_db):
    """GH-S9-BE-06 · CSV export honors school isolation."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school_a = _make_school(client, super_token, "CsvA", "csv-a")
    school_b = _make_school(client, super_token, "CsvB", "csv-b")
    _make_school_user(SessionLocal, school_a, "ad@csva.com", "school_admin")
    _seed_student(SessionLocal, school_a, "alice-csv@a.com", onboarding="completed", tests=1)
    _seed_student(SessionLocal, school_b, "bob-csv@b.com", onboarding="completed", tests=1)

    token = _login(client, "ad@csva.com", "schoolpass123")
    H = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/v1/school/me/students/export.csv", headers=H)
    assert r.status_code == 200
    text = r.text
    assert "alice-csv@a.com" in text
    assert "bob-csv@b.com" not in text
    assert text.startswith("user_id,email,name,journey_status")


def test_logo_upload_school_admin_only(app_with_db):
    """GH-S9-BE-07 · upload logo requires school_admin (psychologist forbidden)."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school = _make_school(client, super_token, "LogoSchool", "logo-school")
    _make_school_user(SessionLocal, school, "ad@logo.com", "school_admin")
    _make_school_user(SessionLocal, school, "psy@logo.com", "psychologist")

    # 1x1 png
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc\x0f"
        b"\x00\x00\x01\x01\x01\x00\x1b\xd2c\x9b\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    psy_token = _login(client, "psy@logo.com", "schoolpass123")
    r = client.post(
        "/api/v1/school/me/logo",
        files={"file": ("logo.png", png_bytes, "image/png")},
        headers={"Authorization": f"Bearer {psy_token}"},
    )
    assert r.status_code == 403

    ad_token = _login(client, "ad@logo.com", "schoolpass123")
    r = client.post(
        "/api/v1/school/me/logo",
        files={"file": ("logo.png", png_bytes, "image/png")},
        headers={"Authorization": f"Bearer {ad_token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["logo_url"]


def test_classification_logic_unit():
    """GH-S9-BE-04 · the pure helpers."""
    from app.services.school_panel_service import (
        classify_journey,
        compute_completion_pct,
        DECIDED_MIN_PCT,
    )

    # decidido: 100% completion
    pct = compute_completion_pct(
        onboarding_completed=True,
        tests_completed=5,
        has_profile=True,
        has_saved=True,
        has_report=True,
    )
    assert pct >= DECIDED_MIN_PCT
    assert classify_journey(completion_pct=pct, last_active_at=datetime.utcnow()) == "completado"

    # no_iniciado: nothing done
    pct = compute_completion_pct(
        onboarding_completed=False,
        tests_completed=0,
        has_profile=False,
        has_saved=False,
        has_report=False,
    )
    assert pct == 0
    assert classify_journey(completion_pct=pct, last_active_at=None) == "no_iniciado"

    # perdido: started but ghosted
    pct = compute_completion_pct(
        onboarding_completed=True,
        tests_completed=1,
        has_profile=False,
        has_saved=False,
        has_report=False,
    )
    last = datetime.utcnow() - timedelta(days=40)
    assert classify_journey(completion_pct=pct, last_active_at=last) == "perdido"

    # en_progreso: active and below 80%
    pct = compute_completion_pct(
        onboarding_completed=True,
        tests_completed=2,
        has_profile=False,
        has_saved=False,
        has_report=False,
    )
    assert classify_journey(completion_pct=pct, last_active_at=datetime.utcnow()) == "en_progreso"


# ============================================================================
# QA-AUD-001 / QA-AUD-052 · invitation creation must invoke send_email
# (Sprint 11.5 · BE-01 · post-handoff QA Audit Run #3)
# ============================================================================


def test_invitation_create_invokes_send_email(app_with_db, monkeypatch):
    """The S9 invitation flow must call email_service.send_email · regression
    guard for QA-AUD-001 (the function did not exist · ImportError swallowed).
    """
    from app.services import email_service as svc

    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school = _make_school(client, super_token, "MailSchool", "mail-school")
    _make_school_user(SessionLocal, school, "ad@mail.com", "school_admin")

    # Capture send_email calls
    captured: list[dict] = []
    original_send_email = svc.send_email

    def _spy_send_email(**kwargs):
        captured.append(kwargs)
        return svc.EmailSendResult(provider="spy", delivered=True, message_id="msg-1")

    monkeypatch.setattr(svc, "send_email", _spy_send_email)

    token = _login(client, "ad@mail.com", "schoolpass123")
    H = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/api/v1/school/me/invitations",
        json={"email": "newstu@mail.com", "role": "student"},
        headers=H,
    )
    assert r.status_code == 201, r.text

    assert len(captured) == 1, "send_email must be called exactly once on invitation create"
    call = captured[0]
    assert call["to"] == "newstu@mail.com"
    assert "Invitación" in call["subject"]
    assert "MailSchool" in call["subject"]
    assert "html_body" in call and call["html_body"]
    assert "text_body" in call and "Activa tu cuenta" in call["text_body"]
    # accept_url is embedded in both bodies
    assert "/invite/" in call["html_body"]
    assert "/invite/" in call["text_body"]

    # restore
    monkeypatch.setattr(svc, "send_email", original_send_email)


def test_student_filters_journey_status(app_with_db):
    """GH-S9-BE-02 · journey_status filter."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school = _make_school(client, super_token, "Filter", "filter-school")
    _make_school_user(SessionLocal, school, "ad@filter.com", "school_admin")

    _seed_student(SessionLocal, school, "ok1@filter.com", onboarding="completed", tests=5, has_profile=True, has_report=True)
    _seed_student(SessionLocal, school, "ok2@filter.com", onboarding="completed", tests=5, has_profile=True, has_report=True)
    _seed_student(SessionLocal, school, "lost@filter.com", onboarding="completed", tests=1, last_active_offset_days=40)

    token = _login(client, "ad@filter.com", "schoolpass123")
    H = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/school/me/students?journey_status=completado", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    for it in body["items"]:
        assert it["journey_status"] == "completado"

    r = client.get("/api/v1/school/me/students?journey_status=perdido", headers=H)
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "lost@filter.com"


def test_super_admin_without_school_id_blocked(app_with_db):
    """super_admin without school_id cannot use /school/me/* (defensive)."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    H = {"Authorization": f"Bearer {super_token}"}
    r = client.get("/api/v1/school/me/dashboard", headers=H)
    assert r.status_code == 400
