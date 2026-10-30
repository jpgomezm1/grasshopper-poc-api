"""D-5 · Sprint 4 · el panel de planes de la agencia.

Lo que protegen estos tests:
 1. Quién puede: el estudiante no entra; el orientador ve pero no activa; el
    comercial y el super admin activan.
 2. Activar agrega una fila con quién y cómo, con 12 meses por defecto (6 para
    profesional), y el permiso cambia de verdad.
 3. Las solicitudes de "Quiero activarlo" salen primero y quedan atendidas.
 4. El aviso de vencimiento: exactamente a los 15 y 3 días, y no si ya renovó.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_bot_gratuito_b4 import app_db  # noqa: F401
from tests.test_planes_d1 import _plan, _usuario

pytestmark = pytest.mark.planes_reales

URL = "/api/v1/admin/planes"


def _crear(Sesion, email, rol=None, respuestas=None, solicitud=None):
    s = Sesion()
    try:
        u = _usuario(s, email, role=rol)
        u.name = email.split("@")[0]
        u.onboarding_answers = dict(respuestas or {})
        if solicitud:
            u.gh_contact_status = "pending"
            u.gh_contact_message = solicitud
            u.gh_contact_requested_at = datetime.utcnow()
        s.commit()
        return u.id
    finally:
        s.close()


def _h(c, email):
    r = c.post("/api/v1/auth/login", json={"email": email, "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def escenario(app_db):
    from app.db.models import UserRole

    app, Sesion = app_db
    ids = {
        "comercial": _crear(Sesion, "comercial@d5.dev", UserRole.GH_COMMERCIAL),
        "orientador": _crear(Sesion, "orientador@d5.dev", UserRole.GH_ADVISOR),
        "sara": _crear(
            Sesion, "sara@d5.dev",
            respuestas={"life_stage": "high_school", "grade": "11"},
            solicitud="Quiero activar el plan pago. Lo pedí desde: Los tests de tu etapa.",
        ),
        "pro": _crear(Sesion, "pro@d5.dev", respuestas={"life_stage": "working"}),
        "otro": _crear(Sesion, "otro@d5.dev"),
    }
    return app, Sesion, ids


def test_un_estudiante_no_entra_ni_se_activa_a_si_mismo(escenario):
    app, _, ids = escenario
    with TestClient(app) as c:
        h = _h(c, "sara@d5.dev")
        assert c.get(URL, headers=h).status_code == 403
        assert c.post(f"{URL}/{ids['sara']}", json={"plan": "vip"}, headers=h).status_code == 403


def test_el_orientador_ve_pero_no_activa(escenario):
    app, _, ids = escenario
    with TestClient(app) as c:
        h = _h(c, "orientador@d5.dev")
        assert c.get(URL, headers=h).status_code == 200
        r = c.post(f"{URL}/{ids['sara']}", json={"plan": "pago"}, headers=h)
        assert r.status_code == 403
        assert "comercial" in r.json()["detail"]


def test_las_solicitudes_salen_primero(escenario):
    app, _, _ = escenario
    with TestClient(app) as c:
        lista = c.get(URL, headers=_h(c, "comercial@d5.dev")).json()
        solo = c.get(f"{URL}?solo_solicitudes=true", headers=_h(c, "comercial@d5.dev")).json()
    assert lista[0]["email"] == "sara@d5.dev"
    assert lista[0]["solicitud"].startswith("Quiero activar el plan")
    assert [f["email"] for f in solo] == ["sara@d5.dev"]


def test_buscar_por_correo_o_nombre(escenario):
    app, _, _ = escenario
    with TestClient(app) as c:
        r = c.get(f"{URL}?q=PRO", headers=_h(c, "comercial@d5.dev")).json()
    assert [f["email"] for f in r] == ["pro@d5.dev"]


def test_activar_agrega_una_fila_atiende_la_solicitud_y_cambia_el_permiso(escenario, monkeypatch):
    app, Sesion, ids = escenario
    correos = []
    monkeypatch.setattr("app.services.email_service.send_email", lambda **kw: correos.append(kw))
    with TestClient(app) as c:
        h = _h(c, "comercial@d5.dev")
        antes = c.get("/api/v1/me/permisos", headers=_h(c, "sara@d5.dev")).json()
        r = c.post(f"{URL}/{ids['sara']}", json={"plan": "pago", "metodo": "transferencia"}, headers=h)
        despues = c.get("/api/v1/me/permisos", headers=_h(c, "sara@d5.dev")).json()
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["plan"], cuerpo["origen"]) == ("pago", "propio")
    # 12 meses por defecto.
    assert 360 <= cuerpo["vence_en_dias"] <= 366
    assert cuerpo["solicitud"] is None
    [fila] = cuerpo["historial"]
    assert fila["metodo"] == "transferencia"
    assert fila["activado_por"] == "comercial"

    assert antes["funciones"]["tests"]["permitido"] is False
    assert despues["funciones"]["tests"]["permitido"] is True

    from app.db.models import User

    s = Sesion()
    assert s.query(User).filter(User.id == ids["sara"]).first().gh_contact_status == "converted"
    s.close()
    assert correos and correos[0]["to"] == "sara@d5.dev"
    assert "plan pago" in correos[0]["subject"]


def test_a_un_profesional_le_dura_6_meses(escenario, monkeypatch):
    app, _, ids = escenario
    monkeypatch.setattr("app.services.email_service.send_email", lambda **kw: None)
    with TestClient(app) as c:
        r = c.post(f"{URL}/{ids['pro']}", json={"plan": "pago"}, headers=_h(c, "comercial@d5.dev"))
    assert 180 <= r.json()["vence_en_dias"] <= 184


def test_renovar_o_bajar_agrega_filas_y_queda_el_historial(escenario, monkeypatch):
    app, _, ids = escenario
    monkeypatch.setattr("app.services.email_service.send_email", lambda **kw: None)
    with TestClient(app) as c:
        h = _h(c, "comercial@d5.dev")
        c.post(f"{URL}/{ids['otro']}", json={"plan": "vip", "sin_vencimiento": True}, headers=h)
        r = c.post(f"{URL}/{ids['otro']}", json={"plan": "gratis", "notas": "pidió la devolución"}, headers=h)
    cuerpo = r.json()
    assert cuerpo["plan"] == "gratis"
    assert [f["plan"] for f in cuerpo["historial"]] == ["gratis", "vip"]


def test_vencimiento_antes_del_inicio_se_rechaza(escenario):
    app, _, ids = escenario
    with TestClient(app) as c:
        r = c.post(
            f"{URL}/{ids['otro']}",
            json={"plan": "pago", "desde": "2026-10-30T00:00:00", "hasta": "2026-10-01T00:00:00"},
            headers=_h(c, "comercial@d5.dev"),
        )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# El aviso de vencimiento
# ---------------------------------------------------------------------------

_RUTA = Path(__file__).resolve().parent.parent / "scripts" / "avisar_vencimientos_planes.py"
_spec = importlib.util.spec_from_file_location("avisar_vencimientos_planes", _RUTA)
avisos = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = avisos
_spec.loader.exec_module(avisos)


def test_avisa_a_los_15_y_a_los_3_dias_y_no_si_ya_renovo(app_db):
    _, Sesion = app_db
    hoy = date(2026, 10, 30)
    base = datetime(2026, 10, 30, 12)
    s = Sesion()
    a15 = _usuario(s, "a15@d5.dev")
    a3 = _usuario(s, "a3@d5.dev")
    a10 = _usuario(s, "a10@d5.dev")
    renovo = _usuario(s, "renovo@d5.dev")
    _plan(s, a15, "pago", base - timedelta(days=300), base + timedelta(days=15))
    _plan(s, a3, "vip", base - timedelta(days=300), base + timedelta(days=3))
    _plan(s, a10, "pago", base - timedelta(days=300), base + timedelta(days=10))
    _plan(s, renovo, "pago", base - timedelta(days=300), base + timedelta(days=15))
    _plan(s, renovo, "pago", base - timedelta(days=1), base + timedelta(days=380))

    resultado = {(a["user"].email, a["dias"]) for a in avisos.a_quien_avisar(s, hoy)}
    s.close()
    assert resultado == {("a15@d5.dev", 15), ("a3@d5.dev", 3)}
