"""E · Sprint 4 · el plan de preparación de 11° y 12°.

Lo que protegen estos tests:
 1. Quien solo se ve en Colombia no recibe SAT ni IELTS, y sí el Saber 11.
 2. Quien va afuera recibe el examen de inglés, y el SAT solo si mira EE. UU.
 3. "Quizás" ve los pasos de afuera, pero condicionados ("Si decides…").
 4. La etapa del medio depende de si su colegio llega a 12°.
 5. Lo que ya hizo sale hecho; lo que su plan no incluye, con candado.
 6. Sobre HTTP: gratis y otros grados reciben 402; pago de 11° recibe el plan.
 7. Nunca publica fechas oficiales.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.services import plan_preparacion_service as svc
from tests.test_bot_gratuito_b4 import app_db  # noqa: F401
from tests.test_planes_d1 import _plan, _usuario

pytestmark = pytest.mark.planes_reales

ONCE = {"life_stage": "high_school", "grade": "11"}
DOCE = {"life_stage": "high_school", "grade": "12"}


@pytest.fixture()
def db(app_db):
    _, Sesion = app_db
    s = Sesion()
    yield s
    s.close()


def _estudiante(db, email, respuestas, plan="pago", **campos):
    u = _usuario(db, email)
    u.onboarding_answers = dict(respuestas)
    for k, v in campos.items():
        setattr(u, k, v)
    db.commit()
    if plan:
        _plan(db, u, plan, datetime.utcnow() - timedelta(days=1))
    return u


def _ids(plan):
    return [p["id"] for e in plan["etapas"] for p in e["pasos"]]


def _paso(plan, id):
    return next(p for e in plan["etapas"] for p in e["pasos"] if p["id"] == id)


def test_solo_colombia_sin_sat_ni_ielts_y_con_saber_11(db):
    u = _estudiante(db, "co@e.dev", {**ONCE, "international_interest": "intl_no"})
    plan = svc.armar(db, u)
    ids = _ids(plan)
    assert "saber_11" in ids
    # I-5 · el paso lleva a la Práctica Saber 11.
    assert _paso(plan, "saber_11")["ruta"] == "/practica-examenes/saber11"
    for afuera in ("practica_ingles", "practica_sat", "examen_oficial", "carta_motivacion"):
        assert afuera not in ids


def test_afuera_con_estados_unidos_recibe_ielts_y_sat(db):
    u = _estudiante(db, "us@e.dev", {**ONCE, "international_interest": "intl_yes", "countries": ["usa"]})
    plan = svc.armar(db, u)
    ids = _ids(plan)
    assert {"practica_ingles", "practica_sat", "carta_motivacion"} <= set(ids)
    assert "saber_11" not in ids
    assert not _paso(plan, "practica_ingles")["detalle"].startswith("Si decides")


def test_afuera_sin_estados_unidos_no_recibe_sat(db):
    u = _estudiante(db, "es@e.dev", {**ONCE, "international_interest": "intl_yes", "countries": ["spain"]})
    ids = _ids(svc.armar(db, u))
    assert "practica_ingles" in ids
    assert "practica_sat" not in ids


def test_quizas_ve_lo_de_afuera_condicionado_y_tambien_el_saber_11(db):
    u = _estudiante(db, "qz@e.dev", {**ONCE, "international_interest": "intl_maybe"})
    plan = svc.armar(db, u)
    assert _paso(plan, "practica_ingles")["detalle"].startswith("Si decides")
    assert "saber_11" in _ids(plan)


def test_sin_decir_donde_le_pide_pensarlo(db):
    u = _estudiante(db, "nd@e.dev", ONCE)
    assert "decidir_donde" in _ids(svc.armar(db, u))


def test_once_con_colegio_hasta_doce_tiene_la_etapa_de_12(db):
    u = _estudiante(db, "c12@e.dev", ONCE, school_reported_last_grade=12)
    plan = svc.armar(db, u)
    assert plan["etapas"][1]["titulo"] == "En 12°"
    assert plan["encabezado"] == "Te quedan 11° y 12°"


def test_once_con_colegio_hasta_once_es_su_ultimo_ano(db):
    u = _estudiante(db, "c11@e.dev", ONCE, school_reported_last_grade=11)
    plan = svc.armar(db, u)
    assert plan["etapas"][1]["titulo"] == "En los próximos meses"
    assert plan["encabezado"] == "Este es tu último año de colegio"


def test_doce_es_su_ultimo_ano(db):
    plan = svc.armar(db, _estudiante(db, "d@e.dev", DOCE))
    assert plan["encabezado"] == "Este es tu último año de colegio"


def test_lo_hecho_sale_hecho(db):
    from app.db.models import VocationalTestResult

    u = _estudiante(db, "h@e.dev", ONCE, english_test_completed=True, english_cefr_level="B1")
    for t in ("istrong", "mbti", "bigfive"):
        db.add(VocationalTestResult(user_id=u.id, test_id=t, answers={}, scores={}))
    db.commit()
    plan = svc.armar(db, u)
    assert _paso(plan, "tests")["hecho"] and _paso(plan, "tests")["detalle"] == "3 de 3"
    assert _paso(plan, "ingles")["hecho"] and _paso(plan, "ingles")["detalle"] == "Tu nivel: B1"
    assert not _paso(plan, "rutas")["hecho"]


def test_nunca_publica_fechas_oficiales(db):
    u = _estudiante(db, "f@e.dev", {**ONCE, "international_interest": "intl_yes", "countries": ["usa"]})
    texto = str(svc.armar(db, u))
    meses = r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
    assert not re.search(meses, texto, re.IGNORECASE)
    assert not re.search(r"20\d\d", texto)


def _get(app, Sesion, email, respuestas, plan):
    s = Sesion()
    _estudiante(s, email, respuestas, plan)
    s.close()
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", json={"email": email, "password": "testpass123"})
        return c.get(
            "/api/v1/me/plan-preparacion",
            headers={"Authorization": f"Bearer {r.json()['access_token']}"},
        )


def test_http_pago_de_once_recibe_el_plan(app_db):
    app, Sesion = app_db
    r = _get(app, Sesion, "ok@e.dev", ONCE, "pago")
    assert r.status_code == 200
    assert [e["id"] for e in r.json()["etapas"]] == ["ahora", "despues", "antes_de_aplicar"]


def test_http_gratis_recibe_402(app_db):
    app, Sesion = app_db
    r = _get(app, Sesion, "gr@e.dev", ONCE, None)
    assert r.status_code == 402
    assert r.json()["detail"]["funcion"] == "plan_preparacion"


def test_http_noveno_no_es_de_su_grado(app_db):
    app, Sesion = app_db
    r = _get(app, Sesion, "n9@e.dev", {"life_stage": "high_school_early", "grade": "9"}, "pago")
    assert r.status_code == 402
    assert r.json()["detail"]["motivo"] == "no_es_de_su_grado"
