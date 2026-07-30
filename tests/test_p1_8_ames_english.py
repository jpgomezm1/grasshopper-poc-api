"""A5 / P1-8 · Banco real del test de inglés (AMES) · Sprint 3 (2026-07-29).

La clienta lo pidió desde el primer feedback: el test tenía **20 preguntas
inventadas por nosotros**. Con este feedback llegó el instrumento real —examen de
60 preguntas, clave y tabla de ubicación de AMES International—, así que ya no
depende de nadie.

Lo que estos tests protegen no es "que haya 60 preguntas": es que la
**transcripción sea fiel**. Un banco copiado a mano de un escaneo falla de tres
maneras, y las tres le dan al estudiante un nivel de inglés equivocado:

  1. la clave se desfasa una posición y ~59 ítems quedan mal calificados,
  2. una letra apunta a una opción que no existe (ítems de 3 opciones con clave D),
  3. la tabla de ubicación se copia con un rango solapado o con un hueco.

Además se fija que NO volvamos a inventar el nivel CEFR por pregunta, que es lo
que hacía el banco anterior.
"""
from __future__ import annotations

import pytest

from app.data import english_test_questions as banco
from app.data.english_test_questions import (
    ENGLISH_TEST_QUESTIONS,
    calculate_score,
    get_questions_for_client,
    placement_for,
)


# ---------------------------------------------------------------------------
# Integridad de la transcripción
# ---------------------------------------------------------------------------


def test_son_las_60_preguntas_del_examen():
    assert len(ENGLISH_TEST_QUESTIONS) == 60
    assert [q["number"] for q in ENGLISH_TEST_QUESTIONS] == list(range(1, 61))


def test_ningun_id_ni_enunciado_repetido():
    """El feedback de Sprint 2 reportó preguntas duplicadas. Que no reaparezcan
    por un copy-paste al transcribir."""
    ids = [q["id"] for q in ENGLISH_TEST_QUESTIONS]
    assert len(set(ids)) == 60
    enunciados = [q["question"] for q in ENGLISH_TEST_QUESTIONS]
    assert len(set(enunciados)) == 60


def test_la_respuesta_correcta_siempre_esta_entre_las_opciones():
    """Falla si la clave se desfasó o si un ítem de 3 opciones tiene clave D."""
    for q in ENGLISH_TEST_QUESTIONS:
        assert q["correct"] in q["options"], f"ítem {q['number']}"


def test_la_letra_de_la_clave_coincide_con_la_posicion_impresa():
    """A=primera opción, B=segunda… Es la invariante que detecta un desfase."""
    for q in ENGLISH_TEST_QUESTIONS:
        esperado = q["options"]["ABCD".index(q["answer_letter"])]
        assert q["correct"] == esperado, f"ítem {q['number']}"


def test_no_hay_opciones_repetidas_dentro_de_un_item():
    """Dos opciones idénticas harían la pregunta imposible de calificar."""
    for q in ENGLISH_TEST_QUESTIONS:
        assert len(set(q["options"])) == len(q["options"]), f"ítem {q['number']}"


@pytest.mark.parametrize(
    "numero,cantidad",
    [(n, 3) for n in range(1, 11)] + [(n, 4) for n in range(11, 61)],
)
def test_cantidad_de_opciones_por_item(numero, cantidad):
    """El examen usa 3 opciones en los ítems 1-10 y 4 en el resto."""
    q = ENGLISH_TEST_QUESTIONS[numero - 1]
    assert len(q["options"]) == cantidad


def test_la_clave_transcrita_coincide_con_el_pdf():
    """Cotejo literal contra `AMES - clave de respuestas.pdf`.

    Se repite aquí a mano, aparte del módulo, justamente para que una corrección
    descuidada en el banco no pase silenciosa: si alguien "arregla" una letra,
    tiene que arreglarla en los dos lados y volver a mirar el escaneo.
    """
    esperada = "".join(
        [
            "CBACCAACCB",  # 1-10
            "CABACDABCB",  # 11-20
            "CDBBAADACD",  # 21-30
            "BBCCDBCBCC",  # 31-40
            "BADDDACADD",  # 41-50
            "CCBCDDCBAD",  # 51-60
        ]
    )
    assert len(esperada) == 60
    assert "".join(q["answer_letter"] for q in ENGLISH_TEST_QUESTIONS) == esperada


