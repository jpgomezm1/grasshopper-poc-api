"""GH-S11.5-BE-04 · accept_invitation takeover protection tests.

Cubre QA-AUD-031, QA-AUD-032 y QA-AUD-010:

  1. Invitacion a email nuevo + user anónimo  → crea cuenta (200)
  2. Invitacion a email existente + user autenticado como ese email → asocia (200, no cambia pw)
  3. Invitacion a email existente + user autenticado como OTRO email → 403
  4. Invitacion a email existente + user anónimo → 401
  5. Token de invitacion expirado → 410 Gone
  6. Cuenta existente con rol superior a la invitacion → 409 cross-role
  7. Cuenta existente ya vinculada a otro colegio → 409 cross-school
  8. Cuenta existente inactiva (ghost row) + usuario anónimo → permite accept (cuenta no establecida)

Nota: los tests 2-4 verifican el comportamiento crítico de seguridad.
El test 2 también valida que la contraseña del propietario NO es reemplazada.
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
# Fixtures
# ============================================================================


@pytest.fixture()
def app_with_db(monkeypatch):
    """SQLite in-memory app fixture — mismo patrón que test_sprint9."""
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

    # Limpiar caches entre tests
    from app.api.v1 import admin as admin_mod

    admin_mod._STATS_CACHE["data"] = None
    admin_mod._STATS_CACHE["ts"] = 0.0
    from app.services import school_panel_service as sps

    sps._DASHBOARD_CACHE.clear()
    sps._REPORTS_CACHE.clear()

    # Reset rate limiter
    from app.core.rate_limiter import limiter as gh_limiter

    gh_limiter.reset()

    yield app, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ============================================================================
# Helpers
# ============================================================================


def _login(client, email, password):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _make_super(SessionLocal, email="root@gh.example.com"):
    from app.api.v1.auth import get_password_hash
    from app.db.models import User, UserRole

    db = SessionLocal()
    u = User(
        email=email,
        hashed_password=get_password_hash("rootpass123"),
        name="Root",
        role=UserRole.SUPER_ADMIN,
    )
    db.add(u)
    db.commit()
    db.close()
    return u


def _make_school(client, super_token, name, slug, seats=50):
    H = {"Authorization": f"Bearer {super_token}"}
    r = client.post("/api/v1/schools", json={"name": name, "slug": slug}, headers=H)
    assert r.status_code == 201, r.text
    school_id = r.json()["id"]
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


def _make_school_admin(SessionLocal, school_id, email):
    from app.api.v1.auth import get_password_hash
    from app.db.models import OnboardingStatus, User, UserRole

    db = SessionLocal()
    u = User(
        email=email,
        hashed_password=get_password_hash("adminpass123"),
        name=email.split("@")[0],
        role=UserRole.SCHOOL_ADMIN,
        school_id=UUID(str(school_id)),
        onboarding_status=OnboardingStatus.COMPLETED,
    )
    db.add(u)
    db.commit()
    db.close()
    return u


def _make_existing_user(SessionLocal, email, role="student", school_id=None, is_active=True, with_password=True):
    """Crea un user existente con o sin password (para simular ghost row)."""
    from app.api.v1.auth import get_password_hash
    from app.db.models import OnboardingStatus, User, UserRole

    db = SessionLocal()
    pw = get_password_hash("existingpass123") if with_password else None
    u = User(
        email=email,
        hashed_password=pw if pw else "placeholder",
        name=email.split("@")[0],
        role=UserRole(role),
        school_id=UUID(str(school_id)) if school_id else None,
        onboarding_status=OnboardingStatus.COMPLETED,
        is_active=is_active,
    )
    if not with_password:
        # Simular ghost row: has_password = False se logra poniendo hashed_password a None
        # El modelo tiene nullable=False en DB, pero en SQLite en memoria no aplica estrictamente.
        # Workaround: setear directamente después de crear
        u.hashed_password = None  # type: ignore[assignment]
    db.add(u)
    db.commit()
    user_id = u.id
    user_email = u.email
    db.close()

    class _Handle:
        pass

    h = _Handle()
    h.id = user_id
    h.email = user_email
    return h


def _create_invitation(client, admin_token, invited_email, role="student"):
    """Crea una invitación como school_admin y retorna el token de invitación."""
    H = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/school/me/invitations",
        json={"email": invited_email, "role": role},
        headers=H,
    )
    assert r.status_code == 201, r.text
    inv = r.json()
    accept_url = inv["accept_url"]
    assert accept_url
    invite_token = accept_url.rsplit("/", 1)[-1]
    return invite_token


# ============================================================================
# Tests principales
# ============================================================================


def test_accept_new_email_anonymous_creates_account(app_with_db):
    """Caso 1: email nuevo + usuario anónimo → crea cuenta correctamente (200)."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school_id = _make_school(client, super_token, "NewEmailSchool", "ne-school")
    _make_school_admin(SessionLocal, school_id, "admin@ne-school.com")

    admin_token = _login(client, "admin@ne-school.com", "adminpass123")
    invite_token = _create_invitation(client, admin_token, "newcomer@test.com", role="student")

    # Sin autenticación (anónimo), email nunca registrado
    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "NewPass123!", "name": "Newcomer"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "student"
    assert body["email"] == "newcomer@test.com"
    assert UUID(body["school_id"]) == UUID(school_id)
    assert "access_token" in body


