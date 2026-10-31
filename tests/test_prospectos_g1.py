"""G-1 / G-2 · Sprint 4 · el panel de prospectos.

Tres sitios donde caía un prospecto, y el equipo solo veía uno (el quiz viejo
"se escribía y nadie lo leía"). Lo que protegen estos tests:
 1. Las tres fuentes llegan al mismo listado, con la misma forma.
 2. El bot gratuito llega con quién es, etapa, destino, presupuesto, cuándo y su
    porqué; el quiz llega SIN puntaje (no se le inventa uno).
 3. Filtros por fuente, banda, estado y fecha.
 4. El estado: derivado ("convertido" si ya tiene cuenta), y el que pone el
    equipo manda y queda en la auditoría.
 5. Si pidió activar su plan desde el muro de pago, se ve.
 6. El CSV trae lo filtrado y abre bien en Excel (BOM).
 7. Un estudiante no entra.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.test_bot_gratuito_b4 import URL, _pedido, app_db  # noqa: F401
from tests.test_planes_d1 import _usuario

API = "/api/v1/prospectos"


@pytest.fixture()
def panel(app_db):
    """Un prospecto de cada fuente y una comercial que los mira."""
    from app.db.models import BotConversation, LeadProfile, UserRole

    app, Sesion = app_db
    s = Sesion()
    _usuario(s, "comercial@g1.dev", role=UserRole.GH_COMMERCIAL)
    _usuario(s, "estudiante@g1.dev")
    s.add(BotConversation(
        name="Pedro Perfilador", email="pedro@correo.com", hechos={
            "ocupacion": "working", "inversion": "15k_30k", "cuando_viajar": "6_months",
            "destino_interes": ["canada"], "que_estudiar": "Una maestría en datos",
        }, transcript=[], is_completed=True, score=55, band="warm", route="telemercadeo",
        score_rationale=["presupuesto viable"],
    ))
    s.add(LeadProfile(
        name="Quinta Quiz", email="quinta@correo.com", answers={"q1": "a"},
        profile_result={"profile_name": "El Analista Metódico"},
        created_at=datetime.utcnow() - timedelta(days=60),
    ))
    s.commit()
    s.close()
    with TestClient(app) as c:
        r = c.post(URL, json=_pedido(contacto={
            "nombre": "Sara Gratuito", "whatsapp": "+57 300 000 0000",
            "email": "sara@correo.com", "cuando": "now",
        }))
        assert r.status_code in (200, 201), r.text
    return app, Sesion


def _h(c, email):
    r = c.post("/api/v1/auth/login", json={"email": email, "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _por_nombre(lista):
    return {p["nombre"]: p for p in lista}


def test_las_tres_fuentes_llegan_al_mismo_listado(panel):
    app, _ = panel
    with TestClient(app) as c:
        lista = c.get(API, headers=_h(c, "comercial@g1.dev")).json()
    p = _por_nombre(lista)
    assert {p[n]["fuente"] for n in p} == {"bot_gratuito", "perfilador", "quiz"}

    sara = p["Sara Gratuito"]
    assert sara["quien"] == "Estudiante de colegio"
    assert sara["etapa"] == "11°"
    assert sara["destino"] == "en el exterior"
    assert sara["presupuesto"] == "entre USD 10.000 y 25.000 al año"
    assert sara["cuando"] == "este mes"
    assert sara["puntaje"] is not None and sara["banda"] and sara["porque"]

    pedro = p["Pedro Perfilador"]
    assert pedro["presupuesto"] == "$15,000 - $30,000 USD"
    assert pedro["destino"] == "Canadá"

    quinta = p["Quinta Quiz"]
    assert quinta["resumen"] == "El Analista Metódico"
    # El quiz no puntuaba: no se le inventa un puntaje.
    assert quinta["puntaje"] is None and quinta["banda"] is None


def test_lo_mas_nuevo_va_arriba(panel):
    app, _ = panel
    with TestClient(app) as c:
        lista = c.get(API, headers=_h(c, "comercial@g1.dev")).json()
    fechas = [p["creado_en"] for p in lista]
    assert fechas == sorted(fechas, reverse=True)
    assert lista[-1]["fuente"] == "quiz"


@pytest.mark.parametrize(
    "consulta, esperados",
    [
        ("?fuente=quiz", {"Quinta Quiz"}),
        ("?fuente=perfilador", {"Pedro Perfilador"}),
        ("?banda=warm", {"Pedro Perfilador"}),
        ("?estado=nuevo", {"Sara Gratuito", "Pedro Perfilador", "Quinta Quiz"}),
    ],
)
def test_los_filtros(panel, consulta, esperados):
    app, _ = panel
    with TestClient(app) as c:
        lista = c.get(API + consulta, headers=_h(c, "comercial@g1.dev")).json()
    assert set(_por_nombre(lista)) == esperados


def test_filtro_por_fecha_deja_fuera_el_quiz_viejo(panel):
    app, _ = panel
    desde = (datetime.utcnow() - timedelta(days=7)).isoformat()
    with TestClient(app) as c:
        lista = c.get(API, params={"desde": desde}, headers=_h(c, "comercial@g1.dev")).json()
    assert "Quinta Quiz" not in _por_nombre(lista)


def test_si_ya_creo_cuenta_y_pidio_el_plan_se_ve_y_queda_convertido(panel):
    app, Sesion = panel
    from app.api.v1.admin_planes import PREFIJO_SOLICITUD

    s = Sesion()
    u = _usuario(s, "sara@correo.com")
    u.gh_contact_message = f"{PREFIJO_SOLICITUD} pago para tener los tests de mi grado."
    s.commit()
    s.close()
    with TestClient(app) as c:
        sara = _por_nombre(c.get(API, headers=_h(c, "comercial@g1.dev")).json())["Sara Gratuito"]
    assert sara["creo_cuenta"] is True
    assert sara["pidio_activar_plan"] is True
    assert sara["estado"] == "convertido" and sara["estado_manual"] is False


def test_el_estado_que_pone_el_equipo_manda_y_queda_auditado(panel):
    app, Sesion = panel
    from app.db.models import AuditLog

    with TestClient(app) as c:
        h = _h(c, "comercial@g1.dev")
        pedro = _por_nombre(c.get(API, headers=h).json())["Pedro Perfilador"]
        r = c.patch(f"{API}/perfilador/{pedro['id']}/estado", json={"estado": "contactado"}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "contactado" and r.json()["estado_manual"] is True
        # Una fuente equivocada no encuentra el prospecto.
        mal = c.patch(f"{API}/bot_gratuito/{pedro['id']}/estado", json={"estado": "descartado"}, headers=h)
        assert mal.status_code == 404
        # Un estado inventado no pasa.
        raro = c.patch(f"{API}/perfilador/{pedro['id']}/estado", json={"estado": "vendido"}, headers=h)
        assert raro.status_code == 422
        contactados = c.get(API + "?estado=contactado", headers=h).json()
    assert set(_por_nombre(contactados)) == {"Pedro Perfilador"}

    s = Sesion()
    [log] = s.query(AuditLog).filter(AuditLog.action == "prospecto.estado").all()
    assert log.payload == {"de": "nuevo", "a": "contactado"}
    s.close()


def test_un_descartado_sigue_descartado_aunque_se_registre(panel):
    """El estado puesto a mano manda sobre el derivado: fue una decisión."""
    app, Sesion = panel
    with TestClient(app) as c:
        h = _h(c, "comercial@g1.dev")
        quinta = _por_nombre(c.get(API, headers=h).json())["Quinta Quiz"]
        c.patch(f"{API}/quiz/{quinta['id']}/estado", json={"estado": "descartado"}, headers=h)
        s = Sesion()
        _usuario(s, "quinta@correo.com")
        s.close()
        quinta = _por_nombre(c.get(API, headers=h).json())["Quinta Quiz"]
    assert quinta["creo_cuenta"] is True
    assert quinta["estado"] == "descartado" and quinta["estado_manual"] is True


def test_el_csv_trae_lo_filtrado_y_abre_bien_en_excel(panel):
    app, _ = panel
    with TestClient(app) as c:
        r = c.get(API + "/csv?fuente=bot_gratuito", headers=_h(c, "comercial@g1.dev"))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    texto = r.content.decode("utf-8")
    assert texto.startswith("﻿")
    lineas = texto.lstrip("﻿").strip().splitlines()
    assert lineas[0].startswith("Fecha,Fuente,Nombre")
    assert len(lineas) == 2 and "Sara Gratuito" in lineas[1]


def test_un_estudiante_no_entra(panel):
    app, _ = panel
    with TestClient(app) as c:
        h = _h(c, "estudiante@g1.dev")
        assert c.get(API, headers=h).status_code == 403
        assert c.get(API + "/csv", headers=h).status_code == 403
