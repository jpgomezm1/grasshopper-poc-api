"""Tests · utilidad central de parseo JSON de respuestas Claude (Fase C/A).

Cubre app/core/ai_json.py: strip_code_fences, extract_first_json y
parse_ai_json (fences, prosa envolvente, llaves anidadas, passthrough
limpio y entradas inválidas → AIJsonError).
"""
from __future__ import annotations

import pytest

from app.core.ai_json import (
    AIJsonError,
    extract_first_json,
    parse_ai_json,
    strip_code_fences,
)


# ---------------------------------------------------------------------------
# strip_code_fences
# ---------------------------------------------------------------------------


def test_strip_fence_json_labelled():
    text = '```json\n{"a": 1}\n```'
    assert strip_code_fences(text) == '{"a": 1}'


def test_strip_fence_bare():
    text = '```\n{"a": 1}\n```'
    assert strip_code_fences(text) == '{"a": 1}'


def test_strip_fence_passthrough_when_no_fence():
    assert strip_code_fences('  {"a": 1}  ') == '{"a": 1}'


def test_strip_fence_handles_empty():
    assert strip_code_fences("") == ""
    assert strip_code_fences(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# extract_first_json
# ---------------------------------------------------------------------------


def test_extract_json_wrapped_in_prose():
    text = 'Claro, aquí tienes el resultado: {"ok": true} ¡Espero que sirva!'
    assert extract_first_json(text) == '{"ok": true}'


def test_extract_json_nested_braces():
    text = 'prefix {"outer": {"inner": {"deep": 1}}, "b": 2} suffix'
    assert extract_first_json(text) == '{"outer": {"inner": {"deep": 1}}, "b": 2}'


def test_extract_json_none_when_no_object():
    assert extract_first_json("sin json aquí") is None
    assert extract_first_json("") is None
    assert extract_first_json(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# parse_ai_json · pipeline completo
# ---------------------------------------------------------------------------


def test_parse_clean_json_passthrough():
    assert parse_ai_json('{"a": 1, "b": [2, 3]}') == {"a": 1, "b": [2, 3]}


def test_parse_fenced_json():
    assert parse_ai_json('```json\n{"text": "hola"}\n```') == {"text": "hola"}


def test_parse_fenced_bare():
    assert parse_ai_json('```\n{"x": 1}\n```') == {"x": 1}


def test_parse_json_wrapped_in_prose():
    text = 'Aquí está tu síntesis:\n{"routes": [{"key": "A"}]}\nAvísame si necesitas más.'
    assert parse_ai_json(text) == {"routes": [{"key": "A"}]}


def test_parse_nested_braces_and_string_with_brace():
    # Strings que contienen '}' · el balanceador es ingenuo a propósito,
    # pero json.loads valida el resultado; el objeto completo debe parsear.
    text = '{"msg": "fin}", "nested": {"a": {"b": 1}}}'
    assert parse_ai_json(text) == {"msg": "fin}", "nested": {"a": {"b": 1}}}


def test_parse_prose_with_nested_object():
    text = "Resultado: {\"chips\": [{\"label\": \"Etapa\", \"value\": \"Explorando\"}]} listo"
    assert parse_ai_json(text) == {
        "chips": [{"label": "Etapa", "value": "Explorando"}]
    }


def test_parse_empty_raises_aijsonerror():
    with pytest.raises(AIJsonError):
        parse_ai_json("")


def test_parse_garbage_raises_aijsonerror_with_preview():
    garbage = "x" * 500
    with pytest.raises(AIJsonError) as exc_info:
        parse_ai_json(garbage)
    # El preview se limita a 200 chars del original
    assert "x" * 200 in str(exc_info.value)
    assert "x" * 201 not in str(exc_info.value)


def test_aijsonerror_is_valueerror():
    # Contrato clave: los except (ValueError, KeyError) existentes la capturan
    assert issubclass(AIJsonError, ValueError)


def test_parse_unbalanced_braces_raises():
    with pytest.raises(AIJsonError):
        parse_ai_json('{"a": 1')
