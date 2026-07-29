"""P1-3 · El onboarding llega al perfil, al clínico y al recomendador · Sprint 3.

Causa raíz de la queja de Sandra: "todas las preguntas que me hizo al loguearse e
iniciar, pareciera que nada de eso lo usara, o quedara guardado, o lo usara la IA".

Tenía razón a medias, y la mitad mala era la que importaba: el onboarding entraba a
4 prompts (reflection, synthesis, routes, chat de Hop) pero NO al perfil consolidado,
NO al análisis clínico y NO al motor de recomendación — justamente los tres que
deciden qué se le muestra y qué se le recomienda.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.v1.auth import _sync_onboarding_to_user_columns


def _user(**kw):
    base = dict(budget_band=None, budget_max_usd=None, preferred_countries=None)
    base.update(kw)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# El presupuesto y los países dejan de ser datos muertos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor,band,techo",
    [
        ("under_5k", "bajo", 5000),
        ("5k_15k", "medio", 15000),
        ("15k_30k", "alto", 30000),
        ("over_30k", "alto", None),
    ],
)
def test_el_presupuesto_del_onboarding_llega_a_las_columnas(valor, band, techo):
    """El recomendador lee user.budget_band / budget_max_usd; el onboarding
    preguntaba el presupuesto y nadie escribía esas columnas."""
    u = _user()
    _sync_onboarding_to_user_columns(u, {"budget": valor})
    assert u.budget_band == band
    assert u.budget_max_usd == techo


def test_no_se_todavia_no_inventa_una_banda_de_presupuesto():
    """Mismo criterio de P1-19: 'no sé' NO es un dato, es la ausencia de uno."""
    u = _user()
    _sync_onboarding_to_user_columns(u, {"budget": "unknown"})
    assert u.budget_band is None
    assert u.budget_max_usd is None


def test_los_paises_usan_los_nombres_del_catalogo():
    """El recomendador hace `preferred_countries & countries` contra Program.country,
    que en la BD real son 'Canada', 'USA', 'UK'... Cualquier otra grafía no
    intersecta con nada y el filtro queda mudo."""
    u = _user()
    _sync_onboarding_to_user_columns(u, {"countries": ["canada", "uk", "usa"]})
    assert u.preferred_countries == ["Canada", "UK", "USA"]


def test_pais_otro_se_omite_en_vez_de_adivinarse():
    u = _user()
    _sync_onboarding_to_user_columns(u, {"countries": ["other"]})
    assert u.preferred_countries is None


def test_no_revienta_con_respuestas_vacias_o_raras():
    u = _user()
    for basura in ({}, {"budget": "xxx"}, {"countries": "no-es-lista"}, None):
        _sync_onboarding_to_user_columns(u, basura)
    assert u.budget_band is None


# ---------------------------------------------------------------------------
# El perfil consolidado por fin ve lo que la persona contó
# ---------------------------------------------------------------------------


def test_el_prompt_del_perfil_incluye_lo_que_conto_el_estudiante():
    from app.services.consolidation_service import render_consolidate_prompt

    inputs = {
        "demographic": {"life_stage": "Terminando el colegio"},
        "tests": [],
        "journey_answers": {},
        "onboarding": {
            "voice_passion": "Me apasiona el maquillaje artístico y el diseño de modas",
            "voice_concerns": "Me preocupa que mis papás prefieran algo más tradicional",
        },
    }
    prompt = render_consolidate_prompt(inputs)
    assert "maquillaje artístico" in prompt
    assert "mis papás prefieran algo más tradicional" in prompt


def test_cambiar_el_onboarding_invalida_la_cache_del_perfil():
    """Si el onboarding no entrara al hash, un estudiante podría reescribir todo lo
    que contó y seguir viendo el perfil viejo durante 24h."""
    from app.services.consolidation_service import hash_inputs

    base = {"user_id": "u1", "demographic": {}, "tests": [], "journey_answers": {}}
    a = hash_inputs({**base, "onboarding": {"voice_passion": "diseño de modas"}})
    b = hash_inputs({**base, "onboarding": {"voice_passion": "ingeniería civil"}})
    assert a != b


def test_el_analisis_clinico_recibe_las_preocupaciones():
    """`voice_concerns` es "¿hay algo que te preocupe sobre tu futuro?" — la pregunta
    más relevante que hacemos, y la psicóloga no la estaba viendo."""
    from app.services.ai_service import format_onboarding_context

    bloque = format_onboarding_context(
        {"voice_concerns": "Me da miedo equivocarme y decepcionar a mi familia"}
    )
    assert "decepcionar a mi familia" in bloque
