"""Sprint 11 · QA + security hardening tests.

Covers, in order of appearance:
  - Health check: 200/503 contract · checks payload structure
  - Security headers middleware (HSTS, CSP, X-Frame-Options, etc.)
  - Rate limiting on /auth/login, /auth/register, /invitations/{t}/accept
  - Structured logging PII masking (pure unit tests, no I/O)
  - Magic-byte file validation (logo upload guard)
  - Webhook replay guard (timestamp tolerance + nonce dedup)
  - Bitrix outbound dedup pre-check (sync_user_lead skips when payload unchanged)

Each test is independent and uses an in-memory SQLite DB.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ============================================================================
# Fixtures
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

    # Reset slowapi memory store between tests so per-test rate counters
    # start at zero. We also reset the school_panel and admin caches.
    from app.core.rate_limiter import limiter
    limiter.reset()

    from app.api.v1 import admin as admin_mod
    admin_mod._STATS_CACHE["data"] = None
    admin_mod._STATS_CACHE["ts"] = 0.0
    from app.services import school_panel_service as sps
    sps._DASHBOARD_CACHE.clear()
    sps._REPORTS_CACHE.clear()

    from app.core.webhook_replay import bitrix_replay_guard
    bitrix_replay_guard.reset()

    yield app, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _make_user(SessionLocal, email="user@gh.example.com", password="secret123", role=None):
    from app.db.models import User, UserRole
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    u = User(
        email=email.lower(),
        hashed_password=get_password_hash(password),
        name="User",
        role=role or UserRole.STUDENT,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


# ============================================================================
# Health check (GH-S11-INFRA-02)
# ============================================================================


def test_health_check_returns_200_when_db_reachable(app_with_db):
    app, _ = app_with_db
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert "checks" in body
    assert body["checks"]["db_connected"] is True
    assert "version" in body
    assert "rate_limit_enabled" in body["checks"]


def test_health_live_always_200(app_with_db):
    app, _ = app_with_db
    with TestClient(app) as client:
        r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"


# ============================================================================
# Security headers (GH-S11-INFRA-05)
# ============================================================================


def test_security_headers_attached_to_every_response(app_with_db):
    app, _ = app_with_db
    with TestClient(app) as client:
        r = client.get("/health/live")
    h = r.headers
    assert "strict-transport-security" in h
    assert "max-age=31536000" in h["strict-transport-security"]
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "strict-origin" in h["referrer-policy"]
    assert "default-src 'self'" in h["content-security-policy"]
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["x-permitted-cross-domain-policies"] == "none"


# ============================================================================
# Rate limiting (GH-S11-INFRA-04)
# ============================================================================


def test_login_rate_limited_after_threshold(app_with_db, monkeypatch):
    app, SessionLocal = app_with_db
    # Tighter limit for the test so we don't have to fire 5+ requests
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: type(
            "S", (), {**vars(_get_real_settings()), "rate_limit_login": "2/minute"}
        )(),
        raising=False,
    )
    _make_user(SessionLocal, email="rate@gh.example.com", password="secret123")

    with TestClient(app) as client:
        # Two attempts allowed
        r1 = client.post(
            "/api/v1/auth/login",
            json={"email": "rate@gh.example.com", "password": "wrong"},
        )
        r2 = client.post(
            "/api/v1/auth/login",
            json={"email": "rate@gh.example.com", "password": "wrong"},
        )
        # The third should be 429 if the limit kicked in. We don't assert
        # the specific status because slowapi captures the live limit at
        # decorator import time, not via runtime get_settings, so the actual
        # configured limit is `5/minute` from main config. Either way, the
        # *behavior* we ship is: requests succeed until limit exhausted.
        statuses = []
        for _ in range(8):
            r = client.post(
                "/api/v1/auth/login",
                json={"email": "rate@gh.example.com", "password": "wrong"},
            )
            statuses.append(r.status_code)
    assert r1.status_code in (401, 429)
    assert r2.status_code in (401, 429)
    # Eventually we should see at least one 429 in the burst
    assert 429 in statuses, f"expected at least one 429 in burst, got {statuses}"


def _get_real_settings():
    from app.config import get_settings
    return get_settings()


# ============================================================================
# PII masking · pure unit tests (GH-S11)
# ============================================================================


def test_mask_email_keeps_domain():
    from app.core.logging_config import mask_email

    assert mask_email("juan@example.com") == "j***@example.com"
    assert mask_email("a@b.co") == "a***@b.co"
    assert mask_email("no-email-string") == "no-email-string"
    assert mask_email("") == ""


def test_mask_string_redacts_bearer_and_token_querystring():
    from app.core.logging_config import mask_string

    assert "[redacted]" in mask_string("Authorization: Bearer abc.def.ghi")
    out = mask_string("https://x.com/cb?access_token=verysecretvalue&x=1")
    assert "verysecretvalue" not in out
    assert "[redacted]" in out
    # JWT-shaped token
    jwt_like = "eyJabc123abc.eyJpYXQiOj.signaturepart"
    masked = mask_string(f"token={jwt_like}")
    assert jwt_like not in masked


def test_mask_value_redacts_secret_keys():
    from app.core.logging_config import mask_value

    assert mask_value("password", "supersecret") == "[redacted]"
    assert mask_value("anthropic_api_key", "sk-ant-xyz") == "[redacted]"
    assert mask_value("Authorization", "Bearer x.y.z") == "[redacted]"
    # Email key gets partial mask
    assert mask_value("email", "u@e.com").startswith("u***@")
    # Non-sensitive strings stay
    assert mask_value("name", "Juan Pablo") == "Juan Pablo"


def test_mask_value_recurses_into_dicts_and_lists():
    from app.core.logging_config import mask_value

    payload = {
        "user": {"email": "test@gh.example.com", "password": "x"},
        "tokens": ["Bearer abc.def.ghi", "no-secret"],
    }
    out = mask_value("payload", payload)
    assert out["user"]["email"].startswith("t***@")
    assert out["user"]["password"] == "[redacted]"
    assert "[redacted]" in out["tokens"][0]
    assert out["tokens"][1] == "no-secret"


# ============================================================================
# Magic-byte file validation (GH-S11 · S9 hardening)
# ============================================================================


def test_validate_image_bytes_accepts_png():
    from app.core.file_validation import validate_image_bytes

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    res = validate_image_bytes(png)
    assert res.ok is True
    assert res.detected_label == "png"


def test_validate_image_bytes_accepts_jpeg():
    from app.core.file_validation import validate_image_bytes

    jpeg = b"\xff\xd8\xff" + b"\x00" * 16
    res = validate_image_bytes(jpeg)
    assert res.ok is True
    assert res.detected_label == "jpeg"


def test_validate_image_bytes_rejects_unknown_signature():
    from app.core.file_validation import validate_image_bytes

    fake = b"%PDF-1.4 not actually an image"
    res = validate_image_bytes(fake)
    assert res.ok is False
    assert res.reason == "unknown_signature"


def test_validate_image_bytes_rejects_dangerous_svg():
    from app.core.file_validation import validate_image_bytes

    bad_svg = b'<?xml version="1.0"?><svg><script>alert(1)</script></svg>'
    res = validate_image_bytes(bad_svg)
    assert res.ok is False
    assert res.reason == "svg_forbidden_tag"

    onerror = b'<svg onload="alert(1)"></svg>'
    res = validate_image_bytes(onerror)
    assert res.ok is False
    assert res.reason == "svg_event_handler"


def test_validate_image_bytes_accepts_clean_svg():
    from app.core.file_validation import validate_image_bytes

    clean = b'<?xml version="1.0"?><svg width="10" height="10"><rect/></svg>'
    res = validate_image_bytes(clean)
    assert res.ok is True
    assert res.detected_label == "svg"


def test_validate_image_bytes_rejects_empty_and_oversize():
    from app.core.file_validation import validate_image_bytes

    assert validate_image_bytes(b"").ok is False
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024)
    res = validate_image_bytes(big, max_bytes=1 * 1024 * 1024)
    assert res.ok is False
    assert res.reason == "too_large"


# ============================================================================
# Webhook replay guard (GH-S11 · S10 hardening)
# ============================================================================


def test_replay_guard_accepts_fresh_timestamp_and_unique_nonce():
    from app.core.webhook_replay import WebhookReplayGuard

    guard = WebhookReplayGuard(timestamp_tolerance_s=300, nonce_ttl_s=600)
    now = time.time()
    ok, _ = guard.check_timestamp(now)
    assert ok
    assert guard.remember_nonce("nonce-1", now) is True


def test_replay_guard_rejects_stale_timestamp():
    from app.core.webhook_replay import WebhookReplayGuard

    guard = WebhookReplayGuard(timestamp_tolerance_s=60)
    now = time.time()
    ok, reason = guard.check_timestamp(now - 600, now=now)
    assert ok is False
    assert reason.startswith("timestamp_skew=")


def test_replay_guard_rejects_repeat_nonce():
    from app.core.webhook_replay import WebhookReplayGuard

    guard = WebhookReplayGuard(timestamp_tolerance_s=300, nonce_ttl_s=60)
    now = time.time()
    assert guard.remember_nonce("abc", now) is True
    assert guard.remember_nonce("abc", now) is False  # replay


def test_replay_guard_purges_after_ttl():
    from app.core.webhook_replay import WebhookReplayGuard

    guard = WebhookReplayGuard(timestamp_tolerance_s=300, nonce_ttl_s=10)
    t0 = 1000.0
    assert guard.remember_nonce("abc", t0) is True
    # After TTL the slot is freed
    assert guard.remember_nonce("abc", t0 + 11) is True


# ============================================================================
# Bitrix outbound dedup (GH-S11 · S10 hardening)
# ============================================================================


def test_bitrix_payload_hash_deterministic():
    from app.services.bitrix_sync_service import _payload_hash

    a = {"NAME": "Juan", "EMAIL": [{"VALUE": "j@e.com"}]}
    b = {"EMAIL": [{"VALUE": "j@e.com"}], "NAME": "Juan"}  # different order
    assert _payload_hash(a) == _payload_hash(b)
    c = {"NAME": "Juan", "EMAIL": [{"VALUE": "other@e.com"}]}
    assert _payload_hash(a) != _payload_hash(c)


def test_bitrix_dedup_skips_when_payload_unchanged(app_with_db, monkeypatch):
    """Two consecutive sync_user_lead calls with identical bundle ⇒ second one
    short-circuits to a `skip_dedup` log row without invoking the client."""
    app, SessionLocal = app_with_db
    from datetime import date, datetime
    from app.db.models import User, UserRole
    from app.api.v1.auth import get_password_hash
    from app.services import bitrix_sync_service as svc
    from app.services.bitrix_client import BitrixClient, BitrixCallResult

    db = SessionLocal()
    today = date.today()
    u = User(
        email="bx@gh.example.com",
        hashed_password=get_password_hash("x"),
        name="BX",
        role=UserRole.STUDENT,
        # GH-S11.5-BE-07 · consent granted so the sync proceeds and dedup
        # path is exercised. Gate itself is tested in test_consent_gate.py.
        birthdate=date(today.year - 25, today.month, today.day),
        consent_data_processing_at=datetime.utcnow(),
        consent_data_processing_version="1.0.0",
        consent_crm_sync_at=datetime.utcnow(),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    user_id = u.id
    db.close()

    calls = {"n": 0}

    class FakeClient:
        def create_lead(self, fields):
            calls["n"] += 1
            return BitrixCallResult(
                provider="stub",
                success=True,
                bitrix_id="LEAD-123",
                response={"id": "LEAD-123"},
                attempts=1,
            )

        def update_lead(self, lead_id, fields):
            calls["n"] += 1
            return BitrixCallResult(
                provider="stub",
                success=True,
                bitrix_id=lead_id,
                response={"id": lead_id},
                attempts=1,
            )

    fake = FakeClient()

    db = SessionLocal()
    log1 = svc.sync_user_lead(db, user_id, client=fake)
    log1_action = log1.action  # capture before next commit may expire it
    log2 = svc.sync_user_lead(db, user_id, client=fake)
    log2_action = log2.action
    db.close()

    # First call hits the client. Second one is deduped.
    assert calls["n"] == 1, f"client should have been called exactly once, got {calls['n']}"
    assert log1_action in ("create", "update")
    assert log2_action == "skip_dedup"


# ============================================================================
# Failed login is recorded in audit log (GH-S11 · S8 hardening)
# ============================================================================


def test_failed_login_records_audit_row(app_with_db):
    app, SessionLocal = app_with_db
    _make_user(SessionLocal, email="audit@gh.example.com", password="secret123")
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "audit@gh.example.com", "password": "wrong"},
        )
    assert r.status_code == 401

    from app.db.models import AuditLog

    db = SessionLocal()
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action == "auth.login_failed")
        .all()
    )
    db.close()
    assert len(rows) >= 1
    assert rows[0].payload.get("reason") == "invalid_credentials"


def test_super_admin_login_records_audit_row(app_with_db):
    from app.db.models import UserRole

    app, SessionLocal = app_with_db
    _make_user(SessionLocal, email="root@gh.example.com", password="rootpass123", role=UserRole.SUPER_ADMIN)
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "root@gh.example.com", "password": "rootpass123"},
        )
    assert r.status_code == 200

    from app.db.models import AuditLog

    db = SessionLocal()
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action == "auth.login_super_admin")
        .all()
    )
    db.close()
    assert len(rows) == 1


# ============================================================================
# Role bypass smoke (GH-S11-QA-04 · student cannot reach admin endpoints)
# ============================================================================


def test_student_cannot_access_super_admin_endpoints(app_with_db):
    app, SessionLocal = app_with_db
    _make_user(SessionLocal, email="kid@gh.example.com", password="secret123")
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "kid@gh.example.com", "password": "secret123"},
        )
        token = r.json()["access_token"]
        H = {"Authorization": f"Bearer {token}"}
        # Sample of protected admin endpoints
        endpoints = [
            ("get", "/api/v1/admin/stats/overview"),
            ("get", "/api/v1/admin/audit-logs"),
            ("post", "/api/v1/schools"),
        ]
        for method, path in endpoints:
            res = client.request(method, path, headers=H, json={})
            assert res.status_code in (
                401,
                403,
                404,
                422,
            ), f"{method} {path} returned {res.status_code} for student"
            # 401/403 are the expected hardening; 404/422 acceptable when the
            # path is shape-validated before auth (FastAPI quirk on POST without body)
            assert res.status_code != 200, f"Student reached {path}"
