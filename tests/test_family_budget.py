"""La calculadora financiera del acudiente · P8.

Verónica (Padres, Paso 2): *"Calculadora Financiera. Módulo PRIVADO para
ingresar presupuesto disponible para la educación de su hijo."*

## Por qué la mitad de estos tests son de privacidad

Porque ella subrayó "privado", y porque el atajo evidente —escribir el número
en `User.budget_max_usd`, que ya existe— habría hecho dos daños a la vez:
pisar lo que declaró el estudiante, y cambiarle sus recomendaciones sin que
sepa por qué. De ahí a que infiera la cifra de su familia hay un paso.

  (a) ⭐ el presupuesto NO toca las columnas del estudiante
  (b) ⭐ el estudiante no puede leerlo
  (c) ⭐ un acudiente no ve al hijo de otro · 404, no 403
  (d) ⭐ una relación revocada deja de dar acceso
  (e) la calculadora dice qué alcanza, contra precios reales
  (f) ⭐ no inventa tasas de cambio
  (g) "cerca" existe para no esconder lo que una beca vuelve posible
  (h) validaciones: sin moneda no hay número
"""
from __future__ import annotations

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


CLAVE = "testpass123"


def _usuario(S, email, rol, **extra):
    from app.db.models import User, UserRole, OnboardingStatus
    from app.api.v1.auth import get_password_hash

    db = S()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash(CLAVE),
            name="Persona",
            role=getattr(UserRole, rol),
            onboarding_status=OnboardingStatus.NOT_STARTED,
            **extra,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id
    finally:
        db.close()


def _relacion(S, parent_id, student_id, activa=True):
    from app.db.models import ParentRelationship

    db = S()
    try:
        r = ParentRelationship(
            parent_user_id=parent_id,
            student_user_id=student_id,
            relationship_type="madre",
            is_active=activa,
        )
        db.add(r)
        db.commit()
    finally:
        db.close()


def _login(client, email):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": CLAVE})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _ruta(sid):
    return f"/api/v1/me/hijos/{sid}/presupuesto"


def _familia(S, *, activa=True, budget_max_usd=None):
    hijo = _usuario(S, "hijo@x.com", "STUDENT", budget_max_usd=budget_max_usd, budget_band="bajo")
    madre = _usuario(S, "madre@x.com", "PARENT")
    _relacion(S, madre, hijo, activa=activa)
    return hijo, madre


# ---------------------------------------------------------------------------
# (a) ⭐ privado de verdad
# ---------------------------------------------------------------------------

def test_el_presupuesto_del_padre_NO_pisa_el_del_estudiante(app_with_db):
    """⭐ El atajo evidente habría sido escribir en `User.budget_max_usd`.

    Habría pisado lo que declaró el hijo y le habría cambiado las
    recomendaciones sin que sepa por qué.
    """
    app, S = app_with_db
    hijo, _madre = _familia(S, budget_max_usd=5000)

    client = TestClient(app)
    r = client.put(
        _ruta(hijo),
        json={"anual_max": 30000, "moneda": "USD"},
        headers=_login(client, "madre@x.com"),
    )
    assert r.status_code == 200, r.text

    from app.db.models import User
    db = S()
    try:
        alumno = db.query(User).filter(User.id == hijo).first()
        assert alumno.budget_max_usd == 5000  # lo que dijo ÉL
        assert alumno.budget_band == "bajo"
    finally:
        db.close()


def test_el_estudiante_no_puede_leer_el_presupuesto(app_with_db):
    app, S = app_with_db
    hijo, _madre = _familia(S)

    client = TestClient(app)
    r = client.get(_ruta(hijo), headers=_login(client, "hijo@x.com"))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# (c) (d) ⭐ las fronteras
# ---------------------------------------------------------------------------

def test_un_acudiente_no_ve_al_hijo_de_otro(app_with_db):
    # 404 y no 403 · confirmar que ese estudiante existe ya es informacion.
    app, S = app_with_db
    ajeno = _usuario(S, "ajeno@x.com", "STUDENT")
    _usuario(S, "madre@x.com", "PARENT")

    client = TestClient(app)
    assert client.get(_ruta(ajeno), headers=_login(client, "madre@x.com")).status_code == 404


def test_una_relacion_revocada_deja_de_dar_acceso(app_with_db):
    """⭐ `is_active=False` es divorcio o cambio de custodia.

    El dato tiene que dejar de ser alcanzable por esta puerta.
    """
    app, S = app_with_db
    hijo, _madre = _familia(S, activa=False)

    client = TestClient(app)
    assert client.get(_ruta(hijo), headers=_login(client, "madre@x.com")).status_code == 404


