"""Panel de costos de IA (AICostsPage) · GET /admin/integrations/ai-costs.

El response model tipaba `daily: List[Dict[str, float]]`, pero cada punto
trae `date` como string ("2026-06-10") → ValidationError → 500 en cuanto
`ai_usage_log` tuvo filas. El panel nació ANTES del primer call-site real
de tracking (hop_chat, 2026-06-09), así que el bug quedó dormido y explotó
en prod justo cuando empezó a haber datos que mostrar.

SQLite + TestClient · patrón de tests/test_programs_list_nullable_b042.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta

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


def _super_admin(SessionLocal):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    try:
        u = User(
            email="super.aicosts@grasshopper.dev",
            hashed_password=get_password_hash("testpass123"),
            name="Super",
            role=UserRole.SUPER_ADMIN,
            onboarding_status=OnboardingStatus.NOT_STARTED,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.email, u.id
    finally:
        db.close()


def _seed_usage(SessionLocal, user_id):
    """Filas en 2 días distintos → el timeseries `daily` trae fechas string."""
    from app.db.models import AIUsageLog

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        db.add_all([
            AIUsageLog(
                provider="anthropic", model="claude-sonnet-4-5",
                feature="hop_chat", tokens_input=1000, tokens_output=200,
                cost_usd=0.006, latency_ms=900, user_id=user_id,
                created_at=now - timedelta(days=1),
            ),
            AIUsageLog(
                provider="anthropic", model="claude-sonnet-4-5",
                feature="recommend_programs", tokens_input=4000, tokens_output=900,
                cost_usd=0.025, latency_ms=20000, user_id=user_id,
                created_at=now,
            ),
        ])
        db.commit()
    finally:
        db.close()


def test_ai_costs_200_with_usage_rows(app_with_db):
    app, SessionLocal = app_with_db
    email, user_id = _super_admin(SessionLocal)
    _seed_usage(SessionLocal, user_id)

    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "testpass123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    resp = client.get("/api/v1/admin/integrations/ai-costs?days=7", headers=headers)
    assert resp.status_code == 200, resp.text
    d = resp.json()

    assert d["total_calls"] == 2
    assert d["total_tokens_input"] == 5000
    features = {b["key"] for b in d["by_feature"]}
    assert features == {"hop_chat", "recommend_programs"}

    # El punto del bug: daily trae la fecha como string y cost/calls numéricos
    assert len(d["daily"]) == 2
    for point in d["daily"]:
        assert isinstance(point["date"], str)
        assert isinstance(point["cost_usd"], float)
        assert isinstance(point["calls"], int)

    assert d["top_users"][0]["email"] == email


def test_ai_costs_200_with_empty_log(app_with_db):
    """Sin filas (el estado pre-tracking, donde el bug nunca se veía)."""
    app, SessionLocal = app_with_db
    email, _ = _super_admin(SessionLocal)

    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "testpass123"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    resp = client.get("/api/v1/admin/integrations/ai-costs", headers=headers)
    assert resp.status_code == 200
    d = resp.json()
    assert d["total_calls"] == 0
    assert d["daily"] == []
    assert d["top_users"] == []
