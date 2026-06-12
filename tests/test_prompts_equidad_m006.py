"""M-006 (Fase C) · cláusula anti-sesgo en los prompts que generan
recomendaciones/análisis sobre estudiantes.

Texto aprobado por JP el 2026-06-12. Dos contratos:
1. Los 3 prompts (recomendador, clínico, consolidación) incluyen la
   REGLA DE EQUIDAD.
2. Siguen siendo renderizables con str.format (la cláusula no introduce
   llaves sin escapar — los prompts usan {{...}} para el JSON de ejemplo).
"""
from __future__ import annotations

import pytest

from app.core.ai_client import load_prompt

PROMPTS_CON_EQUIDAD = ["recommend_programs", "clinical_analysis", "consolidate_profile"]


class _CualquierClave(dict):
    """format_map sin KeyError: cada placeholder se rellena con un dummy."""

    def __missing__(self, key):  # noqa: D105
        return "x"


@pytest.mark.parametrize("name", PROMPTS_CON_EQUIDAD)
def test_prompt_incluye_regla_de_equidad(name):
    text = load_prompt(name)
    assert "REGLA DE EQUIDAD" in text
    assert "género, origen, apellido, colegio o nivel socioeconómico" in text


@pytest.mark.parametrize("name", PROMPTS_CON_EQUIDAD)
def test_prompt_sigue_renderizando_con_format(name):
    """ValueError aquí = llaves desbalanceadas introducidas por la cláusula."""
    text = load_prompt(name)
    rendered = text.format_map(_CualquierClave())
    assert "REGLA DE EQUIDAD" in rendered
    # las llaves escapadas {{...}} del JSON de ejemplo deben sobrevivir como {...}
    assert "{" in rendered
