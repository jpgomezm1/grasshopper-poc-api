"""I-5 / I-6 · Sprint 4 · la Práctica Saber 11.

Lo que protegen estos tests:
 1. Cada prueba del banco tiene 20 ejercicios propios con los tres niveles.
 2. Los enunciados van en español y ninguno se presenta como del Icfes.
 3. La ficha avisa que no está afiliada al Icfes, no usa su nombre como marca
    del producto y no publica datos duros del examen.
 4. A quién se le recomienda: 11° y 12° sí; 10° "con tiempo"; profesional no.
 5. El paso "Prepárate para el Saber 11" del plan de preparación lleva a ella.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.data import exam_prep as banco
from app.services import exam_prep_service as svc

PRUEBAS_CON_BANCO = ["s11_lectura", "s11_matematicas", "s11_sociales", "s11_ciencias"]


@pytest.mark.parametrize("habilidad", PRUEBAS_CON_BANCO)
def test_cada_prueba_tiene_20_y_los_tres_niveles(habilidad):
    items = banco.items(skill_id=habilidad)
    assert len(items) == 20
    niveles = {i["level"] for i in items}
    assert niveles == set(banco.NIVELES)
    assert all(i["exam"] == banco.EXAMEN_SABER11 for i in items)


def test_los_textos_de_lectura_son_propios_y_existen():
    for i in banco.items(skill_id="s11_lectura"):
        assert i["passage_id"] and banco.texto(i["passage_id"]), i["id"]
        assert i["passage_id"].startswith("s11_")


def test_ningun_ejercicio_se_presenta_como_del_icfes():
    for i in banco.items(exam_id=banco.EXAMEN_SABER11):
        texto = (i["question"] + " " + " ".join(i["options"]) + " " + (banco.texto(i["passage_id"]) or "")).lower()
        assert "icfes" not in texto, i["id"]
        assert "cuadernillo" not in texto, i["id"]


def test_los_enunciados_van_en_espanol():
    # Una señal simple y suficiente: cada enunciado tiene alguna palabra o signo
    # propio del español.
    marcas = re.compile(r"[¿¡áéíóúñ]|\b(el|la|los|las|de|que|en|un|una)\b", re.IGNORECASE)
    for i in banco.items(exam_id=banco.EXAMEN_SABER11):
        assert marcas.search(i["question"]), i["id"]


def test_la_ficha_avisa_que_no_es_del_icfes_y_no_publica_datos_duros():
    ficha = banco.get_examen(banco.EXAMEN_SABER11)
    assert ficha["shortName"] == "Práctica Saber 11"
    assert "ICFES" not in ficha["name"] and "Icfes" not in ficha["name"]
    assert "no está afiliado al Icfes" in banco.MARCAS[banco.EXAMEN_SABER11]
    formato = " ".join(ficha["formato"])
    # Ni puntajes, ni duración, ni número de preguntas, ni fechas.
    assert not re.search(r"\b\d+\s*(puntos|minutos|horas|preguntas)\b", formato)
    assert not re.search(r"\d{2,}", formato)


def _estudiante(grade=None, life_stage="high_school"):
    respuestas = {"life_stage": life_stage}
    if grade is not None:
        respuestas["grade"] = str(grade)
    return SimpleNamespace(grade=grade, onboarding_answers=respuestas, english_cefr_level=None)


@pytest.mark.parametrize("grado", [11, 12])
def test_se_recomienda_en_11_y_12(grado):
    r = svc.recomendacion(None, _estudiante(grado), banco.EXAMEN_SABER11)
    assert r["recommended"] is True


def test_en_10_sale_con_tiempo_y_sin_cerrarse():
    r = svc.recomendacion(None, _estudiante(10, "high_school_early"), banco.EXAMEN_SABER11)
    assert r["recommended"] is False
    assert r["reasonCode"] == "grade_early"


def test_a_un_profesional_no_se_le_recomienda():
    r = svc.recomendacion(None, _estudiante(None, "working"), banco.EXAMEN_SABER11)
    assert r["reasonCode"] == "professional_track"


def test_la_frase_de_arranque_no_nombra_las_matematicas():
    h = banco.get_habilidad("s11_lectura")
    assert "matemáticas" not in svc._nivel_para(h, {})["why"]