def test_accept_existing_email_authenticated_as_owner_links_account(app_with_db):
    """Caso 2: email existente + user autenticado como ESE email → asocia (200).

    Verifica también que la contraseña del usuario NO es reemplazada.
    La verificación de contraseña se hace directamente en la DB (evita acumular
    intentos de login y triggear el rate limiter).
    """
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school_id = _make_school(client, super_token, "LinkSchool", "link-school")
    _make_school_admin(SessionLocal, school_id, "admin@link-school.com")

    # Crear usuario existente sin colegio
    _make_existing_user(SessionLocal, "victim@test.com", school_id=None)

    admin_token = _login(client, "admin@link-school.com", "adminpass123")
    invite_token = _create_invitation(client, admin_token, "victim@test.com", role="student")

    # El usuario legítimo se autentica primero con su contraseña original
    victim_token = _login(client, "victim@test.com", "existingpass123")

    # Capturar el hash de contraseña ANTES del accept para comparar después
    from app.api.v1.auth import verify_password
    from app.db.models import User

    db = SessionLocal()
    user_before = db.query(User).filter(User.email == "victim@test.com").first()
    pw_hash_before = user_before.hashed_password
    db.close()

    # Acepta autenticado como sí mismo
    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "AttackerNewPass1!", "name": "Victim"},
        headers={"Authorization": f"Bearer {victim_token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "victim@test.com"
    assert UUID(body["school_id"]) == UUID(school_id)

    # Verificar directamente en DB que el hashed_password NO cambió
    db = SessionLocal()
    user_after = db.query(User).filter(User.email == "victim@test.com").first()
    pw_hash_after = user_after.hashed_password
    db.close()

    assert pw_hash_after == pw_hash_before, (
        "El hashed_password no debe cambiar al aceptar una invitación como cuenta establecida. "
        "Si cambió, el takeover de contraseña no fue mitigado."
    )

    # Verificar que la contraseña original todavía es válida contra el hash guardado
    assert verify_password("existingpass123", pw_hash_after), (
        "La contraseña original debe ser válida contra el hash almacenado."
    )

    # Verificar que la contraseña del payload del atacante NO es válida contra el hash
    assert not verify_password("AttackerNewPass1!", pw_hash_after), (
        "La contraseña del atacante NO debe verificar contra el hash almacenado."
    )


def test_accept_existing_email_authenticated_as_different_user_returns_403(app_with_db):
    """Caso 3: email existente + user autenticado como OTRO email → 403.

    Este es el vector principal del attack: un atacante con cuenta propia
    intenta aceptar una invitación destinada a otra persona.
    """
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school_id = _make_school(client, super_token, "TakeoverSchool", "to-school")
    _make_school_admin(SessionLocal, school_id, "admin@to-school.com")

    # Víctima con cuenta establecida
    _make_existing_user(SessionLocal, "victim@target.com", school_id=None)

    # Atacante con su propia cuenta en otro colegio
    _make_existing_user(SessionLocal, "attacker@evil.com", school_id=None)

    admin_token = _login(client, "admin@to-school.com", "adminpass123")
    invite_token = _create_invitation(client, admin_token, "victim@target.com", role="student")

    # Atacante se autentica como sí mismo (no como la víctima)
    attacker_token = _login(client, "attacker@evil.com", "existingpass123")

    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "AttackerOwnPass1!", "name": "Attacker"},
        headers={"Authorization": f"Bearer {attacker_token}"},
    )
    assert r.status_code == 403, r.text
    detail = r.json()["detail"]
    assert "cuenta" in detail.lower() or "email" in detail.lower()

    # La cuenta de la víctima NO debe haber sido afectada
    r2 = client.post(
        "/api/v1/auth/login",
        json={"email": "victim@target.com", "password": "existingpass123"},
    )
    assert r2.status_code == 200, "La cuenta de la víctima debe seguir intacta tras el ataque bloqueado."


