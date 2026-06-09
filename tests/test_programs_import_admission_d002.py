"""D-002 · curación de variables de admisión vía import Excel + schema (2026-06-05).

Cubre el tooling de curación agregado al endpoint POST /programs/import:
  - helpers de coerción numérica/CEFR opcionales
  - schema: ProgramUpdate/Create aceptan los 5 campos de admisión + validan rangos
  - round-trip: importar un xlsx con las columnas de admisión las cura; una celda
    vacía NO toca el valor curado previo; un xlsx sin las columnas tampoco.

SQLite + TestClient (sin Postgres).
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

def test_coerce_excel_float_optional():
    from app.api.v1.programs import _coerce_excel_float_optional as f

    assert f(None) is None
    assert f("") is None
    assert f("   ") is None
    assert f("12.5") == 12.5
    assert f("12,5") == 12.5  # coma decimal
    assert f("15%") == 15.0   # símbolo de porcentaje
    assert f(20) == 20.0
    with pytest.raises(ValueError):
        f("no-numero")


def test_coerce_excel_int_optional():
    from app.api.v1.programs import _coerce_excel_int_optional as f

    assert f(None) is None
    assert f("") is None
    assert f("1200") == 1200
    assert f("1,350") == 1350
    assert f(1400.0) == 1400
    with pytest.raises(ValueError):
        f("abc")


def test_coerce_excel_cefr_optional():
    from app.api.v1.programs import _coerce_excel_cefr_optional as f

    assert f(None) is None
    assert f("") is None
    assert f("b2") == "B2"
    assert f(" c1 ") == "C1"
    with pytest.raises(ValueError):
        f("Z9")


# ---------------------------------------------------------------------------
# Schema · ProgramUpdate acepta y valida los campos de admisión
# ---------------------------------------------------------------------------

def test_program_update_accepts_admission_fields():
    from app.schemas.program import ProgramUpdate

    m = ProgramUpdate(
        acceptance_rate=12.5,
        avg_admitted_gpa=3.7,
        min_sat=1200,
        avg_sat=1350,
        min_english_level="b2",
    )
    assert m.acceptance_rate == 12.5
    assert m.min_english_level == "B2"  # normalizado a mayúsculas


def test_program_update_rejects_bad_admission_values():
    import pydantic
    from app.schemas.program import ProgramUpdate

    with pytest.raises(pydantic.ValidationError):
        ProgramUpdate(acceptance_rate=150)  # > 100
    with pytest.raises(pydantic.ValidationError):
        ProgramUpdate(min_sat=2000)  # > 1600
    with pytest.raises(pydantic.ValidationError):
        ProgramUpdate(min_english_level="X9")  # no es CEFR


# ---------------------------------------------------------------------------
# Round-trip del endpoint /programs/import
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


def _super_admin(SessionLocal, email="sa-d002@x.com"):
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
_ADM_COLS = ["acceptance_rate", "avg_admitted_gpa", "min_sat", "avg_sat", "min_english_level"]


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


def _base_cells(program_id):
    return [
        program_id, f"Prog {program_id}", program_id.lower(), "Canada", "Toronto", "Inst",
        "pregrado", "area", "subject", 24, 10000, "USD", "medium", "estandar", "si",
    ]


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


def _get(SessionLocal, program_id):
    from app.db.models import Program
    db = SessionLocal()
    try:
        return db.query(Program).filter(Program.program_id == program_id).first()
    finally:
        db.close()


def test_import_sets_admission_fields(app_with_db):
    app, SessionLocal = app_with_db
    email = _super_admin(SessionLocal)
    client = TestClient(app)
    token = _login(client, email)

    headers = _BASE_COLS + _ADM_COLS
    content = _xlsx(headers, [
        _base_cells("P-A") + [12.5, 3.7, 1200, 1350, "B2"],
        _base_cells("P-B") + ["", "", "", "", ""],  # todo vacío → queda NULL
    ])
    r = _upload(client, token, content)
    assert r.status_code == 200, r.text
    assert r.json()["committed"] is True

    a = _get(SessionLocal, "P-A")
    assert a.acceptance_rate == 12.5
    assert a.avg_admitted_gpa == 3.7
    assert a.min_sat == 1200
    assert a.avg_sat == 1350
    assert a.min_english_level == "B2"

    b = _get(SessionLocal, "P-B")
    assert b.acceptance_rate is None
    assert b.min_english_level is None


def test_import_invalid_admission_value_is_row_error(app_with_db):
    app, SessionLocal = app_with_db
    email = _super_admin(SessionLocal)
    client = TestClient(app)
    token = _login(client, email)

    headers = _BASE_COLS + ["acceptance_rate"]
    content = _xlsx(headers, [_base_cells("P-BAD") + ["no-numero"]])
    r = _upload(client, token, content)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["committed"] is False
    assert any(e["field"] == "acceptance_rate" for e in body["errors"])
    # no se insertó nada
    assert _get(SessionLocal, "P-BAD") is None


def test_empty_cell_does_not_wipe_curated_admission(app_with_db):
    app, SessionLocal = app_with_db
    email = _super_admin(SessionLocal)
    client = TestClient(app)
    token = _login(client, email)

    headers = _BASE_COLS + _ADM_COLS
    # 1) curar
    _upload(client, token, _xlsx(headers, [_base_cells("P-C") + [10.0, 3.9, 1300, 1400, "C1"]]))
    assert _get(SessionLocal, "P-C").acceptance_rate == 10.0
    # 2) reimportar con celdas vacías → no borra lo curado
    _upload(client, token, _xlsx(headers, [_base_cells("P-C") + ["", "", "", "", ""]]))
    c = _get(SessionLocal, "P-C")
    assert c.acceptance_rate == 10.0
    assert c.min_english_level == "C1"


def test_import_without_admission_columns_preserves(app_with_db):
    app, SessionLocal = app_with_db
    email = _super_admin(SessionLocal)
    client = TestClient(app)
    token = _login(client, email)

    # 1) curar con columnas
    _upload(client, token, _xlsx(_BASE_COLS + _ADM_COLS, [_base_cells("P-D") + [9.0, 3.8, 1250, 1390, "B2"]]))
    assert _get(SessionLocal, "P-D").min_sat == 1250
    # 2) Excel viejo sin las columnas → no toca
    _upload(client, token, _xlsx(_BASE_COLS, [_base_cells("P-D")]))
    assert _get(SessionLocal, "P-D").min_sat == 1250
