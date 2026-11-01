"""E-4 · Sprint 4 · el kit de aplicación de 12°.

Lo que protegen estos tests:
 1. Los documentos dependen del destino (Colombia, afuera, EE. UU.).
 2. Crear, marcar, editar y borrar sobre HTTP; cambiar de país limpia lo que ya
    no aplica.
 3. Nadie puede ver, editar ni borrar la aplicación de otro (404).
 4. La llave: crear necesita plan pago y ser de 11° o 12°; LEER no (lo que ya
    armó sigue siendo suyo si baja de plan).
 5. Validaciones: país, documento desconocido, nombre vacío, máximo.
 6. Los avisos de fecha: 14 / 7 / 1 día, sin repetir, sin perderse si un día
    no corre, y otra vez si cambia la fecha.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.services import kit_aplicacion_service as kit
from tests.test_bot_gratuito_b4 import app_db  # noqa: F401
from tests.test_planes_d1 import _plan, _usuario

pytestmark = pytest.mark.planes_reales

DOCE = {"life_stage": "high_school", "grade": "12"}
URL = "/api/v1/me/aplicaciones"


def _estudiante(Sesion, email, respuestas=DOCE, plan="pago"):
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


# --- 1 · documentos por destino ----------------------------------------------


def test_colombia_pide_saber_11_y_cedula_y_no_pasaporte_ni_ingles():
    ids = kit.ids_validos("colombia")
    assert {"saber_11", "documento_identidad", "notas", "pago_inscripcion"} <= ids
    assert not ids & {"pasaporte", "ingles", "sat", "carta_motivacion"}


def test_afuera_pide_pasaporte_ingles_y_carta_y_no_saber_11():
    ids = kit.ids_validos("spain")
    assert {"pasaporte", "ingles", "carta_motivacion", "recomendaciones"} <= ids
    assert not ids & {"saber_11", "documento_identidad", "sat"}


def test_el_sat_solo_para_estados_unidos():
    assert "sat" in kit.ids_validos("usa")
    assert "sat" not in kit.ids_validos("canada")


def test_cada_pais_tiene_sus_documentos_sin_repetir():
    for pais in kit.PAISES:
        docs = [d["id"] for d in kit.documentos_para(pais)]
        assert len(docs) == len(set(docs)), pais


# --- 2 · HTTP ----------------------------------------------------------------


def test_crear_marcar_editar_y_borrar(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "k@e4.dev")
    with _cliente(app, "k@e4.dev") as c:
        r = c.post(URL, json={"universidad": "  U de Toronto ", "pais": "canada", "fecha_limite": "2027-01-15"})
        assert r.status_code == 201
        a = r.json()
        assert a["universidad"] == "U de Toronto"
        assert a["listos"] == 0 and a["total"] == len(kit.ids_validos("canada"))

        r = c.patch(f"{URL}/{a['id']}", json={"listos": ["pasaporte", "notas"]})
        assert r.json()["listos"] == 2

        # Cambiar a Colombia: el pasaporte deja de aplicar y deja de contar.
        r = c.patch(f"{URL}/{a['id']}", json={"pais": "colombia"})
        assert r.json()["listos"] == 1
        assert "saber_11" in [d["id"] for d in r.json()["documentos"]]

        r = c.patch(f"{URL}/{a['id']}", json={"sin_fecha": True})
        assert r.json()["fecha_limite"] is None

        lista = c.get(URL).json()
        assert [x["id"] for x in lista["aplicaciones"]] == [a["id"]]
        assert lista["aviso"]

        assert c.delete(f"{URL}/{a['id']}").status_code == 204
        assert c.get(URL).json()["aplicaciones"] == []


def test_ordena_por_fecha_y_las_sin_fecha_al_final(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "o@e4.dev")
    with _cliente(app, "o@e4.dev") as c:
        c.post(URL, json={"universidad": "Sin fecha", "pais": "colombia"})
        c.post(URL, json={"universidad": "Lejos", "pais": "colombia", "fecha_limite": "2027-06-01"})
        c.post(URL, json={"universidad": "Cerca", "pais": "colombia", "fecha_limite": "2027-02-01"})
        nombres = [a["universidad"] for a in c.get(URL).json()["aplicaciones"]]
    assert nombres == ["Cerca", "Lejos", "Sin fecha"]


# --- 3 · ajenas ----------------------------------------------------------------


def test_nadie_toca_la_aplicacion_de_otro(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "duena@e4.dev")
    _estudiante(Sesion, "otro@e4.dev")
    with _cliente(app, "duena@e4.dev") as c:
        aid = c.post(URL, json={"universidad": "Mía", "pais": "colombia"}).json()["id"]
    with _cliente(app, "otro@e4.dev") as c:
        assert c.get(URL).json()["aplicaciones"] == []
        assert c.patch(f"{URL}/{aid}", json={"universidad": "Robada"}).status_code == 404
        assert c.delete(f"{URL}/{aid}").status_code == 404
    with _cliente(app, "duena@e4.dev") as c:
        assert c.get(URL).json()["aplicaciones"][0]["universidad"] == "Mía"


# --- 4 · la llave --------------------------------------------------------------


def test_gratis_no_crea_pero_lee(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "g@e4.dev", plan=None)
    with _cliente(app, "g@e4.dev") as c:
        r = c.post(URL, json={"universidad": "X", "pais": "colombia"})
        assert r.status_code == 402
        assert r.json()["detail"]["funcion"] == "kit_aplicacion"
        assert c.get(URL).status_code == 200


def test_decimo_no_es_de_su_grado(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "d@e4.dev", {"life_stage": "high_school_early", "grade": "10"})
    with _cliente(app, "d@e4.dev") as c:
        r = c.post(URL, json={"universidad": "X", "pais": "colombia"})
    assert r.status_code == 402
    assert r.json()["detail"]["motivo"] == "no_es_de_su_grado"


def test_once_si_puede(app_db):
    """En Colombia muchos colegios terminan en 11°: ese es su año de aplicar."""
    app, Sesion = app_db
    _estudiante(Sesion, "once@e4.dev", {"life_stage": "high_school", "grade": "11"})
    with _cliente(app, "once@e4.dev") as c:
        assert c.post(URL, json={"universidad": "X", "pais": "colombia"}).status_code == 201


# --- 5 · validaciones -------------------------------------------------------


def test_validaciones(app_db):
    app, Sesion = app_db
    _estudiante(Sesion, "v@e4.dev")
    with _cliente(app, "v@e4.dev") as c:
        assert c.post(URL, json={"universidad": "X", "pais": "marte"}).status_code == 422
        assert c.post(URL, json={"universidad": "   ", "pais": "colombia"}).status_code == 422
        aid = c.post(URL, json={"universidad": "X", "pais": "colombia"}).json()["id"]
        # El pasaporte no es de Colombia.
        assert c.patch(f"{URL}/{aid}", json={"listos": ["pasaporte"]}).status_code == 422


def test_maximo_de_aplicaciones(app_db, monkeypatch):
    monkeypatch.setattr(kit, "MAX_APLICACIONES", 2)
    app, Sesion = app_db
    _estudiante(Sesion, "m@e4.dev")
    with _cliente(app, "m@e4.dev") as c:
        for i in range(2):
            assert c.post(URL, json={"universidad": f"U{i}", "pais": "colombia"}).status_code == 201
        assert c.post(URL, json={"universidad": "Otra", "pais": "colombia"}).status_code == 422


# --- 6 · avisos ------------------------------------------------------------


def _con_fecha(Sesion, uid, dias, hoy):
    from app.db.models import AplicacionUniversidad

    s = Sesion()
    a = AplicacionUniversidad(
        user_id=uid, universidad=f"U{dias}", pais="colombia",
        fecha_limite=hoy + timedelta(days=dias), listos=["notas"],
    )
    s.add(a)
    s.commit()
    aid = a.id
    s.close()
    return aid


def test_avisos_de_fecha(app_db):
    from scripts import avisar_fechas_aplicacion as avisos
    from app.db.models import AplicacionUniversidad, Notification

    _, Sesion = app_db
    hoy = date(2027, 1, 1)
    uid = _estudiante(Sesion, "av@e4.dev")
    _con_fecha(Sesion, uid, 30, hoy)   # muy lejos: nada
    aid = _con_fecha(Sesion, uid, 10, hoy)  # toca el de 14
    _con_fecha(Sesion, uid, -1, hoy)   # vencida: nada

    s = Sesion()
    lista = avisos.a_quien_avisar(s, hoy)
    assert [(a["aplicacion"].universidad, a["umbral"]) for a in lista] == [("U10", 14)]
    for a in lista:
        avisos.enviar(s, a)
    n = s.query(Notification).filter(Notification.user_id == uid).one()
    assert n.type == "aplicacion.fecha_cercana"
    assert n.data["navigate_to"] == "/aplicaciones"
    assert "en 10 días" in n.title
    assert "Te faltan" in n.body

    # Al día siguiente no repite.
    assert avisos.a_quien_avisar(s, hoy + timedelta(days=1)) == []
    # Si no corrió el día del umbral 7, el día 5 igual avisa (no se pierde).
    assert [a["umbral"] for a in avisos.a_quien_avisar(s, hoy + timedelta(days=5))] == [7]

    # Si cambia la fecha, se avisa contra la nueva.
    a = s.get(AplicacionUniversidad, aid)
    a.fecha_limite = hoy + timedelta(days=12)
    s.commit()
    assert [x["umbral"] for x in avisos.a_quien_avisar(s, hoy)] == [14]
    s.close()


def test_el_plan_de_preparacion_lleva_al_kit(app_db):
    from app.services import plan_preparacion_service as plan

    _, Sesion = app_db
    uid = _estudiante(Sesion, "pp@e4.dev")
    s = Sesion()
    from app.db.models import User

    p = plan.armar(s, s.get(User, uid))
    req = next(x for e in p["etapas"] for x in e["pasos"] if x["id"] == "requisitos")
    assert req["ruta"] == "/aplicaciones" and req["funcion"] == "kit_aplicacion"
    s.close()
