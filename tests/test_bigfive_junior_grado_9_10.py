"""Big Five juvenil (9° y 10°) · misma estructura, otra redacción (2026-11-02).

Lo que protege: que sea el MISMO instrumento con otras palabras. Mismos ids, misma
dimensión, mismos ítems invertidos (lo delicado de este test) y mismo puntaje con
las mismas respuestas. Y que el selector se lo dé a 9°/10° y no a 11°.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.data.bigfive_junior import (
    BIGFIVE_JUNIOR_DESCRIPTION,
    BIGFIVE_JUNIOR_QUESTIONS,
    get_bigfive_junior,
)
from app.data.vocational_tests import calculate_vocational_scores, get_test_by_id
from app.services import vocational_bank_selector as selector

ADULTO = get_test_by_id("bigfive")["questions"]


def test_mismos_ids_en_el_mismo_orden():
    assert [q["id"] for q in BIGFIVE_JUNIOR_QUESTIONS] == [q["id"] for q in ADULTO]


def test_misma_dimension_y_mismos_invertidos_por_item():
    for j, a in zip(BIGFIVE_JUNIOR_QUESTIONS, ADULTO):
        assert j["category"] == a["category"], j["id"]
        assert bool(j.get("reversed")) == bool(a.get("reversed")), j["id"]
        assert j["type"] == a["type"], j["id"]


def test_diez_items_por_dimension():
    for dim in "OCEAN":
        assert sum(1 for q in BIGFIVE_JUNIOR_QUESTIONS if q["category"] == dim) == 10


def test_todos_los_enunciados_fueron_reescritos_o_corregidos():
    adultos = {q["id"]: q["text"] for q in ADULTO}
    iguales = [q["id"] for q in BIGFIVE_JUNIOR_QUESTIONS if q["text"] == adultos[q["id"]]]
    # Algunos ya eran de lenguaje común ("No me gusta llamar la atención"); se
    # aceptan unos pocos iguales, no un banco copiado.
    assert len(iguales) <= 5, iguales


def test_enunciados_cortos_y_sin_voseo():
    for q in BIGFIVE_JUNIOR_QUESTIONS:
        texto = q["text"].strip()
        assert texto and len(texto) <= 120, q["id"]
        bajo = texto.lower()
        for mala in ("tenés", "querés", "podés", "sos", "vos", "usted"):
            assert not re.search(rf"\b{mala}\b", bajo), f"{q['id']} usa '{mala}'"
        for adulta in ("ideas abstractas", "rigurosamente", "alma de las fiestas", "perturbo"):
            assert adulta not in bajo, f"{q['id']} conserva '{adulta}'"


def test_get_bigfive_junior_hereda_metadatos_y_no_muta_el_canonico():
    junior = get_bigfive_junior()
    base = get_test_by_id("bigfive")
    assert junior["id"] == "bigfive" and junior["name"] == base["name"]
    assert junior["description"] == BIGFIVE_JUNIOR_DESCRIPTION != base["description"]
    assert junior["variant"] == "junior"
    assert get_test_by_id("bigfive")["questions"][0]["text"] == ADULTO[0]["text"]


def test_mismas_respuestas_mismo_puntaje_en_los_dos_bancos():
    """El chico de 10° y el de 11° que responden igual sacan lo mismo: los
    invertidos siguen invertidos. Un ordenado (C alto, sin cosas tiradas)."""
    respuestas = {}
    for q in ADULTO:
        if q["category"] == "C":
            respuestas[q["id"]] = 1 if q.get("reversed") else 5
        else:
            respuestas[q["id"]] = 3
    puntajes = calculate_vocational_scores("bigfive", respuestas)
    assert puntajes["C"] == 100
    # Y el banco juvenil usa los mismos ids: mismo dict de respuestas, mismo resultado.
    assert {q["id"] for q in BIGFIVE_JUNIOR_QUESTIONS} == set(respuestas)


def _usuario(grade=None, **answers):
    return SimpleNamespace(grade=grade, onboarding_answers=answers)


def test_el_selector_le_da_el_juvenil_a_9_y_10_y_el_adulto_a_11():
    assert selector.test_para_usuario("bigfive", _usuario(grade=10))["variant"] == "junior"
    assert selector.test_para_usuario("bigfive", _usuario(grade=9))["questions"][0]["text"] == BIGFIVE_JUNIOR_QUESTIONS[0]["text"]
    adulto = selector.test_para_usuario("bigfive", _usuario(grade=11))
    assert adulto["variant"] == "adulto" and adulto["questions"][0]["text"] == ADULTO[0]["text"]
    # Holland sigue igual que antes.
    assert selector.test_para_usuario("holland", _usuario(grade=10))["variant"] == "junior"


def test_el_resumen_muestra_la_descripcion_juvenil_en_10():
    resumen = {t["id"]: t for t in selector.resumen_tests_para_usuario(_usuario(grade=10))}
    assert resumen["bigfive"]["description"] == BIGFIVE_JUNIOR_DESCRIPTION
    assert resumen["bigfive"]["variant"] == "junior"
