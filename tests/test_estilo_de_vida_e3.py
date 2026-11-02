"""E-3 · Sprint 4 · el cuestionario de estilo de vida y presupuesto (11°).

Lo que protegen estos tests:
 1. El destino y los países usan las MISMAS opciones del onboarding (no copias).
 2. Validación: solo preguntas y opciones conocidas; "solo Colombia" borra países.
 3. El presupuesto NO va a `budget` ni a `user.budget_band` (que se sincroniza
    con Bitrix, el CRM del cliente).
 4. Lo que responde llega al prompt (`format_onboarding_context`): escribir sin
    leer es el error #1 de este repo.
 5. La lectura del final: según lo que respondió, y sin cifras de costos.
 6. El plan de preparación lo usa (paso hecho, y el aviso de becas).
 7. Sobre HTTP: leer sin llave; guardar con plan pago y en 11°–12°.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.data.onboarding_hechos import HECHOS
from app.services import estilo_de_vida_service as svc
from tests.test_bot_gratuito_b4 import app_db  # noqa: F401
from tests.test_planes_d1 import _plan, _usuario

pytestmark = pytest.mark.planes_reales

ONCE = {"life_stage": "high_school", "grade": "11"}
URL = "/api/v1/me/estilo-de-vida"

COMPLETAS = {
    "international_interest": "intl_yes",
    "countries": ["spain"],
    "estilo_vivienda": "residencia",
    "estilo_ciudad": "grande",
    "presupuesto_familiar": "hasta_10k",
    "financiacion": "beca",
    "trabajar_estudiando": "si",
}


# --- 1-2 ----------------------------------------------------------------------


def test_destino_y_paises_usan_las_opciones_del_onboarding():
    por_id = {p["id"]: p for p in svc.preguntas_base()}
    hechos = {h.id: h for h in HECHOS}
    assert por_id["international_interest"]["opciones"] == dict(hechos["international_interest"].opciones)
    assert por_id["countries"]["opciones"] == dict(hechos["countries"].opciones)


def test_validar():
    with pytest.raises(ValueError):
        svc.validar({"inventada": "x"})
    with pytest.raises(ValueError):
        svc.validar({"presupuesto_familiar": "un_millon"})
    with pytest.raises(ValueError):
        svc.validar({"countries": ["marte"]})
    assert svc.validar({"international_interest": "intl_no", "countries": ["usa"]})["countries"] == []


# --- 4-5 ----------------------------------------------------------------------


def test_llega_al_prompt():
    from app.services.ai_service import format_onboarding_context

    texto = format_onboarding_context(dict(COMPLETAS))
    assert "Hasta USD 10.000 al año" in texto
    assert "Dependo de una beca" in texto
    assert "En una residencia universitaria" in texto
    assert "lo respondió con su familia" in texto


def test_lectura_segun_lo_que_respondio():
    lineas = " ".join(svc.lectura(COMPLETAS))
    assert "beca o un crédito" in lineas
    assert "con ese presupuesto" in lineas
    assert "visa de estudiante" in lineas
    no_hablado = " ".join(svc.lectura({**COMPLETAS, "presupuesto_familiar": "no_hablado", "financiacion": "familia",
                                       "trabajar_estudiando": "no"}))
    assert "Hablen en familia" in no_hablado
    assert "visa" not in no_hablado
    assert svc.lectura({"estilo_ciudad": "grande"}) == []  # incompleto: nada


def test_la_lectura_no_inventa_costos():
    todas = " ".join(svc.lectura(COMPLETAS) + svc.lectura({**COMPLETAS, "financiacion": "no_hablado"}))
    assert not re.search(r"\d", todas)


# --- 3, 6-7 · HTTP ------------------------------------------------------------


def _estudiante(Sesion, email, respuestas=ONCE, plan="pago"):
    s = Sesion()
    u = _usuario(s, email)
    u.onboarding_answers = dict(respuestas)
    s.commit()
    if plan:
        _plan(s, u, plan, datetime.utcnow() - timedelta(days=1))
    uid = u.id
    s.close()
    return uid


def _cliente(app, email):
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"email": email, "password": "testpass123"})
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c


def test_http_guardar_y_no_tocar_bitrix(app_db):
    from app.db.models import User

    app, Sesion = app_db
    uid = _estudiante(Sesion, "e@e3.dev")
    with _cliente(app, "e@e3.dev") as c:
        antes = c.get(URL).json()
        assert antes["respondido"] is False and antes["lectura"] == []
        r = c.put(URL, json={"respuestas": COMPLETAS})
    assert r.status_code == 200, r.text
    assert r.json()["respondido"] is True
    s = Sesion()
    u = s.get(User, uid)
    assert u.onboarding_answers["presupuesto_familiar"] == "hasta_10k"
    assert u.onboarding_answers["grade"] == "11"  # no pisa lo que ya estaba
    assert "budget" not in u.onboarding_answers
    assert u.budget_band is None and u.budget_max_usd is None
    s.close()


def test_http_respuesta_invalida_422(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "i@e3.dev")
    with _cliente(app, "i@e3.dev") as c:
        assert c.put(URL, json={"respuestas": {"financiacion": "loteria"}}).status_code == 422


def test_http_gratis_lee_pero_no_guarda(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "g@e3.dev", plan=None)
    with _cliente(app, "g@e3.dev") as c:
        assert c.get(URL).status_code == 200
        r = c.put(URL, json={"respuestas": {"estilo_ciudad": "grande"}})
    assert r.status_code == 402
    assert r.json()["detail"]["funcion"] == "estilo_de_vida"


def test_http_decimo_no_es_de_su_grado(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "d@e3.dev", {"life_stage": "high_school_early", "grade": "10"})
    with _cliente(app, "d@e3.dev") as c:
        r = c.put(URL, json={"respuestas": {"estilo_ciudad": "grande"}})
    assert r.status_code == 402
    assert r.json()["detail"]["motivo"] == "no_es_de_su_grado"


def test_el_plan_de_preparacion_lo_usa(app_db):
    from app.db.models import User
    from app.services import plan_preparacion_service as plan

    _, Sesion = app_db
    uid = _estudiante(Sesion, "p@e3.dev")
    s = Sesion()
    u = s.get(User, uid)

    def paso(p, pid):
        return next(x for e in p["etapas"] for x in e["pasos"] if x["id"] == pid)

    p = plan.armar(s, u)
    assert paso(p, "estilo_de_vida")["hecho"] is False
    assert paso(p, "financiacion")["detalle"] is None
    svc.guardar(s, u, COMPLETAS)
    p = plan.armar(s, u)
    assert paso(p, "estilo_de_vida")["hecho"] is True
    assert "beca o un crédito" in paso(p, "financiacion")["detalle"]
    s.close()


def test_http_el_dashboard_sabe_si_ya_lo_respondio(app_db):
    """Recorridos Sprint 4 · la guía del inicio lo marca "hecho" con este dato."""
    app, Sesion = app_db
    _estudiante(Sesion, "dash@e3.dev")
    with _cliente(app, "dash@e3.dev") as c:
        assert c.get("/api/v1/me/dashboard").json()["estilo_de_vida_respondido"] is False
        c.put(URL, json={"respuestas": COMPLETAS})
        assert c.get("/api/v1/me/dashboard").json()["estilo_de_vida_respondido"] is True