# ---------------------------------------------------------------------------
# Nada inventado
# ---------------------------------------------------------------------------


def test_no_se_inventa_nivel_cefr_por_pregunta():
    """El banco anterior etiquetaba cada pregunta con A1/A2/B1… Ese dato no existe
    en el examen de AMES: era nuestro. Mostrárselo al estudiante como si viniera
    del instrumento es mostrarle un dato falso."""
    assert all(q["difficulty"] is None for q in ENGLISH_TEST_QUESTIONS)


def test_el_front_nunca_recibe_la_respuesta_correcta():
    for item in get_questions_for_client():
        assert "correct" not in item
        assert "answer_letter" not in item


def test_los_items_de_cloze_llevan_su_texto():
    """Un hueco numerado sin el texto al lado es imposible de responder."""
    cliente = {c["number"]: c for c in get_questions_for_client()}
    con_texto = set(range(6, 21)) | set(range(41, 51))
    for numero in con_texto:
        assert cliente[numero].get("passage"), f"ítem {numero} sin texto"
    # Y los que no son cloze no deben arrastrar el texto del anterior.
    for numero in list(range(1, 6)) + list(range(21, 41)) + list(range(51, 61)):
        assert "passage" not in cliente[numero], f"ítem {numero} con texto de más"


def test_cada_texto_menciona_sus_propios_huecos():
    """Detecta el error de pegar el texto equivocado a un grupo de preguntas."""
    cliente = {c["number"]: c for c in get_questions_for_client()}
    for numero in list(range(6, 21)) + list(range(41, 51)):
        assert f"({numero})" in cliente[numero]["passage"], f"ítem {numero}"


# ---------------------------------------------------------------------------
# Tabla de ubicación de AMES
# ---------------------------------------------------------------------------


def test_la_tabla_cubre_0_a_60_sin_huecos_ni_solapes():
    rangos = sorted((minimo, maximo) for minimo, maximo, *_ in banco._PLACEMENT)
    assert rangos[0][0] == 0
    assert rangos[-1][1] == 60
    for (_, fin), (inicio_siguiente, _) in zip(rangos, rangos[1:]):
        assert inicio_siguiente == fin + 1, f"hueco o solape en {fin}"


@pytest.mark.parametrize(
    "puntaje,ielts,clase,cefr",
    [
        (0, "3.5", "Elemental", "A2"),
        (7, "3.5", "Elemental", "A2"),
        (8, "4.0", "Pre intermedio", "B1"),
        (17, "4.0", "Pre intermedio", "B1"),
        (18, "4.5", "Intermedio", "B1"),
        (29, "4.5", "Intermedio", "B1"),
        (30, "5.0", "Intermedio alto", "B1"),
        (39, "5.0", "Intermedio alto", "B1"),
        (40, "5.5", "Avanzado", "B2"),
        (47, "5.5", "Avanzado", "B2"),
        (48, "6.0", "Avanzado académico", "B2"),
        (55, "6.0", "Avanzado académico", "B2"),
        (56, "6.5", "Nivel postgrado", "B2"),
        (60, "6.5", "Nivel postgrado", "B2"),
    ],
)
def test_la_tabla_es_la_que_publica_la_agencia(puntaje, ielts, clase, cefr):
    """Transcrita de `AMES - equivalencia IELTS.jpg`, que es la página "Test de
    inglés gratuito" de la propia agencia.

    Las cuatro columnas son de ella, **incluido el CEFR**. La primera versión de
    esto derivaba el CEFR por nuestra cuenta y difería del suyo en tres franjas:
    un estudiante con 58/60 veía C1 en la plataforma mientras su web publica B2
    para ese mismo puntaje. Mover un borde o una etiqueta aquí vuelve a abrir esa
    contradicción, y el CEFR además filtra qué programas se le recomiendan.
    """
    p = placement_for(puntaje)
    assert p["ielts_equivalent"] == ielts
    assert p["class_placement"] == clase
    assert p["cefr_level"] == cefr


def test_el_techo_del_instrumento_es_B2_no_C1():
    """Su tabla asigna B2 hasta 60/60; C1 empieza en IELTS 7.0, que este examen no
    mide. Es el punto donde más nos habíamos desviado."""
    assert placement_for(60)["cefr_level"] == "B2"
    assert "C1" not in {c for *_, c in banco._PLACEMENT}


