"""T-04 · Tests VARK (estilos de aprendizaje) y Motivadores Iniciales.

Contenido y algoritmo entregados por la clienta (PDF feedback Sprint 2,
págs. 15-19): conteo simple por variable, Regla de Oro de empates VARK
(diferencia 0-1 → Perfil Multimodal) y motivador primario/secundario con
fusión en empate absoluto.
"""
from __future__ import annotations

import pytest

from app.data.vocational_tests import (
    calculate_vocational_scores,
    get_all_tests_summary,
    get_test_by_id,
)
from app.services.scoring_service import (
    calculate_motivadores,
    calculate_vark,
    derive_test_extras,
)


# ── estructura del banco ────────────────────────────────────────────────────

@pytest.mark.parametrize("test_id,variables,n_opts", [
    ("vark", {"V", "A", "R", "K"}, 4),
    ("motivadores", {"LOG", "IMP", "AUT", "EST", "SEG"}, 5),
])
def test_banco_completo_y_bien_formado(test_id, variables, n_opts):
    test = get_test_by_id(test_id)
    assert test is not None
    qs = test["questions"]
    assert len(qs) == 5 == test["questionCount"]
    for q in qs:
        assert q["type"] == "forced_choice"
        opts = q["options"]
        assert len(opts) == n_opts
        assert {o["value"] for o in opts} == variables
        for o in opts:
            assert o["label"].strip()


def test_aparecen_en_el_summary():
    ids = {t["id"] for t in get_all_tests_summary()}
    assert {"vark", "motivadores"} <= ids


# ── scoring genérico forced_choice ──────────────────────────────────────────

def test_scores_forced_choice_son_porcentajes_de_conteo():
    answers = {"vk-1": "V", "vk-2": "V", "vk-3": "K", "vk-4": "R", "vk-5": "V"}
    scores = calculate_vocational_scores("vark", answers)
    assert scores == {"V": 60, "A": 0, "R": 20, "K": 20}


def test_scores_ignoran_respuestas_invalidas():
    scores = calculate_vocational_scores("vark", {"vk-1": "Z", "vk-2": None})
    assert scores == {"V": 0, "A": 0, "R": 0, "K": 0}


# ── VARK · Regla de Oro de empates ──────────────────────────────────────────

def test_vark_estilo_unico_cuando_hay_dominante_claro():
    # V=3, K=1, R=1 → diferencia top-segundo = 2 → estilo único
    r = calculate_vark({"vk-1": "V", "vk-2": "V", "vk-3": "V", "vk-4": "K", "vk-5": "R"})
    assert r["multimodal"] is False
    assert r["styles"] == ["V"]
    assert r["label"] == "Visual"


def test_vark_multimodal_en_empate_exacto():
    # V=2, K=2, A=1 → diferencia 0 → multimodal (ejemplo literal de la clienta)
    r = calculate_vark({"vk-1": "V", "vk-2": "V", "vk-3": "K", "vk-4": "K", "vk-5": "A"})
    assert r["multimodal"] is True
    assert r["styles"] == ["V", "K"]
    assert "Multimodal" in r["label"]
    assert "Visual" in r["label"] and "Kinest" in r["label"]


def test_vark_multimodal_con_diferencia_de_un_punto():
    # V=2, A=1, R=1, K=1 → top-segundo = 1 → multimodal
    r = calculate_vark({"vk-1": "V", "vk-2": "V", "vk-3": "A", "vk-4": "R", "vk-5": "K"})
    assert r["multimodal"] is True
    assert r["styles"][0] == "V"


# ── Motivadores · primario/secundario y fusión ─────────────────────────────

def test_motivador_primario_y_secundario():
    # AUT=3, LOG=2 → primario Autonomía, secundario Logro, sin fusión
    r = calculate_motivadores(
        {"mt-1": "AUT", "mt-2": "AUT", "mt-3": "AUT", "mt-4": "LOG", "mt-5": "LOG"}
    )
    assert r["fusion"] is False
    assert r["primary"] == "AUT"
    assert r["secondary"] == "LOG"
    assert "Autonomía" in r["headline"] and "Logro" in r["headline"]


def test_motivador_fusion_en_empate_absoluto():
    # LOG=2, IMP=2, SEG=1 → fusión "Logro con Impacto Social" (ejemplo de la clienta)
    r = calculate_motivadores(
        {"mt-1": "LOG", "mt-2": "LOG", "mt-3": "IMP", "mt-4": "IMP", "mt-5": "SEG"}
    )
    assert r["fusion"] is True
    assert r["primary"] == "LOG"
    assert r["secondary"] == "IMP"
    assert "Logro con Impacto Social" in r["headline"]


# ── integración extras ──────────────────────────────────────────────────────

def test_derive_extras_para_los_tests_nuevos():
    vark = derive_test_extras("vark", {"vk-1": "V"})
    assert vark and vark["kind"] == "vark" and vark["headline"]
    mot = derive_test_extras("motivadores", {"mt-1": "LOG"})
    assert mot and mot["kind"] == "motivadores" and mot["headline"]


def test_extras_traen_info_renderizable():
    """El front pinta headline + label + info sin lógica propia."""
    r = calculate_vark({"vk-1": "V", "vk-2": "V", "vk-3": "V", "vk-4": "V", "vk-5": "V"})
    assert r["style_info"][0]["name"] == "Visual"
    assert r["style_info"][0]["description"]
    assert r["style_info"][0]["tip"]
    m = calculate_motivadores({f"mt-{i}": "SEG" for i in range(1, 6)})
    assert m["motivator_info"][0]["name"] == "Seguridad y Estructura"
    assert m["counts"]["SEG"] == 5
