"""P1-1 · Lectura narrativa del resultado de cada test · Sprint 3 (2026-07-29).

Reclamo #1 de la clienta (A1): "cuando entro al resultado de los tests, le da muy
poca información sobre su resultado al estudiante... la idea es que cada test pueda
darle más información sobre él al estudiante Y SU FAMILIA".

Y en la reunión: "le salen como unas siglas y ya, pero no le explica... hay que darle
qué significa ese test y qué significa eso para ti EN TU VIDA".

Estos tests NO llaman a la IA: fijan el contrato de datos alrededor de ella (qué ve
el modelo, cuándo se cachea, cuándo se invalida).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import test_interpretation_service as svc


def _resultado(scores, interpretation=None, interpretation_hash=None):
    return SimpleNamespace(
        test_id="holland", scores=scores, user_id="u1",
        interpretation=interpretation, interpretation_hash=interpretation_hash,
        interpretation_generated_at=None,
    )


# ---------------------------------------------------------------------------
# Lo que ve el modelo · nunca una sigla cruda
# ---------------------------------------------------------------------------


def test_el_modelo_nunca_recibe_siglas_crudas():
    """Es literalmente la queja: "le salen unas siglas y ya"."""
    bloque = svc.format_scores_block("holland", {"A": 80, "E": 70, "S": 62})
    assert "Artístico" in bloque and "Emprendedor" in bloque and "Social" in bloque
    # las claves crudas no aparecen como etiqueta
    for linea in bloque.split("\n"):
        assert not linea.startswith("- A:")
        assert not linea.startswith("- E:")


def test_las_dimensiones_van_de_mayor_a_menor():
    """La más alta primero: es la que define la lectura."""
    bloque = svc.format_scores_block("holland", {"R": 35, "A": 80, "E": 70})
    assert bloque.index("Artístico") < bloque.index("Emprendedor") < bloque.index("Realista")


@pytest.mark.parametrize(
    "test_id,clave,esperado",
    [
        ("bigfive", "N", "Sensibilidad emocional"),   # P0-3 · reencuadre, no "Neuroticismo"
        ("career-anchors", "LS", "Estilo de vida"),
        ("mbti", "SN", "Sensorial / Intuitivo"),
        ("istrong", "I:tecnologia", "Tecnología y software"),
        ("values", "logro", "Logro"),
    ],
)
def test_cada_test_tiene_etiquetas_legibles(test_id, clave, esperado):
    """Las siglas que la clienta vio en el PDF (SN, LS, I:tecnologia) tienen que
    llegar traducidas también al prompt."""
    assert esperado in svc.format_scores_block(test_id, {clave: 70})


def test_una_dimension_sin_mapeo_no_rompe():
    bloque = svc.format_scores_block("holland", {"XX": 50})
    assert "XX" in bloque  # se degrada a la clave, pero no revienta


def test_scores_no_numericos_se_ignoran():
    bloque = svc.format_scores_block("holland", {"A": 80, "_extras": {"algo": 1}})
    assert "Artístico" in bloque and "_extras" not in bloque


# ---------------------------------------------------------------------------
# Caché · el punto es no pagar la IA dos veces, pero tampoco mostrar algo viejo
# ---------------------------------------------------------------------------


def test_sin_interpretacion_no_hay_cache():
    assert svc.get_cached(_resultado({"A": 80})) is None


def test_con_hash_coincidente_se_reusa():
    scores = {"A": 80}
    r = _resultado(scores, {"summary": "x"}, svc.scores_hash(scores))
    assert svc.get_cached(r) == {"summary": "x"}


def test_si_repite_el_test_la_lectura_se_regenera():
    """Sin esto, alguien repite un test y sigue leyendo la lectura del resultado
    anterior — que es peor que no tener lectura."""
    r = _resultado({"A": 80}, {"summary": "vieja"}, svc.scores_hash({"A": 80}))
    r.scores = {"A": 30}  # repitió el test y le dio distinto
    assert svc.get_cached(r) is None


def test_el_hash_incluye_la_version_del_prompt():
    """Al cambiar el prompt hay que poder invalidar todo lo cacheado."""
    h = svc.scores_hash({"A": 80})
    original = svc.PROMPT_VERSION
    try:
        svc.PROMPT_VERSION = "otra_version"
        assert svc.scores_hash({"A": 80}) != h
    finally:
        svc.PROMPT_VERSION = original


# ---------------------------------------------------------------------------
# Contrato con el prompt
# ---------------------------------------------------------------------------


def test_el_prompt_pide_lo_que_la_clienta_pidio():
    from app.core.ai_client import load_prompt

    p = load_prompt("interpret_test")
    for marcador in ("{scores_block}", "{student_context}", "for_family", "closing_question"):
        assert marcador in p, f"falta {marcador} en el prompt"


def test_el_prompt_prohibe_las_siglas_y_los_diagnosticos():
    from app.core.ai_client import load_prompt

    p = load_prompt("interpret_test").lower()
    assert "siglas" in p
    assert "diagnostiques" in p or "diagnóstico" in p
