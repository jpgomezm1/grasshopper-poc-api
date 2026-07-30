"""A1 · La lectura de IA tiene que VER el resultado del test, no solo los números.

Queja de la clienta: *"le salen como unas siglas y ya, pero no le explica: mira, eres
analítico, por eso te gustan estas cosas… qué significa eso para ti EN TU VIDA"*.

P1-1 construyó el motor de lectura y se declaró verificado **probando solo Holland** —
el único de los ocho tests que no tiene `_extras` ni dimensiones bipolares, o sea el
único donde el defecto era imposible de ver.

El defecto: `format_scores_block` filtraba `scores` a valores numéricos, y así
descartaba `_extras` entero. El modelo escribía la lectura de MBTI, iStrong, VARK y
Motivadores **sin conocer el resultado**: nunca vio el tipo de 4 letras, ni el código
de iStrong, ni la Regla de Oro Multimodal de VARK.

Dos consecuencias concretas que estos tests cierran:

  - **VARK**: la regla multimodal se evalúa sobre conteos, pero al prompt llegaban
    porcentajes. La IA podía narrar un estilo único dominante en la misma pantalla
    donde el sistema muestra "Perfil Multimodal".
  - **MBTI**: las dimensiones son bipolares. Pedir "las 3 más altas" sobre EI/SN/TF/JP
    no significa nada — a un introvertido marcado (EI=15) le daba como pilares las
    dimensiones donde MENOS se define, y nunca nombraba su tipo.

Como en el PDF, los `scores` se construyen con el motor real, no a mano.
"""
from __future__ import annotations

import pytest

from app.data.vocational_tests import calculate_vocational_scores, get_test_by_id
from app.services import test_interpretation_service as svc
from app.services.scoring_service import derive_test_extras

CON_EXTRAS = ["mbti", "istrong", "vark", "motivadores"]


def _scores(test_id: str, primera_opcion: bool = True) -> dict:
    test = get_test_by_id(test_id)
    respuestas = {}
    for i, q in enumerate(test["questions"]):
        opciones = q.get("options")
        if isinstance(opciones, list) and opciones:
            elegida = opciones[0] if primera_opcion else opciones[i % len(opciones)]
            respuestas[q["id"]] = (
                elegida.get("value") if isinstance(elegida, dict) else elegida
            )
        else:
            respuestas[q["id"]] = 3
    scores = calculate_vocational_scores(test_id, respuestas)
    extras = derive_test_extras(test_id, respuestas)
    if extras:
        scores["_extras"] = extras
    return scores


@pytest.mark.parametrize("test_id", CON_EXTRAS)
def test_el_modelo_recibe_el_resultado_y_no_solo_los_numeros(test_id):
    bloque = svc.format_scores_block(test_id, _scores(test_id))
    assert any(
        marca in bloque for marca in ("TIPO:", "ÁREAS DOMINANTES:", "RESULTADO:")
    ), f"'{test_id}': el bloque no trae el resultado interpretado\n{bloque}"


def test_mbti_le_dice_al_modelo_el_tipo_de_cuatro_letras():
    scores = _scores("mbti")
    tipo = scores["_extras"]["type"]
    bloque = svc.format_scores_block("mbti", scores)
    assert tipo in bloque
    # Y el nombre del tipo, para que no lo narre como una sigla.
    assert scores["_extras"]["type_info"]["name"] in bloque


def test_mbti_expresa_las_dimensiones_como_preferencia_no_como_ranking():
    """Es lo que arregla el problema de fondo: EI/SN/TF/JP son bipolares."""
    bloque = svc.format_scores_block("mbti", _scores("mbti"))
    assert "se inclina a" in bloque


def test_vark_multimodal_se_le_advierte_explicitamente_al_modelo():
    """Si no, puede narrar un estilo dominante mientras la pantalla dice
    "Perfil Multimodal"."""
    # Se busca un patrón de respuestas que produzca multimodal.
    for alterna in (False, True):
        scores = _scores("vark", primera_opcion=alterna)
        if scores["_extras"].get("multimodal"):
            bloque = svc.format_scores_block("vark", scores)
            assert "MULTIMODAL" in bloque
            assert "NO tiene un solo" in bloque
            return
    pytest.skip("ninguno de los dos patrones de respuesta produjo un perfil multimodal")


def test_istrong_manda_los_intereses_concretos_traducidos():
    scores = _scores("istrong")
    bloque = svc.format_scores_block("istrong", scores)
    assert "ÁREAS DOMINANTES:" in bloque
    # Nunca el código crudo de tres letras ni las claves tipo "I:tecnologia".
    assert scores["_extras"]["three_letter_code"] not in bloque
    assert "I:" not in bloque


def test_motivadores_manda_la_etiqueta_y_los_dos_motivadores():
    scores = _scores("motivadores")
    bloque = svc.format_scores_block("motivadores", scores)
    assert "RESULTADO:" in bloque
    assert "Motivador primario:" in bloque


def test_holland_no_cambia_porque_no_tiene_resultado_interpretado():
    """El test sobre el que se hizo la verificación original. No debe ganar ruido."""
    bloque = svc.format_scores_block("holland", _scores("holland"))
    for marca in ("TIPO:", "ÁREAS DOMINANTES:", "RESULTADO:"):
        assert marca not in bloque
    assert "Artístico" in bloque or "Realista" in bloque


def test_unos_extras_corruptos_no_rompen_la_lectura():
    """`_extras` viene de una columna JSON; si trae basura, la lectura tiene que
    seguir saliendo con los números."""
    for basura in ("texto", 42, [], None):
        bloque = svc.format_scores_block("mbti", {"EI": 60, "_extras": basura})
        assert "Extraversión / Introversión" in bloque


def test_extras_no_se_cuela_como_una_dimension_mas():
    bloque = svc.format_scores_block("mbti", _scores("mbti"))
    assert "- _extras" not in bloque


# ---------------------------------------------------------------------------
# La caché tiene que invalidarse · si no, nadie ve el arreglo
# ---------------------------------------------------------------------------


def test_la_version_del_prompt_subio():
    """El bloque de puntajes cambió pero `scores` no, así que sin subir la versión
    las lecturas viejas —escritas sin ver el resultado— se seguirían sirviendo de
    caché para siempre."""
    assert svc.PROMPT_VERSION != "interpret_test_v1"


def test_el_hash_depende_de_la_version_del_prompt():
    scores = _scores("mbti")
    antes = svc.scores_hash(scores)
    original = svc.PROMPT_VERSION
    try:
        svc.PROMPT_VERSION = "otra_version"
        assert svc.scores_hash(scores) != antes
    finally:
        svc.PROMPT_VERSION = original


def test_el_prompt_le_explica_al_modelo_que_hay_dimensiones_bipolares():
    from app.core.ai_client import load_prompt

    plantilla = load_prompt("interpret_test")
    # Se normalizan los espacios: el texto va justificado a 88 columnas y las frases
    # quedan partidas entre líneas.
    plano = " ".join(plantilla.split())
    assert "BIPOLARES" in plano.upper()
    assert "RESULTADO ya interpretado" in plano
    # Y la instrucción de no narrar un dominante cuando el perfil combina varios.
    assert "no lo describas como si tuviera uno solo" in plano.lower()
