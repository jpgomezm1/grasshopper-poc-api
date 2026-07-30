"""B-01 · integridad del banco de preguntas del test de inglés.

La clienta reportó el test "roto": la pregunta g8 tenía un artefacto de
plantilla en el enunciado (`the__(flaw)`). Estos tests blindan el banco:
sin placeholders corruptos, cada `correct` está entre las opciones, ids
únicos, y el scoring da 100% con todas las respuestas correctas.
"""
import re

import pytest

from app.data.english_test_questions import (
    ENGLISH_TEST_QUESTIONS,
    calculate_score,
    get_questions_for_client,
)

# Artefactos de plantilla que NO deben aparecer en un enunciado ya redactado.
_BROKEN_PATTERNS = [r"__\(", r"\(flaw\)", r"\bTODO\b", r"\bXXX\b", r"\{\{"]


@pytest.mark.parametrize("q", ENGLISH_TEST_QUESTIONS, ids=lambda q: q["id"])
def test_question_text_has_no_template_artifacts(q):
    for pat in _BROKEN_PATTERNS:
        assert not re.search(pat, q["question"]), (
            f"pregunta {q['id']} tiene un artefacto de plantilla: {q['question']!r}"
        )


@pytest.mark.parametrize("q", ENGLISH_TEST_QUESTIONS, ids=lambda q: q["id"])
def test_correct_answer_is_one_of_the_options(q):
    assert q["correct"] in q["options"], (
        f"pregunta {q['id']}: la respuesta correcta {q['correct']!r} no está en las opciones"
    )


def test_question_ids_are_unique():
    ids = [q["id"] for q in ENGLISH_TEST_QUESTIONS]
    assert len(ids) == len(set(ids))


def test_client_payload_never_leaks_correct_answer():
    for item in get_questions_for_client():
        assert "correct" not in item


def test_all_correct_answers_score_full():
    """A5 · el techo ya no es C1 sino B2: la tabla de equivalencia que publica la
    agencia asigna B2 hasta 60/60 (C1 empieza en IELTS 7.0, que este examen no
    mide). Antes este test fijaba C1, que era una derivación nuestra."""
    answers = {q["id"]: q["correct"] for q in ENGLISH_TEST_QUESTIONS}
    res = calculate_score(answers)
    assert res["score"] == len(ENGLISH_TEST_QUESTIONS)
    assert res["percentage"] == 100
    assert res["cefr_level"] == "B2"
