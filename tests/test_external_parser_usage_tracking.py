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


def test_call_claude_messages_extracts_meta(monkeypatch):
    """El helper devuelve (texto, metadata) con tokens y latencia reales."""
    class _Usage:
        input_tokens = 640
        output_tokens = 210

    class _Block:
        text = "respuesta del modelo"

    class _Response:
        content = [_Block()]
        usage = _Usage()

    class _Client:
        def with_options(self, **kw):
            return self

        class messages:  # noqa: N801 · imita el SDK
            @staticmethod
            def create(**kw):
                return _Response()

    monkeypatch.setattr(parser, "get_client", lambda: _Client())

    text, meta = parser._call_claude_messages([{"role": "user", "content": "hola"}])

    assert text == "respuesta del modelo"
    assert meta["tokens_input"] == 640
    assert meta["tokens_output"] == 210
    assert "latency_ms" in meta
    assert meta["model"]