def test_el_cefr_nunca_baja_al_subir_el_puntaje():
    orden = ["A1", "A2", "B1", "B2", "C1"]
    anterior = 0
    for puntaje in range(0, 61):
        actual = orden.index(placement_for(puntaje)["cefr_level"])
        assert actual >= anterior, f"el CEFR baja en {puntaje}"
        anterior = actual


# ---------------------------------------------------------------------------
# Calificación
# ---------------------------------------------------------------------------


def test_todo_correcto_da_60_y_el_techo_del_instrumento():
    perfecto = {q["id"]: q["correct"] for q in ENGLISH_TEST_QUESTIONS}
    r = calculate_score(perfecto)
    assert r["score"] == 60
    assert r["percentage"] == 100
    assert r["cefr_level"] == "B2"
    assert r["class_placement"] == "Nivel postgrado"


def test_sin_responder_no_revienta_y_no_regala_nivel():
    r = calculate_score({})
    assert r["score"] == 0
    assert r["cefr_level"] == "A2"
    assert r["class_placement"] == "Elemental"


def test_una_respuesta_desconocida_no_cuenta_como_correcta():
    r = calculate_score({q["id"]: "???" for q in ENGLISH_TEST_QUESTIONS})
    assert r["score"] == 0


def test_se_mantienen_las_llaves_que_ya_consumen_el_front_y_los_pdfs():
    """El PDF del estudiante y la pantalla de resultados leen estas llaves. Si el
    cambio de banco las rompiera, volveríamos al bug de "0% en las tres secciones
    de inglés" que la clienta ya reportó una vez."""
    r = calculate_score({})
    for llave in ("score", "total_questions", "percentage", "cefr_level", "section_scores"):
        assert llave in r
    assert set(r["section_scores"]) == {"grammar", "vocabulary", "reading"}
    for detalle in r["section_scores"].values():
        assert set(detalle) == {"correct", "total", "percentage"}


def test_las_secciones_suman_las_60_preguntas():
    r = calculate_score({})
    assert sum(d["total"] for d in r["section_scores"].values()) == 60


def test_se_expone_la_particion_real_de_ames():
    """`section` es nuestra clasificación; `ames_parts` es la del examen. Se
    reportan las dos para no hacer pasar una interpretación nuestra por dato del
    instrumento."""
    r = calculate_score({})
    assert set(r["ames_parts"]) == {"Part 1", "Part 2"}
    assert r["ames_parts"]["Part 1"]["total"] == 40
    assert r["ames_parts"]["Part 2"]["total"] == 20
    assert r["instrument"] == "AMES English Placement Test"


def test_el_endpoint_no_puede_descartar_la_ubicacion():
    """La tarjeta "Según el examen de ubicación de AMES" del front está condicionada
    a `class_placement`. La primera versión calculaba el campo y el response model
    del endpoint lo tiraba, así que la tarjeta **nunca se renderizaba**: código
    muerto que pasó typecheck, build y toda la suite.

    Este test fija el contrato desde el modelo de respuesta, no desde el servicio.
    """
    from app.api.v1.english_test import TestResultResponse

    campos = set(TestResultResponse.model_fields)
    for campo in ("ielts_equivalent", "class_placement", "instrument"):
        assert campo in campos, f"el endpoint volvería a descartar {campo}"

    # Y que lo que produce el servicio quepa en el modelo.
    r = calculate_score({})
    TestResultResponse(
        score=r["score"],
        total_questions=r["total_questions"],
        percentage=r["percentage"],
        cefr_level=r["cefr_level"],
        section_scores=r["section_scores"],
        ielts_equivalent=r["ielts_equivalent"],
        class_placement=r["class_placement"],
        instrument=r["instrument"],
    )


def test_el_puntaje_por_seccion_refleja_lo_respondido():
    """Responder bien solo la sección de gramática debe dar 100% ahí y 0% en las
    otras dos — no un promedio repartido."""
    solo_gramatica = {
        q["id"]: q["correct"]
        for q in ENGLISH_TEST_QUESTIONS
        if q["section"] == "grammar"
    }
    r = calculate_score(solo_gramatica)
    assert r["section_scores"]["grammar"]["percentage"] == 100
    assert r["section_scores"]["vocabulary"]["percentage"] == 0
    assert r["section_scores"]["reading"]["percentage"] == 0
    assert r["score"] == r["section_scores"]["grammar"]["total"]
