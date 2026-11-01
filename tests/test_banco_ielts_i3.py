"""I-3 · Sprint 4 · la ampliación del banco de IELTS (de 26 a 100).

Con la memoria de I-1, un banco de 26 se agota a la tercera tanda: es lo mismo
que le molestó del Pre SAT ("se repiten"). Lo que protegen estos tests:
 1. Cada habilidad ampliada tiene 25 ejercicios con los tres niveles cubiertos.
 2. Ningún ejercicio repite enunciado con otro.
"""
from __future__ import annotations

import pytest

from app.data import exam_prep as banco

AMPLIADAS = ["ielts_vocabulario", "ielts_gramatica", "ielts_lectura", "ielts_escritura"]


@pytest.mark.parametrize("habilidad", AMPLIADAS)
def test_cada_habilidad_ampliada_tiene_25_y_los_tres_niveles(habilidad):
    items = banco.items(skill_id=habilidad)
    assert len(items) == 25
    por_nivel = {}
    for i in items:
        por_nivel[i["level"]] = por_nivel.get(i["level"], 0) + 1
    assert por_nivel == {
        banco.NIVEL_FUNDAMENTOS: 9,
        banco.NIVEL_INTERMEDIO: 9,
        banco.NIVEL_AVANZADO: 7,
    }


def test_ningun_enunciado_de_ielts_se_repite():
    enunciados = [i["question"] for i in banco.items(exam_id="ielts")]
    assert len(enunciados) == len(set(enunciados))


def test_el_banco_de_ielts_llega_a_100():
    assert len(banco.items(exam_id="ielts")) == 100


# True/False/Not Given · (frase del texto que respalda o contradice, respuesta).
# Para "Not Given", el término clave NO debe aparecer en el texto.
_TFNG = {
    "ielts-read-10": ("uses far less energy than the older approach of boiling", "True"),
    "ielts-read-15": ("A language rarely disappears suddenly", "False"),
    "ielts-read-17": ("only stays alive if children continue to learn it at home", "False"),
    "ielts-read-19": ("employees keep their full salary", "False"),
    "ielts-read-22": ("sheds fibres in the washing machine", "True"),
}
_NOT_GIVEN = {
    "ielts-read-11": ["Asia"],
    "ielts-read-24": ["banned", "ban "],
}


@pytest.mark.parametrize("item_id", sorted(_TFNG))
def test_true_y_false_estan_respaldados_por_una_frase_del_texto(item_id):
    frase, respuesta = _TFNG[item_id]
    item = banco.get_item(item_id)
    assert item["correct"] == respuesta
    assert frase in banco.texto(item["passage_id"])


@pytest.mark.parametrize("item_id", sorted(_NOT_GIVEN))
def test_not_given_no_aparece_en_el_texto(item_id):
    item = banco.get_item(item_id)
    assert item["correct"] == "Not Given"
    texto = banco.texto(item["passage_id"])
    for clave in _NOT_GIVEN[item_id]:
        assert clave not in texto, clave


def test_las_de_detalle_estan_escritas_en_el_texto():
    claves = {
        "ielts-read-9": "pumping water at high pressure requires a great deal of electricity",
        "ielts-read-12": "greatest after sunset",
        "ielts-read-13": "light colours reflect more sunlight",
        "ielts-read-18": "most chose to continue the arrangement",
        "ielts-read-21": "most come from larger objects that break down over time",
    }
    for item_id, frase in claves.items():
        assert frase in banco.texto(banco.get_item(item_id)["passage_id"]), item_id


def test_cada_texto_nuevo_tiene_al_menos_dos_preguntas():
    nuevos = ("desalination", "urban_heat", "language_loss", "four_day_week", "microplastics")
    for t in nuevos:
        assert len([i for i in banco.items(skill_id="ielts_lectura") if i["passage_id"] == t]) >= 2, t
