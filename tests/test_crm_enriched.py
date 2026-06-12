"""GH-CRM-001 · tests for the enriched CRM module.

Covers:
  - GET   /api/v1/admin/crm/leads · super_admin + gh_commercial happy path
  - GET   /api/v1/admin/crm/leads · 403 for gh_advisor / school_admin / student
  - GET   /api/v1/admin/crm/leads · origin filter (grasshopper / school_radar)
  - GET   /api/v1/admin/crm/leads · score band filter
  - GET   /api/v1/admin/crm/leads/{id} · ownership gate (school_radar < 60 → 403 for commercial)
  - PATCH /api/v1/admin/crm/leads/{id}/status · audit + bitrix mock log
  - GET   /api/v1/admin/crm/kpis · structure
  - GET   /api/v1/admin/crm/leads/export · csv path
  - POST  /api/v1/admin/crm/leads/{id}/regenerate-analysis · cache + fallback

SQLite + FastAPI TestClient · no Postgres needed. Calls to Claude are
monkey-patched via crm_service._invoke_ai_analysis to deterministic returns.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ----------------------------------------------------------------------------
# Fixtures (mirror test_gh_team_roles.app_with_db)
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


def _make_user(SessionLocal, *, email, role, school_id=None, password="testpass123", **extra):
    from app.db.models import User
    from app.api.v1.auth import get_password_hash
    db = SessionLocal()
    u = User(
        email=email,
        hashed_password=get_password_hash(password),
        name=email.split("@")[0],
        role=role,
        school_id=school_id,
        **extra,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return uid


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


def _make_program(SessionLocal, **fields):
    from app.db.models import Program
    db = SessionLocal()
    defaults = dict(
        program_id="prog-test-1",
        name="Test Program",
        slug="test-program",
        country="Estados Unidos",
        institution="Test U",
        type="pregrado",
        duration_months=24,
        cost_total=20000,
        currency="USD",
        budget_tier="medium",
        active=True,
    )
    defaults.update(fields)
    p = Program(**defaults)
    db.add(p)
    db.commit()
    db.refresh(p)
    pid = p.id
    db.close()
    return pid


def _login(client, email, password="testpass123"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _bump_user_signals(SessionLocal, user_id, *, score_target):
    """Mutates the user record + creates a journey session to raise score.

    score_target='hot'  → score >= 70 (creates completed session + tests + profile)
    score_target='warm' → score ~ 40 (partial signals)
    score_target='cold' → no signals (score stays 0)
    """
    from app.db.models import (
        ConsolidatedProfileCache,
        Session as JourneySession,
        User,
        VocationalTestResult,
    )
    from datetime import datetime as _dt
    db = SessionLocal()
    u = db.query(User).filter(User.id == user_id).first()
    if score_target == "hot":
        u.budget_band = "alto"
        u.preferred_countries = ["Estados Unidos", "Canadá"]
        u.english_cefr_level = "B2"
        u.gh_contact_status = "pending"
        u.gh_contact_requested_at = _dt.utcnow()
        # Journey completed (30 pts) + 4 tests (20 pts) + profile (15 pts)
        sess = JourneySession(user_id=u.id, is_completed=True, completed_steps=list(range(12)))
        db.add(sess)
        db.flush()
        for i in range(4):
            db.add(
                VocationalTestResult(
                    user_id=u.id,
                    test_id=f"test_{i}",
                    answers={},
                    scores={},
                )
            )
        db.add(
            ConsolidatedProfileCache(
                user_id=u.id,
                profile_hash="hash",
                profile_data={"summary": "test", "interests": ["a"]},
            )
        )
    elif score_target == "warm":
        u.budget_band = "medio"
        u.preferred_countries = ["Estados Unidos"]
    db.commit()
    db.close()


# ============================================================================
# Auth gates
# ============================================================================


def test_crm_leads_requires_super_or_commercial(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    _make_user(SessionLocal, email="adv@gh.com", role=UserRole.GH_ADVISOR)
    _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)
    _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)

    with TestClient(app) as client:
        # gh_advisor → 403
        token = _login(client, "adv@gh.com")
        r = client.get("/api/v1/admin/crm/leads", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, r.text

        # super_admin → 200
        token = _login(client, "sa@gh.com")
        r = client.get("/api/v1/admin/crm/leads", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text

        # gh_commercial → 200
        token = _login(client, "com@gh.com")
        r = client.get("/api/v1/admin/crm/leads", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text


def test_crm_leads_blocks_school_admin(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    school_id = _make_school(SessionLocal)
    _make_user(SessionLocal, email="adm@school.com", role=UserRole.SCHOOL_ADMIN, school_id=school_id)

    with TestClient(app) as client:
        token = _login(client, "adm@school.com")
        r = client.get("/api/v1/admin/crm/leads", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403


# ============================================================================
# Origin filter
# ============================================================================


def test_origin_filter_grasshopper_vs_school_radar(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    school_id = _make_school(SessionLocal)

    # B2C (own lead · school_id None)
    b2c_id = _make_user(SessionLocal, email="b2c@gh.com", role=UserRole.STUDENT)
    _bump_user_signals(SessionLocal, b2c_id, score_target="hot")

    # B2B with high signals → school_radar (gh_contact_status pending)
    b2b_high_id = _make_user(
        SessionLocal, email="b2b.high@school.com", role=UserRole.STUDENT, school_id=school_id
    )
    _bump_user_signals(SessionLocal, b2b_high_id, score_target="hot")

    # B2B with low signals → school_radar but score < 60 → hidden
    _make_user(
        SessionLocal, email="b2b.low@school.com", role=UserRole.STUDENT, school_id=school_id
    )

    _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)

    with TestClient(app) as client:
        token = _login(client, "sa@gh.com")
        H = {"Authorization": f"Bearer {token}"}

        # All
        r = client.get("/api/v1/admin/crm/leads", headers=H)
        assert r.status_code == 200
        items = r.json()["items"]
        emails = {i["email"] for i in items}
        # b2c hot + b2b.high hot are visible; b2b.low (cold) is hidden because school_radar < 60
        assert "b2c@gh.com" in emails
        assert "b2b.high@school.com" in emails
        assert "b2b.low@school.com" not in emails

        # Filter origin=grasshopper → only b2c
        r = client.get("/api/v1/admin/crm/leads?origin=grasshopper", headers=H)
        assert r.status_code == 200
        emails = {i["email"] for i in r.json()["items"]}
        assert "b2c@gh.com" in emails
        assert "b2b.high@school.com" not in emails

        # Filter origin=school_radar → only b2b.high (b2c excluded)
        r = client.get("/api/v1/admin/crm/leads?origin=school_radar", headers=H)
        assert r.status_code == 200
        emails = {i["email"] for i in r.json()["items"]}
        assert "b2b.high@school.com" in emails
        assert "b2c@gh.com" not in emails


# ============================================================================
# Score band filter
# ============================================================================


def test_score_band_filter_hot(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    hot_id = _make_user(SessionLocal, email="hot@gh.com", role=UserRole.STUDENT)
    _bump_user_signals(SessionLocal, hot_id, score_target="hot")
    _make_user(SessionLocal, email="cold@gh.com", role=UserRole.STUDENT)
    _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)

    with TestClient(app) as client:
        token = _login(client, "sa@gh.com")
        H = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/v1/admin/crm/leads?score_band=hot", headers=H)
        assert r.status_code == 200
        emails = [i["email"] for i in r.json()["items"]]
        assert "hot@gh.com" in emails
        assert "cold@gh.com" not in emails


# ============================================================================
# Detail · ownership gate
# ============================================================================


def test_detail_ownership_gate_for_gh_commercial(app_with_db):
    """A gh_commercial CANNOT see a school student that did NOT opt-in
    to contact AND has score < SCHOOL_RADAR_MIN_SCORE."""
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    school_id = _make_school(SessionLocal)
    cold_school_id = _make_user(
        SessionLocal,
        email="b2b.cold@school.com",
        role=UserRole.STUDENT,
        school_id=school_id,
    )
    _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)
    _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)

    with TestClient(app) as client:
        # commercial · ownership gate triggers · 403
        token = _login(client, "com@gh.com")
        r = client.get(
            f"/api/v1/admin/crm/leads/{cold_school_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403, r.text

        # super_admin · unrestricted · 200
        token = _login(client, "sa@gh.com")
        r = client.get(
            f"/api/v1/admin/crm/leads/{cold_school_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text


def test_detail_ownership_gate_passes_when_student_opted_in(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    school_id = _make_school(SessionLocal)
    student_id = _make_user(
        SessionLocal,
        email="b2b.opted@school.com",
        role=UserRole.STUDENT,
        school_id=school_id,
    )
    # mark student as having requested contact (open) → commercial CAN see
    from app.db.models import User
    from datetime import datetime as _dt
    db = SessionLocal()
    u = db.query(User).filter(User.id == student_id).first()
    u.gh_contact_status = "pending"
    u.gh_contact_requested_at = _dt.utcnow()
    db.commit()
    db.close()

    _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)
    with TestClient(app) as client:
        token = _login(client, "com@gh.com")
        r = client.get(
            f"/api/v1/admin/crm/leads/{student_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text


# ============================================================================
# Detail response shape
# ============================================================================


def test_detail_response_shape_and_score_breakdown(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    uid = _make_user(SessionLocal, email="lead@gh.com", role=UserRole.STUDENT)
    _bump_user_signals(SessionLocal, uid, score_target="hot")
    _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)

    with TestClient(app) as client:
        token = _login(client, "sa@gh.com")
        r = client.get(
            f"/api/v1/admin/crm/leads/{uid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # required keys
        for k in (
            "user_id",
            "origin",
            "score_breakdown",
            "demographics",
            "journey",
            "activity_log",
        ):
            assert k in body, f"missing {k}"
        # 7 signals
        assert len(body["score_breakdown"]["signals"]) == 7
        assert body["score_breakdown"]["score"] >= 0
        # journal metadata only · no content key
        assert "journal" in body["journey"]
        assert "total_entries" in body["journey"]["journal"]
        assert "entries_by_type" in body["journey"]["journal"]
        # ai_analysis is None on first read (cache empty)
        assert body["ai_analysis"] is None


# ============================================================================
# PATCH pipeline status · audit + bitrix log
# ============================================================================


def test_patch_pipeline_status_persists_and_logs(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole, AuditLog, BitrixSyncLog
    uid = _make_user(SessionLocal, email="leadpatch@gh.com", role=UserRole.STUDENT)
    _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)

    with TestClient(app) as client:
        token = _login(client, "sa@gh.com")
        H = {"Authorization": f"Bearer {token}"}
        r = client.patch(
            f"/api/v1/admin/crm/leads/{uid}/status",
            headers=H,
            json={"status": "contacted", "note": "Llamada hecha"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pipeline_status"] == "contacted"
        assert body["pipeline_status_at"] is not None

    db = SessionLocal()
    audits = db.query(AuditLog).filter(AuditLog.action == "crm.pipeline_status_change").all()
    assert len(audits) == 1
    assert audits[0].payload["new"] == "contacted"

    bitrix_rows = db.query(BitrixSyncLog).filter(BitrixSyncLog.action == "pipeline.contacted").all()
    assert len(bitrix_rows) == 1
    assert bitrix_rows[0].provider == "stub"
    db.close()


def test_patch_pipeline_status_validates_enum(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    uid = _make_user(SessionLocal, email="lead@gh.com", role=UserRole.STUDENT)
    _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)

    with TestClient(app) as client:
        token = _login(client, "sa@gh.com")
        H = {"Authorization": f"Bearer {token}"}
        r = client.patch(
            f"/api/v1/admin/crm/leads/{uid}/status",
            headers=H,
            json={"status": "not_a_real_status"},
        )
        assert r.status_code == 422


# ============================================================================
# KPIs
# ============================================================================


def test_kpis_shape(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    uid = _make_user(SessionLocal, email="hot@gh.com", role=UserRole.STUDENT)
    _bump_user_signals(SessionLocal, uid, score_target="hot")
    _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)

    with TestClient(app) as client:
        token = _login(client, "sa@gh.com")
        r = client.get(
            "/api/v1/admin/crm/kpis", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for k in (
            "total_leads",
            "hot_leads",
            "pending_action",
            "converted_last_30d",
            "by_origin",
            "by_band",
        ):
            assert k in body
        assert body["total_leads"] >= 1
        assert body["hot_leads"] >= 1


# ============================================================================
# Export CSV
# ============================================================================


def test_export_csv_returns_attachment(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    _make_user(SessionLocal, email="x@gh.com", role=UserRole.STUDENT)
    _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)

    with TestClient(app) as client:
        token = _login(client, "sa@gh.com")
        r = client.get(
            "/api/v1/admin/crm/leads/export?format=csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
        body = r.text
        # header row exists
        assert "user_id" in body.splitlines()[0]


# ============================================================================
# Regenerate AI analysis · stubbed Claude → fallback path is exercised
# (no network call)
# ============================================================================


def test_regenerate_ai_analysis_uses_fallback_when_claude_off(app_with_db, monkeypatch):
    """When ANTHROPIC_API_KEY is not configured, the call to Claude is
    stubbed and the fallback (deterministic template) is returned. The cache
    is still populated so a second call is fast."""
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    uid = _make_user(SessionLocal, email="lead.ai@gh.com", role=UserRole.STUDENT)
    _bump_user_signals(SessionLocal, uid, score_target="hot")
    _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)
    _make_program(SessionLocal, country="Estados Unidos", budget_tier="medium")

    # Force Claude calls to fail (simulate offline / fallback path).
    # Fase C2: el CRM usa call_claude_with_meta → (None, metadata) en fallo.
    monkeypatch.setattr(
        "app.services.crm_service.call_claude_with_meta",
        lambda *a, **kw: (None, {"model": "claude-sonnet-4-6", "error_kind": "connection"}),
    )

    with TestClient(app) as client:
        token = _login(client, "sa@gh.com")
        H = {"Authorization": f"Bearer {token}"}
        r = client.post(
            f"/api/v1/admin/crm/leads/{uid}/regenerate-analysis",
            headers=H,
            json={"force": True},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_fallback"] is True
        assert body["rationale"]
        assert isinstance(body["program_matches"], list)
        assert isinstance(body["next_actions"], list)
        # Cache populated · subsequent GET detail returns the analysis
        r2 = client.get(
            f"/api/v1/admin/crm/leads/{uid}", headers=H
        )
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["ai_analysis"] is not None
        assert body2["ai_analysis"]["rationale"] == body["rationale"]
