"""D-3 · Sprint 4 · el backend niega lo que el plan o el grado no abren.

Con la regla REAL de planes (`planes_reales`, sin el `pago` por defecto de
`conftest.py`). Lo que protegen estos tests:

 1. Un estudiante gratis recibe 402 `plan_requerido` en cada función paga.
 2. Uno pago pasa la llave (lo que pase después ya es de cada función).
 3. Uno pago de otro grado recibe 402 por grado en el test que no es suyo.
 4. Leer lo que ya hizo NO se bloquea.
 5. El equipo no se bloquea.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.test_bot_gratuito_b4 import app_db  # noqa: F401
from tests.test_planes_d1 import _plan, _usuario

pytestmark = pytest.mark.planes_reales

API = "/api/v1"

# (método, ruta, cuerpo) · lo que CREA o GENERA, una ruta por función.
PAGAS = [
    ("post", "/hop/chat", {"message": "hola"}),
    ("get", "/busqueda/paises", None),
    ("get", "/ofertas", None),
    ("get", "/me/videos", None),
    ("get", "/exam-prep", None),
    ("put", "/me/cv/profile", {}),
    ("post", "/me/cv/share", None),
    ("post", "/me/tools/statement-of-purpose", {}),
    ("get", "/vocational-tests/holland/interpretation", None),
]


def _estudiante(Sesion, email, plan=None, respuestas=None, rol=None):
    db = Sesion()
    try:
        u = _usuario(db, email, role=rol)
        u.onboarding_answers = dict(respuestas or {})
        db.commit()
        if plan:
            _plan(db, u, plan, datetime.utcnow() - timedelta(days=1))
    finally:
        db.close()


def _h(c, email):
    r = c.post(f"{API}/auth/login", json={"email": email, "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _pedir(c, h, metodo, ruta, cuerpo):
    kwargs = {"headers": h}
    if cuerpo is not None:
        kwargs["json"] = cuerpo
    return getattr(c, metodo)(API + ruta, **kwargs)


ONCE = {"life_stage": "high_school", "grade": "11"}
NOVENO = {"life_stage": "high_school_early", "grade": "9"}


@pytest.mark.parametrize("metodo, ruta, cuerpo", PAGAS)
def test_gratis_recibe_402_en_cada_funcion_paga(app_db, metodo, ruta, cuerpo):
    app, Sesion = app_db
    _estudiante(Sesion, "gratis@d3.dev", respuestas=ONCE)
    with TestClient(app) as c:
        r = _pedir(c, _h(c, "gratis@d3.dev"), metodo, ruta, cuerpo)
    assert r.status_code == 402, (ruta, r.status_code, r.text)
    detalle = r.json()["detail"]
    assert detalle["code"] == "plan_requerido"
    assert detalle["plan_requerido"] == "pago"
    assert detalle["motivo"] == "plan"
    assert "plan pago" in detalle["message"]


@pytest.mark.parametrize("metodo, ruta, cuerpo", PAGAS)
def test_pago_pasa_la_llave(app_db, metodo, ruta, cuerpo):
    app, Sesion = app_db
    _estudiante(Sesion, "pago@d3.dev", "pago", ONCE)
    # `raise_server_exceptions=False`: algunas funciones usan SQL de Postgres
    # (p. ej. `ANY` en /busqueda) y en SQLite responden 500. Eso ya es de la
    # función; la llave las dejó pasar, que es lo que se prueba aquí.
    with TestClient(app, raise_server_exceptions=False) as c:
        r = _pedir(c, _h(c, "pago@d3.dev"), metodo, ruta, cuerpo)
    # Lo que responda después (200, 404, 405, 422…) ya es de cada función: aquí
    # solo importa que la llave no lo haya frenado.
    assert r.status_code != 402, (ruta, r.text)


def test_un_test_de_otro_grado_se_niega_por_grado(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "noveno@d3.dev", "pago", NOVENO)
    with TestClient(app) as c:
        h = _h(c, "noveno@d3.dev")
        propio = c.get(f"{API}/vocational-tests/vark", headers=h)
        ajeno = c.get(f"{API}/vocational-tests/mbti", headers=h)
        enviar_ajeno = c.post(f"{API}/vocational-tests/mbti/submit", json={"answers": {}}, headers=h)
    assert propio.status_code == 200, propio.text
    for r in (ajeno, enviar_ajeno):
        assert r.status_code == 402
        assert r.json()["detail"]["motivo"] == "no_es_de_su_grado"
        assert r.json()["detail"]["message"] == "Esto no hace parte de tu etapa."


def test_el_ingles_se_niega_en_noveno_y_se_abre_en_once(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "ing9@d3.dev", "pago", NOVENO)
    _estudiante(Sesion, "ing11@d3.dev", "pago", ONCE)
    with TestClient(app) as c:
        assert c.get(f"{API}/english-test/questions", headers=_h(c, "ing9@d3.dev")).status_code == 402
        assert c.get(f"{API}/english-test/questions", headers=_h(c, "ing11@d3.dev")).status_code == 200


def test_la_sesion_1a1_es_vip(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "pago1a1@d3.dev", "pago", ONCE)
    with TestClient(app) as c:
        r = c.post(f"{API}/me/session-requests", json={"reason": "Quiero hablar"}, headers=_h(c, "pago1a1@d3.dev"))
    assert r.status_code == 402
    assert r.json()["detail"]["plan_requerido"] == "vip"
    assert "plan VIP" in r.json()["detail"]["message"]


@pytest.mark.parametrize(
    "ruta",
    [
        "/vocational-tests/results/all",
        "/english-test/result",
        "/me/cv/profile",
        "/vocational-tests/holland/interpretation?only_cached=true",
        "/me/plan",
        "/me/permisos",
        "/onboarding-chat/inicio",
    ],
)
def test_leer_lo_que_ya_hizo_no_se_bloquea(app_db, ruta):
    app, Sesion = app_db
    _estudiante(Sesion, "lee@d3.dev", respuestas=ONCE)
    with TestClient(app) as c:
        r = c.get(API + ruta, headers=_h(c, "lee@d3.dev"))
    assert r.status_code != 402, (ruta, r.text)


def test_el_equipo_no_se_bloquea(app_db):
    from app.db.models import UserRole

    app, Sesion = app_db
    _estudiante(Sesion, "asesor@d3.dev", rol=UserRole.GH_ADVISOR)
    with TestClient(app) as c:
        r = c.get(f"{API}/ofertas", headers=_h(c, "asesor@d3.dev"))
    assert r.status_code != 402