def test_sin_token_no_se_puede(app_with_db):
    app, S = app_with_db
    hijo, _madre = _familia(S)
    assert TestClient(app).get(_ruta(hijo)).status_code in (401, 403)


# ---------------------------------------------------------------------------
# (e) (f) (g) la calculadora
# ---------------------------------------------------------------------------

def test_dice_que_alcanza_contra_precios_reales(app_with_db):
    app, S = app_with_db
    hijo, _madre = _familia(S)

    client = TestClient(app)
    r = client.put(
        _ruta(hijo),
        json={"anual_max": 5000, "moneda": "USD", "con_financiacion": False},
        headers=_login(client, "madre@x.com"),
    )
    alcanza = r.json()["que_alcanza"]

    assert alcanza["total_con_precio"] > 0
    assert alcanza["alcanzables"]["cuantas"] > 0
    assert len(alcanza["alcanzables"]["ejemplos"]) > 0


def test_el_rango_del_catalogo_se_ve_aunque_no_haya_presupuesto(app_with_db):
    # Es justo cuando mas le sirve a un padre que todavia no sabe que numeros
    # se manejan.
    app, S = app_with_db
    hijo, _madre = _familia(S)

    client = TestClient(app)
    cuerpo = client.get(_ruta(hijo), headers=_login(client, "madre@x.com")).json()

    assert cuerpo["anual_max"] is None
    assert cuerpo["que_alcanza"]["rango_del_catalogo"]["min"] is not None


def test_no_inventa_tasas_de_cambio(app_with_db):
    """⭐ Una tasa desactualizada en una decisión de educación es peor que no
    dar el dato: la familia planearía sobre un número falso."""
    app, S = app_with_db
    hijo, _madre = _familia(S)

    client = TestClient(app)
    r = client.put(
        _ruta(hijo),
        json={"anual_max": 60000000, "moneda": "COP"},
        headers=_login(client, "madre@x.com"),
    )
    alcanza = r.json()["que_alcanza"]

    assert alcanza["alcanzables"] is None
    assert "no convertimos" in (alcanza["aviso"] or "").lower() or "tasa" in (alcanza["aviso"] or "").lower()


def test_cerca_no_esconde_lo_que_una_beca_vuelve_posible(app_with_db):
    # Con 2000 USD, el voluntariado de 500-2000 entra; algo de 2500 queda
    # "cerca" y hay que enseñarlo.
    app, S = app_with_db
    hijo, _madre = _familia(S)

    client = TestClient(app)
    r = client.put(
        _ruta(hijo), json={"anual_max": 2000, "moneda": "USD"}, headers=_login(client, "madre@x.com")
    )
    alcanza = r.json()["que_alcanza"]

    assert alcanza["cerca"]["cuantas"] > 0


# ---------------------------------------------------------------------------
# (h) validaciones
# ---------------------------------------------------------------------------

def test_un_numero_sin_moneda_no_entra(app_with_db):
    # 15.000 no es lo mismo en dolares que en pesos.
    app, S = app_with_db
    hijo, _madre = _familia(S)

    client = TestClient(app)
    r = client.put(_ruta(hijo), json={"anual_max": 15000}, headers=_login(client, "madre@x.com"))
    assert r.status_code == 422
    assert "moneda" in r.json()["detail"].lower()


def test_una_moneda_inventada_se_rechaza(app_with_db):
    app, S = app_with_db
    hijo, _madre = _familia(S)

    client = TestClient(app)
    r = client.put(
        _ruta(hijo), json={"anual_max": 100, "moneda": "XYZ"}, headers=_login(client, "madre@x.com")
    )
    assert r.status_code == 422


def test_guardar_dos_veces_no_duplica(app_with_db):
    app, S = app_with_db
    hijo, _madre = _familia(S)

    client = TestClient(app)
    h = _login(client, "madre@x.com")
    client.put(_ruta(hijo), json={"anual_max": 10000, "moneda": "USD"}, headers=h)
    client.put(_ruta(hijo), json={"anual_max": 20000, "moneda": "USD"}, headers=h)

    assert client.get(_ruta(hijo), headers=h).json()["anual_max"] == 20000

    from app.db.models import FamilyBudget
    db = S()
    try:
        assert db.query(FamilyBudget).count() == 1
    finally:
        db.close()
