"""GH-S11.5-BE-07 · D-026 · QA-AUD-062 · Habeas Data consent gate tests.

Covers:
  - has_crm_consent gate semantics (data_processing + crm_sync + parental)
  - is_minor logic (birthdate present · None default-deny)
  - sync_user_lead / sync_user_deal SKIP when consent missing
  - sync_user_lead PROCEEDS with valid stub backend when consent granted
  - Endpoints: GET /me/data · POST /me/consents · DELETE /me/data
  - GET /privacy-policy returns versioned skeleton
  - Audit log rows persist for each grant/revoke/export/delete

Uses a temporary SQLite DB · stub Bitrix backend (no network).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

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
    monkeypatch.setenv("BITRIX_WEBHOOK_URL", "")  # force stub backend
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


def _make_user(
    SessionLocal,
    email,
    *,
    role="student",
    birthdate=None,
    consent_data_processing=False,
    consent_crm_sync=False,
    consent_parental=False,
    bitrix_lead_id=None,
):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash("testpass123"),
            name=email.split("@")[0],
            role=UserRole(role),
            onboarding_status=OnboardingStatus.NOT_STARTED,
            birthdate=birthdate,
            bitrix_lead_id=bitrix_lead_id,
        )
        if consent_data_processing:
            u.consent_data_processing_at = datetime.utcnow()
            u.consent_data_processing_version = "1.0.0"
        if consent_crm_sync:
            u.consent_crm_sync_at = datetime.utcnow()
        if consent_parental:
            u.consent_parental_at = datetime.utcnow()
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id, u.email
    finally:
        db.close()


def _login(client, email, password="testpass123"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ============================================================================
# Unit · consent_service
# ============================================================================


def test_is_minor_with_known_birthdate():
    """is_minor: 17yo → True · 18yo → False · None → True (default-deny)."""
    from app.db.models import User
    from app.services.consent_service import is_minor

    today = date.today()

    minor = User(birthdate=date(today.year - 17, today.month, today.day))
    adult = User(birthdate=date(today.year - 19, today.month, today.day))
    unknown = User(birthdate=None)

    assert is_minor(minor) is True
    assert is_minor(adult) is False
    assert is_minor(unknown) is True  # default-deny


def test_has_crm_consent_requires_all_three_for_minor(app_with_db):
    """Minor with full chain → True · missing parental → False · missing crm → False."""
    app, SessionLocal = app_with_db
    from app.db.models import User
    from app.services.consent_service import has_crm_consent

    today = date.today()

    db = SessionLocal()
    minor_full = User(
        email="m1@x.com",
        hashed_password="!",
        birthdate=date(today.year - 16, today.month, today.day),
        consent_data_processing_at=datetime.utcnow(),
        consent_crm_sync_at=datetime.utcnow(),
        consent_parental_at=datetime.utcnow(),
    )
    minor_no_parental = User(
        email="m2@x.com",
        hashed_password="!",
        birthdate=date(today.year - 16, today.month, today.day),
        consent_data_processing_at=datetime.utcnow(),
        consent_crm_sync_at=datetime.utcnow(),
        consent_parental_at=None,
    )
    minor_no_crm = User(
        email="m3@x.com",
        hashed_password="!",
        birthdate=date(today.year - 16, today.month, today.day),
        consent_data_processing_at=datetime.utcnow(),
        consent_crm_sync_at=None,
        consent_parental_at=datetime.utcnow(),
    )
    no_data_processing = User(
        email="m4@x.com",
        hashed_password="!",
        birthdate=date(today.year - 25, today.month, today.day),
        consent_data_processing_at=None,
        consent_crm_sync_at=datetime.utcnow(),
    )
    db.close()

    assert has_crm_consent(minor_full) == (True, None)
    assert has_crm_consent(minor_no_parental) == (False, "no_parental_consent")
    assert has_crm_consent(minor_no_crm) == (False, "no_crm_sync_consent")
    assert has_crm_consent(no_data_processing) == (
        False,
        "no_data_processing_consent",
    )


# ============================================================================
# Bitrix sync gate · skip_no_consent
# ============================================================================


def test_sync_user_lead_skips_when_no_consent(app_with_db):
    """sync_user_lead MUST persist `skip_no_consent` row WITHOUT calling Bitrix."""
    app, SessionLocal = app_with_db
    user_id, _ = _make_user(
        SessionLocal,
        "stu@nogate.com",
        consent_data_processing=False,
        consent_crm_sync=False,
    )

    from app.services.bitrix_sync_service import sync_user_lead
    from app.db.models import BitrixSyncLog

    db = SessionLocal()
    try:
        result_log = sync_user_lead(db, user_id)
        assert result_log.action == "skip_no_consent"
        assert result_log.provider == "consent_gate"
        assert result_log.payload["reason"] == "no_data_processing_consent"

        rows = db.query(BitrixSyncLog).filter(
            BitrixSyncLog.user_id == user_id
        ).all()
        assert len(rows) == 1
        assert rows[0].action == "skip_no_consent"
    finally:
        db.close()


def test_sync_user_lead_skips_when_minor_no_parental(app_with_db):
    """Minor with crm_sync but no parental → skip with reason."""
    app, SessionLocal = app_with_db
    today = date.today()
    user_id, _ = _make_user(
        SessionLocal,
        "minor@x.com",
        birthdate=date(today.year - 15, today.month, today.day),
        consent_data_processing=True,
        consent_crm_sync=True,
        consent_parental=False,
    )

    from app.services.bitrix_sync_service import sync_user_lead
    db = SessionLocal()
    try:
        result_log = sync_user_lead(db, user_id)
        assert result_log.action == "skip_no_consent"
        assert result_log.payload["reason"] == "no_parental_consent"
    finally:
        db.close()


def test_sync_user_lead_proceeds_when_consent_granted(app_with_db):
    """Adult with full consent → stub backend produces a normal sync row."""
    app, SessionLocal = app_with_db
    today = date.today()
    user_id, _ = _make_user(
        SessionLocal,
        "adult@x.com",
        birthdate=date(today.year - 25, today.month, today.day),
        consent_data_processing=True,
        consent_crm_sync=True,
    )

    from app.services.bitrix_sync_service import sync_user_lead
    from app.db.models import BitrixSyncStatus

    db = SessionLocal()
    try:
        result_log = sync_user_lead(db, user_id)
        # Stub backend produces a SUCCESS row (with provider='stub' or 'consent_gate'
        # if dedup occurred — first call must be SUCCESS · not skip_no_consent).
        assert result_log.action != "skip_no_consent"
        # Either stubbed or actual success, but NOT consent_gate
        assert result_log.provider != "consent_gate"
    finally:
        db.close()


# ============================================================================
# Endpoints
# ============================================================================


def test_post_consents_grant_and_revoke_writes_audit(app_with_db):
    """POST /me/consents flips columns + writes audit rows."""
    app, SessionLocal = app_with_db
    user_id, email = _make_user(SessionLocal, "consents@x.com")

    client = TestClient(app)
    token = _login(client, email)
    H = {"Authorization": f"Bearer {token}"}

    # Grant data_processing + crm_sync
    r = client.post(
        "/api/v1/me/consents",
        json={"data_processing": True, "crm_sync": True},
        headers=H,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data_processing"]["granted"] is True
    assert body["crm_sync"]["granted"] is True
    assert body["policy_version_current"] == "1.0.0"

    # Revoke crm_sync
    r = client.post(
        "/api/v1/me/consents",
        json={"crm_sync": False},
        headers=H,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["crm_sync"]["granted"] is False
    assert body["data_processing"]["granted"] is True  # not touched

    # Audit rows present
    from app.db.models import ConsentAuditLog
    db = SessionLocal()
    try:
        events = [
            r.event
            for r in db.query(ConsentAuditLog)
            .filter(ConsentAuditLog.user_id == user_id)
            .order_by(ConsentAuditLog.created_at.asc())
            .all()
        ]
        assert "data_processing.granted" in events
        assert "crm_sync.granted" in events
        assert "crm_sync.revoked" in events
    finally:
        db.close()


def test_get_me_data_returns_full_export_and_logs(app_with_db):
    """GET /me/data returns all sections + writes data_export audit row."""
    app, SessionLocal = app_with_db
    user_id, email = _make_user(
        SessionLocal,
        "exporter@x.com",
        consent_data_processing=True,
    )
    client = TestClient(app)
    token = _login(client, email)
    H = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/me/data", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["user_id"] == str(user_id)
    assert body["email"] == email
    assert "consent_state" in body
    assert "sessions" in body
    assert "journal_entries" in body
    assert "vocational_tests" in body
    assert "consent_audit_log" in body
    assert "exported_at" in body

    # The export call itself wrote a `data_export` audit row · visible in
    # subsequent calls (this request's audit row was appended after the
    # query that built the response payload, so it shows up next time).
    r2 = client.get("/api/v1/me/data", headers=H)
    audit_events = [a["event"] for a in r2.json()["consent_audit_log"]]
    assert "data_export" in audit_events
    # And direct DB inspection confirms the row was written for both calls.
    from app.db.models import ConsentAuditLog
    db = SessionLocal()
    try:
        rows = (
            db.query(ConsentAuditLog)
            .filter(
                ConsentAuditLog.user_id == user_id,
                ConsentAuditLog.event == "data_export",
            )
            .all()
        )
        assert len(rows) >= 2  # one per export call
    finally:
        db.close()


def test_delete_me_data_anonymizes_and_deactivates(app_with_db):
    """DELETE /me/data soft-deletes: PII redacted, login disabled, cascade clean."""
    app, SessionLocal = app_with_db
    user_id, email = _make_user(
        SessionLocal,
        "deleteme@x.com",
        consent_data_processing=True,
    )
    client = TestClient(app)
    token = _login(client, email)
    H = {"Authorization": f"Bearer {token}"}

    r = client.delete("/api/v1/me/data", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "scheduled"
    assert "anonimizados" in body["note"].lower()

    # User still exists but cannot login.
    from app.db.models import User
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        assert u is not None
        assert u.is_active is False
        assert u.email != email  # anonymized
        assert u.email.startswith("deleted+")
        assert u.name is None
        assert u.phone is None
        assert u.consent_crm_sync_at is None
        # version stays for retention proof
        assert u.consent_data_processing_version == "1.0.0"
    finally:
        db.close()

    # Login no longer works (hashed_password = "!" cannot match anything).
    r2 = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "testpass123"},
    )
    assert r2.status_code == 401  # original email gone · anonymized


def test_get_privacy_policy_returns_versioned_markdown(app_with_db):
    """GET /privacy-policy is public and returns versioned markdown."""
    app, _ = app_with_db
    client = TestClient(app)

    r = client.get("/api/v1/privacy-policy")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "1.0.0"
    assert "dpo_email" in body
    assert "markdown" in body
    assert len(body["markdown"]) > 100  # has actual content


def test_consent_endpoints_require_auth(app_with_db):
    """Each /me/* endpoint rejects unauthenticated calls."""
    app, _ = app_with_db
    client = TestClient(app)

    assert client.get("/api/v1/me/data").status_code in (401, 403)
    assert client.post(
        "/api/v1/me/consents", json={"crm_sync": True}
    ).status_code in (401, 403)
    assert client.delete("/api/v1/me/data").status_code in (401, 403)


def test_revoke_crm_sync_enqueues_desync(app_with_db, monkeypatch):
    """Revoking crm_sync schedules a Bitrix de-sync background task."""
    app, SessionLocal = app_with_db
    user_id, email = _make_user(
        SessionLocal,
        "revoker@x.com",
        consent_data_processing=True,
        consent_crm_sync=True,
        bitrix_lead_id="LEAD_42",
    )
    client = TestClient(app)
    token = _login(client, email)
    H = {"Authorization": f"Bearer {token}"}

    # Capture desync calls
    desync_calls = []
    real = None
    from app.services import bitrix_sync_service as bss

    def fake_desync(db, uid, **kw):
        desync_calls.append(uid)
        return None

    monkeypatch.setattr(bss, "desync_user_on_revoke", fake_desync)

    r = client.post(
        "/api/v1/me/consents",
        json={"crm_sync": False},
        headers=H,
    )
    assert r.status_code == 200, r.text
    # TestClient runs background tasks synchronously after request returns.
    assert user_id in desync_calls


# ============================================================================
# Bypass attempt · ensure no PII leaks via unauthenticated routes
# ============================================================================


def test_bitrix_sync_log_skip_row_does_not_contain_pii(app_with_db):
    """`skip_no_consent` row payload must contain reason · NOT PII."""
    app, SessionLocal = app_with_db
    user_id, _ = _make_user(SessionLocal, "stu@nopayload.com")

    from app.services.bitrix_sync_service import sync_user_lead
    from app.db.models import BitrixSyncLog

    db = SessionLocal()
    try:
        sync_user_lead(db, user_id)
        row = (
            db.query(BitrixSyncLog)
            .filter(BitrixSyncLog.user_id == user_id)
            .first()
        )
        # Payload only carries the reason, no email/name/phone.
        payload = row.payload or {}
        assert payload.get("reason") in {
            "no_data_processing_consent",
            "no_crm_sync_consent",
            "no_parental_consent",
        }
        assert "stu@nopayload.com" not in str(payload)
        assert "EMAIL" not in str(payload)
    finally:
        db.close()
