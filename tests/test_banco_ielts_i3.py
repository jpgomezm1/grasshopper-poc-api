"""I-3 · Sprint 4 · la ampliación del banco de IELTS (de 26 a 100).

Con la memoria de I-1, un banco de 26 se agota a la tercera tanda: es lo mismo
que le molestó del Pre SAT ("se repiten"). Lo que protegen estos tests:
 1. Cada habilidad ampliada tiene 25 ejercicios con los tres niveles cubiertos.
 2. Ningún ejercicio repite enunciado con otro.
"""
from __future__ import annotations

import pytest

from app.data import exam_prep as banco

AMPLIADAS = ["ielts_vocabulario", "ielts_gramatica"]


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
