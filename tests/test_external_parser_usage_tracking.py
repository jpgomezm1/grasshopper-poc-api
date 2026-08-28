"""Tracking M-001 en el parser de tests externos (visión / texto).

El parser llamaba al SDK directo y devolvía solo el texto → el parseo de
tests subidos (MBTI/Big5/etc., a veces por visión sobre una imagen) nunca
aparecía en ai_usage_log. Fase C: las funciones de llamada devuelven
``(texto, metadata)`` y `ParseOutcome` expone `usage`, que el caller
(_run_parse_task) registra con feature="external_test_parse".

Cubre: (a) éxito propaga usage; (b) sin llamada IA (extracción falla) →
usage None; (c) el helper _call_claude_messages extrae tokens/latencia.
"""
from __future__ import annotations

import json

import pytest

from app.services import external_test_parser as parser
from app.services.document_parser import DocumentParseError


_META = {
    "model": "claude-sonnet-4-6",
    "tokens_input": 500,
    "tokens_output": 120,
    "latency_ms": 800,
}

_ENVELOPE = json.dumps({
    "test_type": "mbti",
    "student_name": "Test User",
    "test_date": "2026-04-30",
    "payload": {
        "type_code": "ENFJ", "identity": "A",
        "e_score": 72, "s_score": 32, "t_score": 22, "j_score": 64,
        "strengths": ["Liderazgo"], "suggested_careers": ["Educación"],
    },
    "confidence": 0.95,
    "parser_version": "v1",
    "notes": None,
})


def test_parse_propagates_usage_on_success(monkeypatch):
    # Hay texto extraíble → ruta de texto (no visión)
    monkeypatch.setattr(
        parser, "extract_text_from_upload",
        lambda *a, **k: ("texto extraido del pdf", {"has_text_layer": True}),
    )
    monkeypatch.setattr(parser, "_call_claude_text", lambda prompt: (_ENVELOPE, dict(_META)))

    outcome = parser.parse_external_test(
        test_type="mbti", file_bytes=b"x",
        content_type="application/pdf", filename="mbti.pdf",
    )

    assert outcome.result is not None
    assert outcome.parsing_status == "done"
    assert outcome.usage == _META


def test_no_usage_when_extraction_fails(monkeypatch):
    """Sin llamada a la IA (extracción del documento falla) → usage None."""
    def _boom(*a, **k):
        raise DocumentParseError("no se pudo leer el documento")

    monkeypatch.setattr(parser, "extract_text_from_upload", _boom)

    outcome = parser.parse_external_test(
        test_type="mbti", file_bytes=b"x",
        content_type="application/pdf", filename="mbti.pdf",
    )

    assert outcome.result is None
    assert outcome.parsing_status == "failed"
    assert outcome.usage is None


# `_call_claude_messages` se movió a `app/services/document_ai.py` el
# 2026-08-28 (lo necesitaba también el lector de diplomas). Su test se mudó con
# él a `tests/test_document_ai.py`, donde el mock apunta al módulo correcto.
#
# Vale la pena recordar por qué: al mover la función, este test seguía
# parcheando `parser.get_client` y el parche dejó de aplicar — la llamada salió
# a la API de Anthropic DE VERDAD y el test falló porque el modelo contestó un
# saludo. Un mock que apunta al módulo equivocado no se ve como un mock roto:
# se ve como una llamada de red silenciosa.
