"""J-2 · Sprint 4 · el dashboard trae la escalera de SU grado.

Verónica: *"la plataforma no te va llevando sino que tú tienes que saber qué
hacer"*. La guía ya existía pero era la misma para todos ("haz tu primer test",
"completa otro"). Ahora el dashboard trae los tests de su etapa, en el orden de
la matriz de D-2, con si ya lo hizo y si su plan lo tiene con candado. Todo el
que pinta la guía lee de aquí.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.test_bot_gratuito_b4 import app_db  # noqa: F401
from tests.test_planes_d1 import _plan, _usuario

pytestmark = pytest.mark.planes_reales


def _estudiante(Sesion, email, respuestas, plan=None, hechos=()):
    from app.db.models import VocationalTestResult

    s = Sesion()
    u = _usuario(s, email)
    u.onboarding_answers = respuestas
    s.commit()
    if plan:
        _plan(s, u, plan, datetime.utcnow() - timedelta(days=1))
    for t in hechos:
        s.add(VocationalTestResult(user_id=u.id, test_id=t, scores={}, answers={}))
    s.commit()
    s.close()


def _dashboard(app, email):
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", json={"email": email, "password": "testpass123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        d = c.get("/api/v1/me/dashboard", headers=h)
    assert d.status_code == 200, d.text
    return d.json()


def test_noveno_pago_ve_sus_tres_tests_en_orden_y_sin_ingles(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "n@j2.dev", {"life_stage": "high_school_early", "grade": "9"}, "pago", hechos=["vark"])
    d = _dashboard(app, "n@j2.dev")
    assert [(t["id"], t["hecho"], t["con_candado"]) for t in d["tests_de_su_etapa"]] == [
        ("vark", True, False),
        ("motivadores", False, False),
        ("holland", False, False),
    ]
    assert d["ingles_aplica"] is False
    # Con plan pago solo queda con candado lo VIP (la sesión 1:1). El Profiler
    # no aparece: no es "plan", es "no disponible".
    assert d["funciones_con_candado"] == ["sesion_1a1"]


def test_once_gratis_ve_sus_tests_con_candado(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "o@j2.dev", {"life_stage": "high_school", "grade": "11"})
    d = _dashboard(app, "o@j2.dev")
    assert [t["id"] for t in d["tests_de_su_etapa"]] == ["istrong", "mbti", "bigfive"]
    assert all(t["con_candado"] for t in d["tests_de_su_etapa"])
    assert d["ingles_aplica"] is True
    assert {"tests", "hoja_de_vida", "chat_hopper"} <= set(d["funciones_con_candado"])


def test_cada_test_lleva_su_nombre_corto(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "nom@j2.dev", {"life_stage": "high_school", "grade": "11"}, "pago")
    d = _dashboard(app, "nom@j2.dev")
    assert all(t["nombre"] and t["nombre"] != t["id"] for t in d["tests_de_su_etapa"])


def test_sin_grado_conocido_no_hay_escalera_de_etapa(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "sg@j2.dev", {}, "pago")
    d = _dashboard(app, "sg@j2.dev")
    assert d["tests_de_su_etapa"] == []
