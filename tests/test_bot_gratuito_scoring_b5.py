"""B-5 · Sprint 4 · el puntaje del bot gratuito es el del demo de Verónica.

Lo que protegen estos tests:
 1. Cada factor puntúa exactamente como `leadScore()` del demo.
 2. Los cortes: 6 caliente (asesor), 3-5 tibio (perfilamiento), < 3 frío
    (telemarketing).
 3. La escala de la bandeja (0-100) y el desglose con el valor sobre 8.
 4. Que el endpoint lo guarde y NO lo devuelva a la pantalla.
"""
from __future__ import annotations

import pytest

from app.services.bot_gratuito_scoring import puntuar


def _r(stage="11", budget="b2", dest="ext"):
    return {"who": "colegio", "stage": stage, "budget": budget, "dest": dest}


@pytest.mark.parametrize(
    "stage, puntos",
    [("9", 0), ("10", 1), ("11", 2), ("12", 2), ("grad", 2), ("u1", 2), ("u4", 2), ("p1", 2), ("p3", 2)],
)
def test_etapa(stage, puntos):
    # Los otros tres factores en 0, para aislar la etapa.
    v = puntuar(_r(stage=stage, budget="nose", dest="nose"), "later")
    assert v.puntos == puntos


@pytest.mark.parametrize("cuando, puntos", [("now", 2), ("soon", 2), ("year", 1), ("later", 0)])
def test_cuando(cuando, puntos):
    assert puntuar(_r(stage="9", budget="nose", dest="nose"), cuando).puntos == puntos


@pytest.mark.parametrize("budget, puntos", [("b2", 2), ("b3", 2), ("b1", 1), ("beca", 1), ("nose", 0)])
def test_presupuesto(budget, puntos):
    assert puntuar(_r(stage="9", budget=budget, dest="nose"), "later").puntos == puntos


@pytest.mark.parametrize("dest, puntos", [("ext", 2), ("both", 2), ("local", 1), ("nose", 0)])
def test_destino(dest, puntos):
    assert puntuar(_r(stage="9", budget="nose", dest=dest), "later").puntos == puntos


@pytest.mark.parametrize(
    "respuestas, cuando, puntos, banda, ruta",
    [
        # 2+2+2+2 = 8
        (_r(), "now", 8, "hot", "asesor"),
        # 2+0+2+2 = 6 · el corte exacto de caliente
        (_r(), "later", 6, "hot", "asesor"),
        # 1+0+2+2 = 5 · justo debajo
        (_r(stage="10"), "later", 5, "warm", "perfilamiento"),
        # 0+1+1+1 = 3 · el corte exacto de tibio
        (_r(stage="9", budget="b1", dest="local"), "year", 3, "warm", "perfilamiento"),
        # 0+0+1+1 = 2 · justo debajo
        (_r(stage="9", budget="b1", dest="local"), "later", 2, "cold", "telemercadeo"),
        # 0+0+0+0
        (_r(stage="9", budget="nose", dest="nose"), "later", 0, "cold", "telemercadeo"),
    ],
)
def test_cortes_y_rutas(respuestas, cuando, puntos, banda, ruta):
    v = puntuar(respuestas, cuando)
    assert (v.puntos, v.banda, v.ruta) == (puntos, banda, ruta)


def test_la_escala_de_la_bandeja_es_sobre_100():
    assert puntuar(_r(), "now").score == 100
    assert puntuar(_r(), "later").score == 75
    assert puntuar(_r(stage="9", budget="nose", dest="nose"), "later").score == 0


def test_el_desglose_dice_por_que_y_el_total_sobre_8():
    v = puntuar(_r(stage="10", budget="beca", dest="local"), "soon")
    assert v.motivos == [
        "+1 etapa: 10°",
        "+2 quiere iniciar en 1 a 3 meses",
        "+1 presupuesto: depende de una beca o un crédito",
        "+1 destino: en el país de origen",
        "total 5 de 8 (reglas del demo de Verónica)",
    ]


# ---------------------------------------------------------------------------
# Sobre el endpoint · reusa el fixture de B-4
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from tests.test_bot_gratuito_b4 import URL, _leads, _pedido, app_db  # noqa: E402,F401


def test_el_endpoint_guarda_el_puntaje_y_no_lo_devuelve(app_db):  # noqa: F811
    app, Sesion = app_db
    with TestClient(app) as c:
        r = c.post(URL, json=_pedido())  # 11° · 1-3 meses · 10-25k · exterior = 8
    assert r.status_code == 200
    assert set(r.json()) == {"lead_id", "siguiente_paso"}

    [lead] = _leads(Sesion)
    assert (lead.score, lead.band, lead.route) == (100, "hot", "asesor")
    assert lead.score_rationale[-1] == "total 8 de 8 (reglas del demo de Verónica)"
    assert lead.alarms == []
