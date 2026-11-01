"""H-4 · Sprint 4 · el chat de Hopper sabe en qué etapa va la persona.

Hopper le preguntaba "¿en qué etapa estás?" a una estudiante que ya había dicho
en el onboarding que va en 11°: el grado y la etapa no llegaban al chat (en el
journey viajan por otro bloque, que el chat no arma). Y los países solo salían
de una columna que no siempre se llena.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services import hop_chat_service as svc


def _u(respuestas, **extra):
    base = dict(
        onboarding_answers=respuestas, grade=None, budget_band=None, budget_max_usd=None,
        preferred_countries=[], english_cefr_level=None, role=None,
    )
    base.update(extra)
    return SimpleNamespace(**base)


def test_la_etapa_de_colegio_llega_al_chat():
    bloque = svc._build_constraints_block(_u({"life_stage": "high_school", "grade": "11"}))
    assert "Etapa: colegio, 11°" in bloque


def test_la_etapa_de_un_adulto_llega_en_palabras():
    bloque = svc._build_constraints_block(_u({"life_stage": "working"}))
    assert "Etapa: (sin información)" not in bloque


def test_los_paises_del_onboarding_llegan_si_la_columna_esta_vacia():
    bloque = svc._build_constraints_block(_u({"life_stage": "high_school", "grade": "11", "countries": ["germany"]}))
    assert "Alemania" in bloque


def test_sin_datos_lo_dice_explicito():
    bloque = svc._build_constraints_block(_u({}))
    assert "Etapa: (sin información)" in bloque
