"""R3-02 (feedback clienta 2026-07-08) · expertise de counselling en los prompts
de IA + des-sesgo internacional de la capa IA (el refocus de julio solo había
cubierto el front).

Contratos:
1. Los prompts que razonan sobre el estudiante (chat, recomendador,
   consolidación, rutas) incluyen el bloque EXPERTISE DE COUNSELLING
   (sistemas educativos IB/AP/SAT, escalas de notas, Best Fit, no asumir
   exterior).
2. Las personas de los prompts ya NO enmarcan todo como "internacional/
   exterior" (des-sesgo de la capa IA).
3. Todos siguen siendo renderizables con str.format (el bloque no introduce
   llaves sin escapar).
"""
from __future__ import annotations

import pytest

from app.core.ai_client import load_prompt

PROMPTS_CON_EXPERTISE = [
    "hop_chat",
    "recommend_programs",
    "consolidate_profile",
    "routes",
]

# frase sesgada vieja -> prompt donde vivía
_FRASES_SESGADAS = {
    "hop_chat": "intercambios y programas académicos internacionales",
    "reflection": "experiencias internacionales",
    "synthesis": "para estudiar o vivir en el exterior",
    "routes": "experto en educacion internacional",
    "advisor_brief": "asesores de educacion internacional",
}

PROMPTS_EDITADOS = sorted(set(PROMPTS_CON_EXPERTISE) | set(_FRASES_SESGADAS))


class _CualquierClave(dict):
    """format_map sin KeyError: cada placeholder se rellena con un dummy."""

    def __missing__(self, key):  # noqa: D105
        return "x"


@pytest.mark.parametrize("name", PROMPTS_CON_EXPERTISE)
def test_prompt_incluye_expertise_counselling(name):
    text = load_prompt(name)
    assert "EXPERTISE DE COUNSELLING" in text
    # señas distintivas del bloque (conocimiento de sistemas + best fit)
    assert "college counsellor" in text
    assert "NUNCA para inventar datos" in text


@pytest.mark.parametrize("name", ["hop_chat", "recommend_programs", "consolidate_profile"])
def test_bloque_completo_sistemas_educativos(name):
    """Los prompts principales llevan el bloque completo con sistemas y exámenes."""
    text = load_prompt(name)
    for token in ("Bachillerato Internacional IB", "SAT (400-1600)", "Best Fit"):
        assert token in text, f"{name} no incluye {token!r}"


@pytest.mark.parametrize("name", sorted(_FRASES_SESGADAS))
def test_persona_ya_no_esta_sesgada_a_internacional(name):
    text = load_prompt(name)
    assert _FRASES_SESGADAS[name] not in text, (
        f"{name} conserva la frase sesgada {_FRASES_SESGADAS[name]!r}"
    )


@pytest.mark.parametrize("name", PROMPTS_EDITADOS)
def test_prompt_sigue_renderizando_con_format(name):
    """ValueError aquí = llaves desbalanceadas introducidas por la edición."""
    text = load_prompt(name)
    rendered = text.format_map(_CualquierClave())
    assert rendered  # no explota y produce texto


def test_no_asumir_exterior_presente():
    """La regla de neutralidad (no asumir que quiere irse al exterior) está en
    los prompts que hablan con/sobre el estudiante."""
    for name in ("hop_chat", "recommend_programs", "consolidate_profile", "routes"):
        text = load_prompt(name)
        assert "nunca asumas que la persona quiere irse al exterior" in text.lower(), name
