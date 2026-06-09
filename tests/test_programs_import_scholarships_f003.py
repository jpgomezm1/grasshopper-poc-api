"""F-003 · curación de becas LatAm vía import Excel + helpers (2026-06-05).

Cubre el tooling de curación agregado al endpoint POST /programs/import:
  - helpers de coerción booleana (`_coerce_excel_bool`, `_coerce_excel_bool_optional`)
  - round-trip: importar un xlsx CON la columna `scholarships_for_latam`
    enciende/apaga el flag; una celda vacía NO toca el valor curado previo;
    un xlsx SIN la columna tampoco lo borra.

El render real a PDF no aplica aquí. Usa SQLite + TestClient (sin Postgres).
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Helpers de coerción (unit · sin DB)
# ---------------------------------------------------------------------------

def test_coerce_excel_bool_tokens():
    from app.api.v1.programs import _coerce_excel_bool

    for t in ("si", "sí", "YES", "true", "1", "y", "x", " Si "):
        assert _coerce_excel_bool(t) is True
    for f in ("no", "false", "0", "", "  ", "tal vez"):
        assert _coerce_excel_bool(f) is False
    # default aplica solo a None
    assert _coerce_excel_bool(None) is False
    assert _coerce_excel_bool(None, default=True) is True
    assert _coerce_excel_bool(1) is True
    assert _coerce_excel_bool(0) is False


def test_coerce_excel_bool_optional_preserves_unknown():
    from app.api.v1.programs import _coerce_excel_bool_optional

    # vacío / None → None (no tocar)
    assert _coerce_excel_bool_optional(None) is None
    assert _coerce_excel_bool_optional("") is None
    assert _coerce_excel_bool_optional("   ") is None
    # con valor → bool
    assert _coerce_excel_bool_optional("si") is True
    assert _coerce_excel_bool_optional("no") is False
    assert _coerce_excel_bool_optional(1) is True


# ---------------------------------------------------------------------------
# Round-trip del endpoint /programs/import (SQLite + TestClient)
# ---------------------------------------------------------------------------

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


def _super_admin(SessionLocal, email="sa@x.com"):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash("testpass123"),
            name="SA",
            role=UserRole.SUPER_ADMIN,
            onboarding_status=OnboardingStatus.NOT_STARTED,
        )
        db.add(u)
        db.commit()
        return u.email
    finally:
        db.close()


def _login(client, email, password="testpass123"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


_BASE_COLS = [
    "program_id", "name", "slug", "country", "city", "institution",
    "type", "area", "subject", "duration_months", "cost_total",
    "currency", "budget_tier", "alliance_type", "active",
]


def _xlsx(headers, rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _row(program_id, *, beca=None):
    base = [
        program_id, f"Prog {program_id}", program_id.lower(), "Canada", "Toronto", "Inst",
        "pregrado", "area", "subject", 24, 10000, "USD", "medium", "estandar", "si",
    ]
    if beca is not None:
        base = base + [beca]
    return base


def _get_flag(SessionLocal, program_id):
    from app.db.models import Program
    db = SessionLocal()
    try:
        p = db.query(Program).filter(Program.program_id == program_id).first()
        return p.scholarships_for_latam if p else "MISSING"
    finally:
        db.close()


def _upload(client, token, content, *, commit=True):
    return client.post(
        f"/api/v1/programs/import?commit={'true' if commit else 'false'}",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "file": (
                "catalog.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def test_import_with_scholarship_column_sets_tristate(app_with_db):
    app, SessionLocal = app_with_db
    email = _super_admin(SessionLocal)
    client = TestClient(app)
    token = _login(client, email)

    headers = _BASE_COLS + ["scholarships_for_latam"]
    content = _xlsx(headers, [
        _row("P-YES", beca="si"),
        _row("P-NO", beca="no"),
        _row("P-EMPTY", beca=""),
    ])
    r = _upload(client, token, content)
    assert r.status_code == 200, r.text
    assert r.json()["committed"] is True

    assert _get_flag(SessionLocal, "P-YES") is True
    assert _get_flag(SessionLocal, "P-NO") is False
    # celda vacía en insert → queda NULL (desconocido), no False
    assert _get_flag(SessionLocal, "P-EMPTY") is None


def test_empty_cell_does_not_wipe_curated_flag(app_with_db):
    app, SessionLocal = app_with_db
    email = _super_admin(SessionLocal)
    client = TestClient(app)
    token = _login(client, email)

    headers = _BASE_COLS + ["scholarships_for_latam"]
    # 1) curar a True
    _upload(client, token, _xlsx(headers, [_row("P-1", beca="si")]))
    assert _get_flag(SessionLocal, "P-1") is True
    # 2) reimportar con celda vacía → NO debe borrar el True curado
    _upload(client, token, _xlsx(headers, [_row("P-1", beca="")]))
    assert _get_flag(SessionLocal, "P-1") is True


def test_import_without_column_preserves_flag(app_with_db):
    app, SessionLocal = app_with_db
    email = _super_admin(SessionLocal)
    client = TestClient(app)
    token = _login(client, email)

    # 1) curar a True con la columna
    _upload(client, token, _xlsx(_BASE_COLS + ["scholarships_for_latam"], [_row("P-2", beca="si")]))
    assert _get_flag(SessionLocal, "P-2") is True
    # 2) reimportar SIN la columna (Excel viejo) → no toca el flag
    _upload(client, token, _xlsx(_BASE_COLS, [_row("P-2")]))
    assert _get_flag(SessionLocal, "P-2") is True
