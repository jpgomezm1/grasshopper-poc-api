"""D-1 · Sprint 4 · el plan vigente de cada usuario, decidido en un solo sitio.

Regla (D1, D2, D9 de JP): no estudiante → pago (rol) · colegio con licencia
vigente → pago (licencia) · plan propio vigente → ese · nada → gratis.

Lo que protegen estos tests: cada rama de la regla, que una licencia o un plan
vencido deje de contar sin que nadie lo toque, que gane el plan propio más
reciente, y `GET /me/plan` sobre HTTP.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.services import plan_service as ps
from tests.test_bot_gratuito_b4 import app_db  # noqa: F401

# La regla real de planes, sin el `pago` por defecto de `conftest.py`.
pytestmark = pytest.mark.planes_reales

AHORA = datetime(2026, 10, 29, 12, 0)


def _usuario(db, email, role=None, school_id=None):
    from app.api.v1.auth import get_password_hash
    from app.db.models import OnboardingStatus, User, UserRole

    u = User(
        email=email,
        hashed_password=get_password_hash("testpass123"),
        role=role or UserRole.STUDENT,
        school_id=school_id,
        onboarding_status=OnboardingStatus.NOT_STARTED,
        onboarding_answers={},
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _colegio(db, *, licencia="active", vence=None):
    from app.db.models import License, School

    s = School(name="Colegio Prueba", slug=f"prueba-{datetime.utcnow().timestamp()}")
    db.add(s)
    db.commit()
    if licencia:
        db.add(License(school_id=s.id, status=licencia, expires_at=vence))
        db.commit()
    return s


def _plan(db, user, plan, desde, hasta=None):
    from app.db.models import UserPlan

    db.add(UserPlan(user_id=user.id, plan=plan, desde=desde, hasta=hasta, creado_en=desde))
    db.commit()


@pytest.fixture()
def db(app_db):
    _, Sesion = app_db
    s = Sesion()
    yield s
    s.close()


def test_sin_nada_es_gratis(db):
    u = _usuario(db, "nada@d1.dev")
    assert ps.plan_vigente(db, u, AHORA) == ps.PlanVigente("gratis", "ninguno")


def test_quien_no_es_estudiante_no_se_bloquea(db):
    from app.db.models import UserRole

    for rol in (UserRole.PSYCHOLOGIST, UserRole.SCHOOL_ADMIN, UserRole.GH_ADVISOR, UserRole.SUPER_ADMIN):
        u = _usuario(db, f"{rol.value}@d1.dev", role=rol)
        assert ps.plan_vigente(db, u, AHORA).origen == "rol"


def test_colegio_con_licencia_vigente_es_pago(db):
    s = _colegio(db, vence=datetime.utcnow() + timedelta(days=90))
    u = _usuario(db, "lic@d1.dev", school_id=s.id)
    p = ps.plan_vigente(db, u)
    assert (p.plan, p.origen) == ("pago", "licencia")
    assert p.hasta is not None


def test_licencia_vencida_o_cancelada_deja_de_contar(db):
    vencida = _colegio(db, vence=datetime.utcnow() - timedelta(days=1))
    cancelada = _colegio(db, licencia="cancelled")
    for s, email in ((vencida, "vencida@d1.dev"), (cancelada, "cancelada@d1.dev")):
        u = _usuario(db, email, school_id=s.id)
        assert ps.plan_vigente(db, u).plan == "gratis"


def test_plan_propio_vigente(db):
    u = _usuario(db, "propio@d1.dev")
    _plan(db, u, "vip", AHORA - timedelta(days=10), AHORA + timedelta(days=355))
    p = ps.plan_vigente(db, u, AHORA)
    assert (p.plan, p.origen, p.hasta) == ("vip", "propio", AHORA + timedelta(days=355))


def test_plan_propio_vencido_vuelve_a_gratis_solo(db):
    u = _usuario(db, "vencido@d1.dev")
    _plan(db, u, "pago", AHORA - timedelta(days=400), AHORA - timedelta(days=35))
    assert ps.plan_vigente(db, u, AHORA).plan == "gratis"


def test_un_plan_que_todavia_no_empieza_no_cuenta(db):
    u = _usuario(db, "futuro@d1.dev")
    _plan(db, u, "pago", AHORA + timedelta(days=1))
    assert ps.plan_vigente(db, u, AHORA).plan == "gratis"


def test_gana_el_mas_reciente_y_queda_el_historial(db):
    """Pasar de pago a VIP agrega una fila; no edita la anterior."""
    from app.db.models import UserPlan

    u = _usuario(db, "historial@d1.dev")
    _plan(db, u, "pago", AHORA - timedelta(days=60))
    _plan(db, u, "vip", AHORA - timedelta(days=5))
    assert ps.plan_vigente(db, u, AHORA).plan == "vip"
    assert db.query(UserPlan).filter(UserPlan.user_id == u.id).count() == 2


def test_la_licencia_manda_sobre_el_plan_propio(db):
    """Si el colegio paga, no importa que su plan propio sea gratis o haya vencido."""
    s = _colegio(db)
    u = _usuario(db, "ambos@d1.dev", school_id=s.id)
    _plan(db, u, "gratis", AHORA - timedelta(days=1))
    assert ps.plan_vigente(db, u).origen == "licencia"


def test_get_me_plan(app_db):
    app, Sesion = app_db
    s = Sesion()
    _usuario(s, "http@d1.dev")
    s.close()
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", json={"email": "http@d1.dev", "password": "testpass123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        cuerpo = c.get("/api/v1/me/plan", headers=h).json()
        assert cuerpo == {"plan": "gratis", "origen": "ninguno", "hasta": None}
        assert c.get("/api/v1/me/plan").status_code in (401, 403)