def test_accept_existing_email_anonymous_returns_401(app_with_db):
    """Caso 4: email existente establecido + request anónimo → 401.

    El frontend debe redirigir al login con next=accept_url.
    """
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school_id = _make_school(client, super_token, "AnonSchool", "anon-school")
    _make_school_admin(SessionLocal, school_id, "admin@anon-school.com")

    # Cuenta existente y establecida
    _make_existing_user(SessionLocal, "established@test.com", school_id=None)

    admin_token = _login(client, "admin@anon-school.com", "adminpass123")
    invite_token = _create_invitation(client, admin_token, "established@test.com", role="student")

    # Intento anónimo (sin Authorization header)
    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "AnyPass123!", "name": "Anyone"},
    )
    assert r.status_code == 401, r.text
    # Debe haber WWW-Authenticate header indicando Bearer
    assert "WWW-Authenticate" in r.headers or "www-authenticate" in r.headers


def test_accept_expired_token_returns_410(app_with_db):
    """Caso 5: token expirado → 410 Gone."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school_id = _make_school(client, super_token, "ExpiredSchool", "exp-school")
    _make_school_admin(SessionLocal, school_id, "admin@exp-school.com")

    admin_token = _login(client, "admin@exp-school.com", "adminpass123")

    # Crear invitación con expires_in_days=1
    H = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/school/me/invitations",
        json={"email": "expired@test.com", "role": "student", "expires_in_days": 1},
        headers=H,
    )
    assert r.status_code == 201, r.text
    inv = r.json()
    invite_token = inv["accept_url"].rsplit("/", 1)[-1]

    # Expirar manualmente la invitación en la DB
    from app.db.models import Invitation

    db = SessionLocal()
    row = db.query(Invitation).filter(Invitation.token == invite_token).first()
    row.expires_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()
    db.close()

    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "AnyPass123!"},
    )
    assert r.status_code == 410, r.text


def test_accept_cross_role_blocks_downgrade(app_with_db):
    """Caso 6: cuenta existente con rol superior a la invitación → 409.

    Un psychologist no puede ser "downgraded" a student via invitación.
    """
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school_id = _make_school(client, super_token, "CrossRoleSchool", "cr-school")
    _make_school_admin(SessionLocal, school_id, "admin@cr-school.com")

    # Usuario existente con rol psychologist (sin colegio, aún no vinculado)
    _make_existing_user(SessionLocal, "psy@cr-school.com", role="psychologist", school_id=None)

    admin_token = _login(client, "admin@cr-school.com", "adminpass123")
    # Invitación como STUDENT para un email que ya es PSYCHOLOGIST
    invite_token = _create_invitation(client, admin_token, "psy@cr-school.com", role="student")

    # El psychologist autentica e intenta aceptar la invitación
    psy_token = _login(client, "psy@cr-school.com", "existingpass123")

    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "PsyPass123!"},
        headers={"Authorization": f"Bearer {psy_token}"},
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "incompatible" in detail.lower() or "rol" in detail.lower()


def test_accept_cross_school_blocks_move(app_with_db):
    """Caso 7: cuenta existente vinculada a otro colegio → 409.

    No se puede mover una cuenta establecida a un nuevo colegio vía invitación.
    """
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")

    school_a = _make_school(client, super_token, "SchoolA", "school-a")
    school_b = _make_school(client, super_token, "SchoolB", "school-b")
    _make_school_admin(SessionLocal, school_a, "admin@school-a.com")
    _make_school_admin(SessionLocal, school_b, "admin@school-b.com")

    # Estudiante ya vinculado a school_a
    _make_existing_user(SessionLocal, "student@multi-school.com", role="student", school_id=school_a)

    # school_b invita al mismo email
    admin_b_token = _login(client, "admin@school-b.com", "adminpass123")
    invite_token = _create_invitation(client, admin_b_token, "student@multi-school.com", role="student")

    # El estudiante autentica e intenta aceptar
    student_token = _login(client, "student@multi-school.com", "existingpass123")

    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "StudentPass1!"},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert r.status_code == 409, r.text


def test_accept_inactive_ghost_account_anonymous_creates_account(app_with_db):
    """Caso 8: cuenta existente pero inactiva (ghost/incomplete) + anónimo → crea correctamente.

    Si `is_active=False` o `hashed_password is None`, la cuenta no está "establecida"
    y el flow anónimo debe continuar normalmente (no requiere auth).

    Nota: SQLite en memoria puede no respetar NOT NULL de hashed_password; este test
    valida la lógica del flag `is_established` para cuentas inactivas con password.
    """
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school_id = _make_school(client, super_token, "GhostSchool", "ghost-school")
    _make_school_admin(SessionLocal, school_id, "admin@ghost-school.com")

    # Cuenta inactiva: is_active=False
    _make_existing_user(
        SessionLocal, "ghost@test.com", role="student", school_id=None, is_active=False
    )

    admin_token = _login(client, "admin@ghost-school.com", "adminpass123")
    invite_token = _create_invitation(client, admin_token, "ghost@test.com", role="student")

    # Sin autenticación → debe pasar porque la cuenta no está establecida
    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "NewGhostPass1!", "name": "Ghost"},
    )
    # Puede ser 200 (cuenta inactiva no es "establecida") o 401 (si la lógica
    # usa solo is_active=False como criterio de no-establecida).
    # La implementación usa `is_active AND hashed_password is not None`.
    # Una cuenta inactiva con password no se considera establecida → 200.
    assert r.status_code == 200, (
        f"Cuenta inactiva debe ser tratable como ghost · got {r.status_code}: {r.text}"
    )


def test_double_accept_token_returns_410(app_with_db):
    """Token de invitación ya usado → 410 (idempotencia)."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school_id = _make_school(client, super_token, "DoubleAccept", "double-accept")
    _make_school_admin(SessionLocal, school_id, "admin@double-accept.com")

    admin_token = _login(client, "admin@double-accept.com", "adminpass123")
    invite_token = _create_invitation(client, admin_token, "once@test.com", role="student")

    # Primera aceptación: OK
    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "OncePass123!", "name": "Once"},
    )
    assert r.status_code == 200, r.text

    # Segunda aceptación con el mismo token: 410
    r2 = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "TwicePass123!", "name": "Twice"},
    )
    assert r2.status_code == 410, r2.text


