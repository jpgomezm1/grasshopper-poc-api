"""GH-COMMPROD · gh_commercial productivity sprint (2026-05-03).

Covers the new productivity features:
    - Notifications inbox + mark-read + push subscriptions
    - Tasks CRUD + permission gates
    - Lead assignment + handoff flow
    - Tags catalog + lead-tag set
    - Saved searches CRUD
    - Comments + @mention notifications
    - Pipeline stages CRUD + reorder + delete-default-blocked
    - Auto-assign + pipeline rule CRUD
    - Today dashboard structure
    - Activity timeline merge
    - Performance + funnel + benchmarks structure
    - SLA breach evaluation

SQLite + FastAPI TestClient · monkey-patches the rate limiter.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

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


def _make_user(SessionLocal, *, email, role, **extra):
    from app.db.models import User
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    u = User(
        email=email,
        hashed_password=get_password_hash("testpass123"),
        name=email.split("@")[0],
        role=role,
        **extra,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return uid


def _login(client, email, password="testpass123"):
    r = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# Notifications
# ===========================================================================


def test_notifications_inbox_and_mark_read(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    from app.services import notifications_service

    com_uid = _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)

    # Seed 3 notifications
    db = SessionLocal()
    notifications_service.create_notification(
        db, user_id=com_uid, type="lead.assigned", title="N1", body="b1"
    )
    notifications_service.create_notification(
        db, user_id=com_uid, type="task.due_soon", title="N2", body="b2"
    )
    notifications_service.create_notification(
        db, user_id=com_uid, type="lead.sla_breach", title="N3", body="b3"
    )
    db.close()

    with TestClient(app) as client:
        token = _login(client, "com@gh.com")
        r = client.get("/api/v1/notifications/me", headers=_h(token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] == 3
        assert data["unread"] == 3
        assert len(data["items"]) == 3

        first_id = data["items"][0]["id"]
        r = client.patch(
            f"/api/v1/notifications/{first_id}/read", headers=_h(token)
        )
        assert r.status_code == 200
        assert r.json()["unread"] == 2

        r = client.patch("/api/v1/notifications/read-all", headers=_h(token))
        assert r.status_code == 200
        assert r.json()["unread"] == 0

        r = client.get(
            "/api/v1/notifications/me?status=unread", headers=_h(token)
        )
        assert r.status_code == 200
        assert r.json()["total"] == 0


def test_notifications_other_role_only_sees_their_own(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole
    from app.services import notifications_service

    a = _make_user(SessionLocal, email="a@gh.com", role=UserRole.GH_COMMERCIAL)
    b = _make_user(SessionLocal, email="b@gh.com", role=UserRole.GH_COMMERCIAL)

    db = SessionLocal()
    notifications_service.create_notification(
        db, user_id=a, type="lead.assigned", title="forA"
    )
    notifications_service.create_notification(
        db, user_id=b, type="lead.assigned", title="forB"
    )
    db.close()

    with TestClient(app) as client:
        ta = _login(client, "a@gh.com")
        r = client.get("/api/v1/notifications/me", headers=_h(ta))
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["title"] == "forA"


def test_push_subscription_upsert(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)
    with TestClient(app) as client:
        token = _login(client, "com@gh.com")
        body = {
            "endpoint": "https://fcm.example/abc",
            "keys": {"p256dh": "p256-key-data-long", "auth": "auth-key-data-long"},
            "user_agent": "test",
        }
        r = client.post(
            "/api/v1/notifications/me/push-subscriptions",
            json=body,
            headers=_h(token),
        )
        assert r.status_code == 201, r.text
        # Re-upsert idempotent
        r2 = client.post(
            "/api/v1/notifications/me/push-subscriptions",
            json=body,
            headers=_h(token),
        )
        assert r2.status_code == 201
        r3 = client.get(
            "/api/v1/notifications/me/push-subscriptions", headers=_h(token)
        )
        assert r3.status_code == 200
        assert len(r3.json()) == 1


# ===========================================================================
# Tasks
# ===========================================================================


def test_tasks_create_list_patch_delete(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)

    with TestClient(app) as client:
        token = _login(client, "com@gh.com")
        # Create
        r = client.post(
            "/api/v1/tasks",
            json={
                "description": "Llamar a María",
                "priority": "high",
                "due_at": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
            },
            headers=_h(token),
        )
        assert r.status_code == 201, r.text
        task_id = r.json()["id"]
        # List
        r = client.get("/api/v1/tasks", headers=_h(token))
        assert r.status_code == 200
        assert r.json()["total"] == 1
        # Patch (mark done)
        r = client.patch(
            f"/api/v1/tasks/{task_id}", json={"status": "done"}, headers=_h(token)
        )
        assert r.status_code == 200
        assert r.json()["status"] == "done"
        # Delete
        r = client.delete(f"/api/v1/tasks/{task_id}", headers=_h(token))
        assert r.status_code == 204


def test_tasks_forbidden_for_students(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    _make_user(SessionLocal, email="stu@gh.com", role=UserRole.STUDENT)
    with TestClient(app) as client:
        token = _login(client, "stu@gh.com")
        r = client.get("/api/v1/tasks", headers=_h(token))
        assert r.status_code == 403


def test_tasks_other_user_filtered_for_non_super(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    a = _make_user(SessionLocal, email="a@gh.com", role=UserRole.GH_COMMERCIAL)
    b = _make_user(SessionLocal, email="b@gh.com", role=UserRole.GH_COMMERCIAL)

    # Create task for B (impossible for A as gh_commercial · falls back to A)
    with TestClient(app) as client:
        ta = _login(client, "a@gh.com")
        r = client.post(
            "/api/v1/tasks",
            json={
                "description": "Tarea para B",
                "assigned_to_user_id": str(b),
                "priority": "normal",
            },
            headers=_h(ta),
        )
        assert r.status_code == 201
        # Falls back to actor (A)
        assert UUID(r.json()["assigned_to_user_id"]) == a


# ===========================================================================
# Lead assignment + handoff
# ===========================================================================


def test_assign_and_handoff_creates_notifications(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    com1 = _make_user(SessionLocal, email="com1@gh.com", role=UserRole.GH_COMMERCIAL)
    com2 = _make_user(SessionLocal, email="com2@gh.com", role=UserRole.GH_COMMERCIAL)
    sa = _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)
    lead = _make_user(SessionLocal, email="lead@example.com", role=UserRole.STUDENT)

    with TestClient(app) as client:
        sa_token = _login(client, "sa@gh.com")
        # Assign to com1
        r = client.patch(
            f"/api/v1/admin/commercial/leads/{lead}/assign",
            json={"to_user_id": str(com1), "note": "primer touch"},
            headers=_h(sa_token),
        )
        assert r.status_code == 200, r.text
        assert UUID(r.json()["assigned_to_user_id"]) == com1

        # com1 should have a notification
        c1 = _login(client, "com1@gh.com")
        r = client.get("/api/v1/notifications/me", headers=_h(c1))
        assert r.status_code == 200
        types = [n["type"] for n in r.json()["items"]]
        assert "lead.assigned" in types

        # Hand-off to com2
        r = client.patch(
            f"/api/v1/admin/commercial/leads/{lead}/handoff",
            json={"to_user_id": str(com2), "note": "Vacaciones · pásalo"},
            headers=_h(sa_token),
        )
        assert r.status_code == 200, r.text
        assert UUID(r.json()["assigned_to_user_id"]) == com2

        # com2 received notification
        c2 = _login(client, "com2@gh.com")
        r = client.get("/api/v1/notifications/me", headers=_h(c2))
        types = [n["type"] for n in r.json()["items"]]
        assert "lead.assigned" in types


def test_assign_rejects_non_gh_assignee(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    sa = _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)
    student = _make_user(SessionLocal, email="x@gh.com", role=UserRole.STUDENT)
    lead = _make_user(SessionLocal, email="lead@gh.com", role=UserRole.STUDENT)

    with TestClient(app) as client:
        sa_token = _login(client, "sa@gh.com")
        r = client.patch(
            f"/api/v1/admin/commercial/leads/{lead}/assign",
            json={"to_user_id": str(student)},
            headers=_h(sa_token),
        )
        assert r.status_code == 400


# ===========================================================================
# Tags
# ===========================================================================


def test_tags_seed_and_set_per_lead(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole, LeadTag

    com = _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)
    lead = _make_user(SessionLocal, email="lead@gh.com", role=UserRole.STUDENT)
    sa = _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)

    # Insert 2 tags directly (since SQLite doesn't seed via alembic migrations here)
    db = SessionLocal()
    db.add(LeadTag(key="presupuesto-premium", label="Presupuesto premium", color="amber"))
    db.add(LeadTag(key="interes-usa", label="Interés USA", color="blue"))
    db.commit()
    tag_ids = [str(t.id) for t in db.query(LeadTag).all()]
    db.close()

    with TestClient(app) as client:
        c_token = _login(client, "com@gh.com")
        r = client.get("/api/v1/admin/commercial/tags", headers=_h(c_token))
        assert r.status_code == 200
        assert len(r.json()) == 2

        r = client.put(
            f"/api/v1/admin/commercial/leads/{lead}/tags",
            json={"tag_ids": tag_ids},
            headers=_h(c_token),
        )
        assert r.status_code == 200
        assert len(r.json()["tags"]) == 2


# ===========================================================================
# Saved searches
# ===========================================================================


def test_saved_searches_personal(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    a = _make_user(SessionLocal, email="a@gh.com", role=UserRole.GH_COMMERCIAL)
    b = _make_user(SessionLocal, email="b@gh.com", role=UserRole.GH_COMMERCIAL)

    with TestClient(app) as client:
        ta = _login(client, "a@gh.com")
        r = client.post(
            "/api/v1/admin/commercial/saved-searches",
            json={
                "name": "Mis hot",
                "filters": {"score_band": "hot"},
                "pinned": True,
            },
            headers=_h(ta),
        )
        assert r.status_code == 201
        sid = r.json()["id"]

        # B doesn't see A's search
        tb = _login(client, "b@gh.com")
        r = client.get("/api/v1/admin/commercial/saved-searches", headers=_h(tb))
        assert r.status_code == 200
        assert r.json() == []

        # A patches
        r = client.patch(
            f"/api/v1/admin/commercial/saved-searches/{sid}",
            json={"pinned": False},
            headers=_h(ta),
        )
        assert r.status_code == 200
        assert r.json()["pinned"] is False


# ===========================================================================
# Comments + mentions
# ===========================================================================


def test_comments_and_mention_notification(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    com1 = _make_user(SessionLocal, email="c1@gh.com", role=UserRole.GH_COMMERCIAL)
    com2 = _make_user(SessionLocal, email="c2@gh.com", role=UserRole.GH_COMMERCIAL)
    lead = _make_user(SessionLocal, email="lead@gh.com", role=UserRole.STUDENT)

    with TestClient(app) as client:
        t1 = _login(client, "c1@gh.com")
        r = client.post(
            f"/api/v1/admin/commercial/leads/{lead}/comments",
            json={
                "body": "Hey @c2 mira esto",
                "mentions": [str(com2)],
            },
            headers=_h(t1),
        )
        assert r.status_code == 201, r.text

        # com2 receives mention notification
        t2 = _login(client, "c2@gh.com")
        r = client.get("/api/v1/notifications/me", headers=_h(t2))
        types = [n["type"] for n in r.json()["items"]]
        assert "comment.mention" in types

        # List comments
        r = client.get(
            f"/api/v1/admin/commercial/leads/{lead}/comments", headers=_h(t1)
        )
        assert r.status_code == 200
        assert len(r.json()) == 1


# ===========================================================================
# Pipeline stages
# ===========================================================================


def test_pipeline_stages_seed_and_protected(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole, PipelineStage

    sa = _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)

    # Seed 1 default stage manually (alembic seed not triggered in SQLite tests)
    db = SessionLocal()
    db.add(
        PipelineStage(
            key="pending",
            label="Pendiente",
            color="slate",
            order_index=10,
            is_default=True,
        )
    )
    db.commit()
    stage_id = db.query(PipelineStage).first().id
    db.close()

    with TestClient(app) as client:
        sa_token = _login(client, "sa@gh.com")
        r = client.get(
            "/api/v1/admin/commercial/pipeline-stages", headers=_h(sa_token)
        )
        assert r.status_code == 200
        assert len(r.json()) == 1

        # Cannot delete default
        r = client.delete(
            f"/api/v1/admin/commercial/pipeline-stages/{stage_id}",
            headers=_h(sa_token),
        )
        assert r.status_code == 400

        # Create custom + delete OK
        r = client.post(
            "/api/v1/admin/commercial/pipeline-stages",
            json={
                "key": "negociando",
                "label": "Negociando",
                "color": "indigo",
                "order_index": 25,
            },
            headers=_h(sa_token),
        )
        assert r.status_code == 201
        new_id = r.json()["id"]
        r = client.delete(
            f"/api/v1/admin/commercial/pipeline-stages/{new_id}",
            headers=_h(sa_token),
        )
        assert r.status_code == 204


def test_pipeline_stage_403_for_gh_commercial(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)
    with TestClient(app) as client:
        t = _login(client, "com@gh.com")
        r = client.post(
            "/api/v1/admin/commercial/pipeline-stages",
            json={"key": "negociando", "label": "Negociando", "order_index": 99},
            headers=_h(t),
        )
        assert r.status_code == 403


# ===========================================================================
# Today / activity / performance / funnel
# ===========================================================================


def test_today_dashboard_structure(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    com = _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)
    with TestClient(app) as client:
        t = _login(client, "com@gh.com")
        r = client.get("/api/v1/admin/commercial/today", headers=_h(t))
        assert r.status_code == 200, r.text
        body = r.json()
        for key in (
            "kpis",
            "priority_leads",
            "overdue_tasks",
            "upcoming_tasks",
            "sla_breaches",
        ):
            assert key in body
        for k in (
            "leads_assigned_total",
            "leads_pending_action",
            "tasks_today",
            "tasks_overdue",
            "sla_breach_count",
            "week_conversions",
        ):
            assert k in body["kpis"]


def test_performance_and_funnel(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    com = _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)
    with TestClient(app) as client:
        t = _login(client, "com@gh.com")
        r = client.get(
            "/api/v1/admin/commercial/me/performance?period=30d", headers=_h(t)
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["period"] == "30d"
        assert "leads_handled" in body
        assert "timeseries" in body

        r = client.get(
            "/api/v1/admin/commercial/me/funnel?period=30d", headers=_h(t)
        )
        assert r.status_code == 200
        assert len(r.json()["stages"]) == 5


def test_activity_timeline_includes_assignment(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    sa = _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)
    com = _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)
    lead = _make_user(SessionLocal, email="lead@gh.com", role=UserRole.STUDENT)

    with TestClient(app) as client:
        sa_token = _login(client, "sa@gh.com")
        client.patch(
            f"/api/v1/admin/commercial/leads/{lead}/assign",
            json={"to_user_id": str(com)},
            headers=_h(sa_token),
        )
        r = client.get(
            f"/api/v1/admin/commercial/leads/{lead}/activity", headers=_h(sa_token)
        )
        assert r.status_code == 200, r.text
        kinds = [it["kind"] for it in r.json()["items"]]
        assert "assignment" in kinds


def test_benchmarks_response(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    com = _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)
    lead = _make_user(SessionLocal, email="lead@gh.com", role=UserRole.STUDENT)
    with TestClient(app) as client:
        t = _login(client, "com@gh.com")
        r = client.get(
            f"/api/v1/admin/commercial/leads/{lead}/benchmarks", headers=_h(t)
        )
        assert r.status_code == 200, r.text
        for k in ("rank", "percentile", "cohort_size", "my_score"):
            assert k in r.json()


# ===========================================================================
# SLA
# ===========================================================================


def test_sla_evaluator_breach_state():
    from app.db.models import User
    from app.services.sla_service import evaluate

    u = User(email="x@y.com", hashed_password="x")
    u.lead_pipeline_status = "pending"
    u.lead_pipeline_status_at = datetime.utcnow() - timedelta(hours=48)
    info = evaluate(u)
    assert info.state == "breach"

    u.lead_pipeline_status_at = datetime.utcnow() - timedelta(hours=2)
    assert evaluate(u).state == "ok"


def test_sla_sweep_creates_breach_notification(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import User, UserRole
    from app.services import sla_service

    com = _make_user(SessionLocal, email="com@gh.com", role=UserRole.GH_COMMERCIAL)
    lead = _make_user(SessionLocal, email="lead@gh.com", role=UserRole.STUDENT)

    db = SessionLocal()
    u = db.query(User).filter(User.id == lead).first()
    u.assigned_to_user_id = com
    u.assigned_at = datetime.utcnow() - timedelta(hours=48)
    u.lead_pipeline_status = "pending"
    u.lead_pipeline_status_at = datetime.utcnow() - timedelta(hours=48)
    db.commit()

    created = sla_service.evaluate_and_notify_breaches(db)
    db.close()
    assert created >= 1


# ===========================================================================
# Auto-assign + pipeline rules
# ===========================================================================


def test_auto_assign_round_robin(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import User, UserRole, AutoAssignRule
    from app.services import commercial_service

    a = _make_user(SessionLocal, email="a@gh.com", role=UserRole.GH_COMMERCIAL)
    b = _make_user(SessionLocal, email="b@gh.com", role=UserRole.GH_COMMERCIAL)
    lead = _make_user(SessionLocal, email="lead@gh.com", role=UserRole.STUDENT)

    db = SessionLocal()
    db.add(
        AutoAssignRule(
            strategy="round_robin", config={}, is_active=True, priority=100
        )
    )
    db.commit()
    u = db.query(User).filter(User.id == lead).first()
    chosen = commercial_service.auto_assign_lead(db, lead=u)
    db.close()
    assert chosen is not None
    assert chosen.id in (a, b)


def test_pipeline_rules_crud(app_with_db):
    app, SessionLocal = app_with_db
    from app.db.models import UserRole

    sa = _make_user(SessionLocal, email="sa@gh.com", role=UserRole.SUPER_ADMIN)
    with TestClient(app) as client:
        t = _login(client, "sa@gh.com")
        r = client.post(
            "/api/v1/admin/commercial/pipeline-rules",
            json={
                "name": "Test rule",
                "condition": {"score_gte": 80, "status": "pending"},
                "action": {"move_to": "qualified"},
                "is_active": True,
            },
            headers=_h(t),
        )
        assert r.status_code == 201, r.text
        rid = r.json()["id"]

        r = client.patch(
            f"/api/v1/admin/commercial/pipeline-rules/{rid}",
            json={"is_active": False},
            headers=_h(t),
        )
        assert r.status_code == 200
        assert r.json()["is_active"] is False

        r = client.delete(
            f"/api/v1/admin/commercial/pipeline-rules/{rid}", headers=_h(t)
        )
        assert r.status_code == 204
