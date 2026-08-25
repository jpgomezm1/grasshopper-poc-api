"""Holland adaptado a 13-14 años · paridad del instrumento + selección de banco.

Estos tests son la garantía de que la adaptación de lenguaje NO tocó el
instrumento: mismo número de ítems, misma dimensión por ítem, mismo puntaje.
Si alguien agrega, quita o re-clasifica una pregunta del banco junior, esta
suite falla — que es justo lo que evita repetir el episodio del test de inglés
(preguntas inventadas presentadas como instrumento).
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.vocational_tests import get_test, list_tests
from app.data.holland_junior import (
    HOLLAND_JUNIOR_QUESTIONS,
    VARIANT_ADULTO,
    VARIANT_JUNIOR,
    get_holland_junior,
)
from app.data.vocational_tests import calculate_vocational_scores, get_test_by_id
from app.services import vocational_bank_selector as selector

DIMENSIONES = ("R", "I", "A", "S", "E", "C")


def _adulto():
    return get_test_by_id("holland")


def _usuario(grade=None, onboarding_answers=None):
    """Estudiante mínimo: sólo lo que el selector necesita leer."""
    return SimpleNamespace(
        id="u-test",
        grade=grade,
        onboarding_answers=onboarding_answers or {},
    )


# ---------------------------------------------------------------------------
# 1 · Paridad estructural · el instrumento sigue siendo Holland
# ---------------------------------------------------------------------------


def test_mismo_numero_de_items():
    adulto = _adulto()["questions"]
    assert len(HOLLAND_JUNIOR_QUESTIONS) == len(adulto) == 48


def test_mismos_ids_en_el_mismo_orden():
    """Los ids iguales son lo que hace que el scoring no necesite saber nada.

    El front manda `{item_id: valor}`; si un id del banco junior no existiera en
    el canónico, esa respuesta se descartaría silenciosamente y el puntaje de esa
    dimensión bajaría sin que nadie se entere.
    """
    ids_junior = [q["id"] for q in HOLLAND_JUNIOR_QUESTIONS]
    ids_adulto = [q["id"] for q in _adulto()["questions"]]
    assert ids_junior == ids_adulto


def test_misma_dimension_por_item():
    por_id_adulto = {q["id"]: q["category"] for q in _adulto()["questions"]}
    for q in HOLLAND_JUNIOR_QUESTIONS:
        assert q["category"] == por_id_adulto[q["id"]], (
            f"El ítem {q['id']} cambió de dimensión: "
            f"{por_id_adulto[q['id']]} -> {q['category']}"
        )


def test_ocho_items_por_dimension_en_ambos_bancos():
    for banco in (HOLLAND_JUNIOR_QUESTIONS, _adulto()["questions"]):
        conteo = {d: 0 for d in DIMENSIONES}
        for q in banco:
            conteo[q["category"]] += 1
        assert conteo == {d: 8 for d in DIMENSIONES}


def test_mismo_tipo_y_sin_items_invertidos():
    """Holland puntúa directo (1-5). Un `reversed` colado invertiría el puntaje."""
    por_id_adulto = {q["id"]: q for q in _adulto()["questions"]}
    for q in HOLLAND_JUNIOR_QUESTIONS:
        assert q["type"] == por_id_adulto[q["id"]]["type"] == "likert"
        assert q.get("reversed") is None
        assert por_id_adulto[q["id"]].get("reversed") is None


def test_metadatos_heredados_del_banco_canonico():
    junior = get_holland_junior()
    adulto = _adulto()
    for clave in ("id", "slug", "name", "shortName", "academicBasis", "icon"):
        assert junior[clave] == adulto[clave]
    # questionCount es metadato de UI; si no coincide con los ítems reales, la
    # barra de progreso miente.
    assert junior["questionCount"] == len(junior["questions"]) == 48


def test_no_hay_ids_repetidos_en_el_banco_junior():
    ids = [q["id"] for q in HOLLAND_JUNIOR_QUESTIONS]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# 2 · La adaptación de lenguaje sí ocurrió
# ---------------------------------------------------------------------------


def test_todos_los_enunciados_fueron_reescritos():
    por_id_adulto = {q["id"]: q["text"] for q in _adulto()["questions"]}
    iguales = [
        q["id"] for q in HOLLAND_JUNIOR_QUESTIONS
        if q["text"].strip() == por_id_adulto[q["id"]].strip()
    ]
    assert not iguales, f"Ítems sin adaptar: {iguales}"


def test_enunciados_no_vacios_y_de_largo_razonable():
    for q in HOLLAND_JUNIOR_QUESTIONS:
        texto = q["text"].strip()
        assert texto
        # Un enunciado larguísimo se vuelve un párrafo y el chico deja de leerlo.
        assert len(texto) <= 120, f"{q['id']} quedó muy largo ({len(texto)})"


def test_sin_voseo_ni_jerga_de_adulto():
    """Español neutro de tú, y sin el vocabulario de oficina que ella criticó."""
    # Palabras sueltas: con frontera de palabra, si no "archivos" dispara "vos".
    palabras_prohibidas = ("tenés", "querés", "podés", "sos", "vos", "usted")
    frases_prohibidas = (
        "entorno estructurado", "ambientes de trabajo", "ambiente laboral",
        "tareas administrativas", "maquinaria pesada", "hipótesis",
    )
    for q in HOLLAND_JUNIOR_QUESTIONS:
        bajo = q["text"].lower()
        for mala in palabras_prohibidas:
            assert not re.search(rf"\b{mala}\b", bajo), f"{q['id']} usa '{mala}'"
        for frase in frases_prohibidas:
            assert frase not in bajo, f"{q['id']} contiene '{frase}'"


def test_la_descripcion_junior_es_distinta_y_aclara_que_es_el_mismo_test():
    junior = get_holland_junior()
    assert junior["description"] != _adulto()["description"]
    assert "mismo test" in junior["description"].lower()


def test_get_holland_junior_no_muta_el_banco_canonico():
    """Devuelve copias: si el endpoint tocara el dict compartido, el siguiente
    estudiante (adulto) heredaría las preguntas del anterior."""
    junior = get_holland_junior()
    junior["questions"][0]["text"] = "MUTADO"
    junior["name"] = "MUTADO"

    adulto = _adulto()
    assert adulto["name"] != "MUTADO"
    assert adulto["questions"][0]["text"] != "MUTADO"
    assert HOLLAND_JUNIOR_QUESTIONS[0]["text"] != "MUTADO"


# ---------------------------------------------------------------------------
# 3 · Puntúa igual · las respuestas del banco junior entran al scoring de siempre
# ---------------------------------------------------------------------------


def test_respuestas_del_banco_junior_puntuan_con_el_test_canonico():
    todo_5 = {q["id"]: 5 for q in HOLLAND_JUNIOR_QUESTIONS}
    scores = calculate_vocational_scores("holland", todo_5)
    assert scores == {d: 100 for d in DIMENSIONES}

    todo_1 = {q["id"]: 1 for q in HOLLAND_JUNIOR_QUESTIONS}
    assert calculate_vocational_scores("holland", todo_1) == {d: 20 for d in DIMENSIONES}


def test_una_dimension_alta_se_refleja_en_esa_dimension():
    respuestas = {
        q["id"]: (5 if q["category"] == "A" else 1)
        for q in HOLLAND_JUNIOR_QUESTIONS
    }
    scores = calculate_vocational_scores("holland", respuestas)
    assert scores["A"] == 100
    assert all(scores[d] == 20 for d in DIMENSIONES if d != "A")


def test_mismas_respuestas_mismo_puntaje_en_los_dos_bancos():
    """La equivalencia que le importa a la clienta: el chico de 9° y el de 11°
    que responden lo mismo obtienen el mismo perfil RIASEC."""
    valores = [1, 2, 3, 4, 5, 4, 3, 2]
    desde_junior = {
        q["id"]: valores[i % len(valores)]
        for i, q in enumerate(HOLLAND_JUNIOR_QUESTIONS)
    }
    desde_adulto = {
        q["id"]: valores[i % len(valores)]
        for i, q in enumerate(_adulto()["questions"])
    }
    assert calculate_vocational_scores("holland", desde_junior) == (
        calculate_vocational_scores("holland", desde_adulto)
    )


# ---------------------------------------------------------------------------
# 4 · Selección del banco según la ruta del estudiante
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("grado,esperado", [
    (9, VARIANT_JUNIOR),
    (10, VARIANT_JUNIOR),
    (11, VARIANT_ADULTO),
    (12, VARIANT_ADULTO),
    (None, VARIANT_ADULTO),   # profesional o todavía no lo dijo
])
def test_variante_segun_columna_grade(grado, esperado):
    assert selector.variante_para(_usuario(grade=grado)) == esperado


@pytest.mark.parametrize("valor,esperado", [
    ("9", VARIANT_JUNIOR),
    ("10", VARIANT_JUNIOR),
    ("10°", VARIANT_JUNIOR),
    ("noveno", VARIANT_JUNIOR),
    ("grado 9", VARIANT_JUNIOR),
    ("11", VARIANT_ADULTO),
    ("once", VARIANT_ADULTO),
    ("12", VARIANT_ADULTO),
])
def test_variante_desde_el_espejo_json_del_onboarding(valor, esperado):
    """`onboarding_answers["grade"]` es el espejo que escribe el chat; se lee
    porque la columna tipada se pobló después y hay usuarios que sólo tienen
    el JSON."""
    user = _usuario(grade=None, onboarding_answers={"grade": valor})
    assert selector.variante_para(user) == esperado


def test_la_columna_manda_sobre_el_json_desactualizado():
    """Si el estudiante pasó de 10° a 11°, la columna es la que se actualiza."""
    user = _usuario(grade=11, onboarding_answers={"grade": "10"})
    assert selector.variante_para(user) == VARIANT_ADULTO


@pytest.mark.parametrize("life_stage,esperado", [
    ("high_school_early", VARIANT_JUNIOR),   # "En el colegio (9° o 10°)"
    ("En el colegio", VARIANT_JUNIOR),       # mismo valor, vocabulario del journey
    ("high_school", VARIANT_ADULTO),         # 11°
    ("Terminando el colegio", VARIANT_ADULTO),
    ("university", VARIANT_ADULTO),
    ("working", VARIANT_ADULTO),
    (None, VARIANT_ADULTO),
])
def test_fallback_por_etapa_cuando_no_hay_grado(life_stage, esperado):
    user = _usuario(grade=None, onboarding_answers={"life_stage": life_stage})
    assert selector.variante_para(user) == esperado


def test_valores_basura_no_rompen_y_caen_a_adulto():
    """Ante la duda, adulto: peor es darle preguntas de niño a quien no lo es."""
    for basura in ("", "   ", "no sé", "octavo", 7, 13, True, [], {"x": 1}):
        user = _usuario(grade=None, onboarding_answers={"grade": basura})
        assert selector.variante_para(user) == VARIANT_ADULTO


def test_usuario_sin_los_campos_no_revienta():
    """Usuarios cargados parcialmente (load_only) o fakes viejos de otros tests."""
    assert selector.variante_para(SimpleNamespace()) == VARIANT_ADULTO
    assert selector.variante_para(
        SimpleNamespace(grade=None, onboarding_answers=None)
    ) == VARIANT_ADULTO


def test_grado_del_estudiante_devuelve_entero():
    assert selector.grado_del_estudiante(_usuario(grade=9)) == 9
    assert selector.grado_del_estudiante(
        _usuario(onboarding_answers={"grade": "11°"})
    ) == 11
    assert selector.grado_del_estudiante(_usuario()) is None


# ---------------------------------------------------------------------------
# 5 · El endpoint entrega el banco correcto
# ---------------------------------------------------------------------------


def test_endpoint_grado_9_recibe_el_banco_adaptado():
    salida = get_test("holland", current_user=_usuario(grade=9))
    assert salida["variant"] == VARIANT_JUNIOR
    textos = {q["id"]: q["text"] for q in salida["questions"]}
    assert textos["h-a-8"] == HOLLAND_JUNIOR_QUESTIONS[23]["text"]
    assert "Prefiero ambientes de trabajo" not in textos["h-a-8"]
    assert len(salida["questions"]) == 48


def test_endpoint_grado_11_sigue_con_el_banco_de_siempre():
    salida = get_test("holland", current_user=_usuario(grade=11))
    assert salida["variant"] == VARIANT_ADULTO
    adulto = {q["id"]: q["text"] for q in _adulto()["questions"]}
    for q in salida["questions"]:
        assert q["text"] == adulto[q["id"]]


def test_endpoint_no_toca_los_demas_tests():
    """Sólo Holland tiene variantes; Big Five sale idéntico para un chico de 9°."""
    salida = get_test("bigfive", current_user=_usuario(grade=9))
    assert salida == get_test_by_id("bigfive")
    assert "variant" not in salida


def test_endpoint_test_inexistente_sigue_dando_404():
    with pytest.raises(HTTPException) as ei:
        get_test("no-existe", current_user=_usuario(grade=9))
    assert ei.value.status_code == 404


def test_listado_muestra_la_descripcion_que_corresponde():
    canonicos = {t["id"] for t in list_tests(current_user=_usuario(grade=11))}

    junior = list_tests(current_user=_usuario(grade=9))
    assert {t["id"] for t in junior} == canonicos  # no aparecen ni desaparecen tests

    holland = next(t for t in junior if t["id"] == "holland")
    assert holland["variant"] == VARIANT_JUNIOR
    assert holland["description"] == get_holland_junior()["description"]
    # El resto de metadatos del listado siguen ahí (el front los pinta).
    for clave in ("slug", "name", "shortName", "estimatedMinutes", "questionCount", "icon"):
        assert clave in holland

    otros = [t for t in junior if t["id"] != "holland"]
    assert all("variant" not in t for t in otros)


def test_listado_de_un_adulto_conserva_la_descripcion_original():
    holland = next(
        t for t in list_tests(current_user=_usuario(grade=None)) if t["id"] == "holland"
    )
    assert holland["description"] == _adulto()["description"]
    assert holland["variant"] == VARIANT_ADULTO