def test_audit_log_records_blocked_takeover(app_with_db):
    """Takeover bloqueado queda registrado en audit_logs con action invitation.accept_blocked_takeover."""
    app, SessionLocal = app_with_db
    _make_super(SessionLocal)
    client = TestClient(app)
    super_token = _login(client, "root@gh.example.com", "rootpass123")
    school_id = _make_school(client, super_token, "AuditSchool", "audit-school")
    _make_school_admin(SessionLocal, school_id, "admin@audit-school.com")

    _make_existing_user(SessionLocal, "auditme@test.com", school_id=None)
    _make_existing_user(SessionLocal, "badactor@test.com", school_id=None)

    admin_token = _login(client, "admin@audit-school.com", "adminpass123")
    invite_token = _create_invitation(client, admin_token, "auditme@test.com", role="student")

    bad_token = _login(client, "badactor@test.com", "existingpass123")
    r = client.post(
        f"/api/v1/invitations/{invite_token}/accept",
        json={"password": "BadPass1!"},
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert r.status_code == 403

    # Verificar audit log
    from app.db.models import AuditLog

    db = SessionLocal()
    log = (
        db.query(AuditLog)
        .filter(AuditLog.action == "invitation.accept_blocked_takeover")
        .first()
    )
    db.close()
    assert log is not None, "El audit log del takeover bloqueado debe existir."
    assert log.resource_type == "invitation"
