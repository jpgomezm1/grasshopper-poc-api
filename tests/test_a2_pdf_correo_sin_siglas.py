"""A2 · El PDF que se manda por correo no puede imprimir siglas ni tarjetas vacías.

Queja literal de la clienta sobre el reporte que descargó:

    "Muestra solo barras con siglas — mbti SN/JP/TF/EI, Anclas LS/GM/AU/SE/EC/TF,
     istrong I:tecnologia…, Big Five con 'Neuroticismo 90%' crudo — sin ninguna
     explicación."

Se arregló primero **solo en el PDF del front**. El de WeasyPrint —el que se adjunta
al correo de la familia, que es el que ella descargó— quedó con:

  - `_TEST_LABELS` con tres claves que NO existen (`riasec`, `big5`, `anchors`) y sin
    las tres reales (`career-anchors`, `vark`, `motivadores`) → 3 de 8 tests salían
    impresos como "CAREER-ANCHORS" con descripción vacía.
  - `_highlight_for` devolviendo "—" para 6 de 8, y para los otros dos justamente las
    siglas de su queja ("SIA", "O · N").

El test que respaldaba eso (`test_pdf_service.py`) usaba formas de `scores` inventadas
que producción nunca genera, así que pasaba en verde.

**Estos tests construyen los scores con el motor real** (`calculate_vocational_scores`
+ `derive_test_extras`, lo mismo que corre el endpoint de submit). Si un test cambia de
forma, esto se entera.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.data.vocational_tests import (
    VOCATIONAL_TESTS,
    calculate_vocational_scores,
    get_test_by_id,
)
from app.services import pdf_service
from app.services.scoring_service import derive_test_extras

TEST_IDS = [t["id"] for t in VOCATIONAL_TESTS]


def _scores_reales(test_id: str) -> dict:
    """Reproduce lo que el endpoint de submit persiste en `scores`.

    Se responde cada pregunta con la primera opción disponible: da igual el perfil
    resultante, lo que importa es la FORMA del blob.
    """
    test = get_test_by_id(test_id)
    respuestas = {}
    for q in test["questions"]:
        opciones = q.get("options")
        if isinstance(opciones, list) and opciones:
            primera = opciones[0]
            valor = primera.get("value") if isinstance(primera, dict) else primera
        else:
            valor = 3  # escala Likert
        respuestas[q["id"]] = valor

    scores = calculate_vocational_scores(test_id, respuestas)
    extras = derive_test_extras(test_id, respuestas)
    if extras:
        scores["_extras"] = extras
    return scores


def _resultado(test_id: str):
    return SimpleNamespace(
        test_id=test_id,
        scores=_scores_reales(test_id),
        interpretation=None,
        interpretation_hash=None,
    )


# ---------------------------------------------------------------------------
# Etiquetas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("test_id", TEST_IDS)
def test_todos_los_tests_reales_tienen_nombre_legible(test_id):
    """Si falta uno, el PDF imprime el slug en mayúsculas. Fue el caso de
    career-anchors, vark y motivadores."""
    assert test_id in pdf_service._TEST_LABELS, (
        f"'{test_id}' cae al fallback y se imprimiría como '{test_id.upper()}'"
    )
    nombre, descripcion = pdf_service._TEST_LABELS[test_id]
    assert nombre
    # MBTI y VARK son acrónimos reconocidos y su nombre coincide con el slug en
    # mayúsculas; para el resto, coincidir con el slug significa que cayó al fallback.
    if test_id not in {"mbti", "vark"}:
        assert nombre != test_id.upper()
    assert descripcion, "sin descripción la tarjeta queda muda"


def test_no_quedan_claves_muertas_sin_marcar():
    """Las claves que no corresponden a ningún test real solo se aceptan como alias
    históricos declarados. Una clave muerta nueva es un `_TEST_LABELS` desalineado."""
    alias_conocidos = {"riasec", "big5", "anchors"}
    sobrantes = set(pdf_service._TEST_LABELS) - set(TEST_IDS) - alias_conocidos
    assert not sobrantes, f"claves que no son ningún test: {sobrantes}"


# ---------------------------------------------------------------------------
# Destacados · nombres, no siglas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("test_id", TEST_IDS)
def test_ningun_test_se_queda_sin_destacado(test_id):
    """Con datos reales, los 8 tienen algo legible que decir. Antes 6 de 8 devolvían
    "—"."""
    hl = pdf_service._highlight_for(test_id, _scores_reales(test_id))
    assert hl, f"'{test_id}' no produce destacado con datos reales"
    assert hl != "—"


@pytest.mark.parametrize("test_id", TEST_IDS)
def test_el_destacado_no_es_una_sigla_cruda(test_id):
    """El corazón de su queja. Un destacado válido tiene palabras, no un acrónimo.

    Se exceptúa el tipo MBTI (INFJ, ESTP…), que es un nombre reconocido — pero aun
    así tiene que ir acompañado de su descripción.
    """
    hl = pdf_service._highlight_for(test_id, _scores_reales(test_id))
    if test_id == "mbti":
        assert " · " in hl, f"el tipo MBTI debe ir explicado, no solo '{hl}'"
        return
    # Al menos una palabra de 4+ letras que NO sea todo mayúsculas → descarta
    # "SIA", "O · N", "LS · GM". "Realista", "Apertura" o "Logro" sí pasan.
    palabras = [p for p in hl.replace("·", " ").split() if p.isalpha()]
    assert any(
        len(p) >= 4 and not p.isupper() for p in palabras
    ), f"'{test_id}' devuelve algo que parece una sigla: '{hl}'"


def test_istrong_no_imprime_el_codigo_de_tres_letras():
    """`I:tecnologia` y el three_letter_code son literalmente lo que ella señaló."""
    hl = pdf_service._highlight_for("istrong", _scores_reales("istrong"))
    assert "I:" not in hl
    assert hl.upper() != hl, "parece un código en mayúsculas"


def test_bigfive_no_dice_neuroticismo():
    """P0-3 · el reencuadre tiene que valer también en el PDF del correo."""
    hl = pdf_service._highlight_for("bigfive", _scores_reales("bigfive")) or ""
    assert "neurotic" not in hl.lower()


def test_sin_scores_devuelve_None_y_no_un_guion():
    """`None` deja que la plantilla omita la línea; "—" imprime una tarjeta sin dato,
    que es peor que una sigla."""
    assert pdf_service._highlight_for("holland", {}) is None
    assert pdf_service._highlight_for("desconocido", {"X": 1}) is None


def test_extras_no_se_cuela_como_dimension():
    """`_extras` es un dict dentro de `scores`; si se colara al ranking numérico
    rompería el orden o imprimiría basura."""
    scores = _scores_reales("mbti")
    assert "_extras" in scores
    hl = pdf_service._highlight_for("mbti", scores)
    assert "_extras" not in (hl or "")


# ---------------------------------------------------------------------------
# La tarjeta completa
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("test_id", TEST_IDS)
def test_la_tarjeta_del_pdf_queda_completa(test_id):
    """Lo que de verdad ve la familia: nombre legible + descripción + destacado."""
    nombre, descripcion = pdf_service._TEST_LABELS[test_id]
    hl = pdf_service._highlight_for(test_id, _scores_reales(test_id))
    tarjeta = pdf_service.TestCard(
        name=nombre, highlight=hl, description=descripcion, reading=None
    )
    assert tarjeta.name and tarjeta.description and tarjeta.highlight
