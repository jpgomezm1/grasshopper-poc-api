"""Unit tests · external_test_parser (GH-S5-BE-04).

Tests focus on:
    - Schema validators (null coercion · range bounds · forbidden extras)
    - JSON extraction helper (handles ```json fences, trailing text, etc.)
    - document_parser dispatch (PDF vs image vs unsupported)

Does NOT exercise Claude · those tests live in scripts/eval_external_test_parser.py
"""
from __future__ import annotations

import io
import pytest

from app.schemas.external_tests import (
    ParsedBig5,
    ParsedIStrong,
    ParsedMBTI,
    ParsedRIASEC,
    ParserResult,
)
from app.services import document_parser
from app.services.external_test_parser import _extract_json, ParseError


# -----------------------------------------------------------------------------
# Schema validator tests
# -----------------------------------------------------------------------------

def test_mbti_schema_accepts_null_lists():
    """Claude often returns null for empty arrays · we coerce to [] in validator."""
    parsed = ParsedMBTI.model_validate({
        "type_code": "INTJ",
        "identity": None,
        "e_score": 38, "s_score": 26, "t_score": 68, "j_score": 55,
        "strengths": None,
        "suggested_careers": None,
    })
    assert parsed.strengths == []
    assert parsed.suggested_careers == []


def test_mbti_schema_rejects_extras():
    with pytest.raises(Exception):
        ParsedMBTI.model_validate({
            "type_code": "INTJ", "extra_field": "boom",
        })


def test_mbti_score_bounds():
    with pytest.raises(Exception):
        ParsedMBTI.model_validate({"type_code": "INTJ", "e_score": 195})


def test_istrong_schema_handles_null_basic_interests():
    parsed = ParsedIStrong.model_validate({
        "holland_code": "SEC",
        "realistic": 32, "investigative": 40, "artistic": 44,
        "social": 61, "enterprising": 58, "conventional": 52,
        "top_basic_interests": None,
        "suggested_careers": None,
    })
    assert parsed.top_basic_interests == []
    assert parsed.suggested_careers == []
    assert parsed.holland_code == "SEC"


def test_riasec_score_bounds():
    """Sprint 5 regression: model returned 195 for an out-of-bounds score."""
    with pytest.raises(Exception):
        ParsedRIASEC.model_validate({
            "holland_code": "ASI",
            "realistic": 55, "investigative": 102.5, "artistic": 195,
            "social": 135, "enterprising": 90, "conventional": 47.5,
        })


def test_big5_partial_dimensions():
    """Some clinical reports only give 3 of 5 · should still validate."""
    parsed = ParsedBig5.model_validate({
        "openness": 76, "conscientiousness": 64, "extraversion": 52,
        "agreeableness": None, "neuroticism": None,
    })
    assert parsed.openness == 76
    assert parsed.agreeableness is None


def test_parser_result_full_envelope():
    pr = ParserResult.model_validate({
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
    assert pr.test_type == "mbti"
    assert pr.confidence == 0.95
    assert pr.payload.type_code == "ENFJ"


# -----------------------------------------------------------------------------
# JSON extraction tests
# -----------------------------------------------------------------------------

def test_extract_json_plain():
    raw = '{"type_code": "INTJ", "confidence": 0.9}'
    assert _extract_json(raw)["type_code"] == "INTJ"


def test_extract_json_with_fence():
    raw = '```json\n{"type_code": "INTJ"}\n```'
    assert _extract_json(raw)["type_code"] == "INTJ"


def test_extract_json_with_text_before_after():
    raw = 'Sure, here is the JSON:\n\n{"a": 1}\n\nHope this helps!'
    assert _extract_json(raw)["a"] == 1


def test_extract_json_garbage_raises():
    with pytest.raises(ParseError):
        _extract_json("no json here")


# -----------------------------------------------------------------------------
# document_parser dispatch
# -----------------------------------------------------------------------------

def test_is_pdf_detection():
    assert document_parser.is_pdf("application/pdf", None)
    assert document_parser.is_pdf(None, "report.pdf")
    assert document_parser.is_pdf(None, "REPORT.PDF")
    assert not document_parser.is_pdf("image/png", "x.png")


def test_is_image_detection():
    assert document_parser.is_image("image/png", "a.png")
    assert document_parser.is_image("image/jpeg", "b.jpg")
    assert document_parser.is_image(None, "c.heic")
    assert not document_parser.is_image("application/pdf", "x.pdf")


def test_extract_text_from_upload_unsupported_raises():
    with pytest.raises(document_parser.DocumentParseError):
        document_parser.extract_text_from_upload(b"x", "application/zip", "x.zip")


def test_extract_text_from_upload_image_passthrough():
    text, meta = document_parser.extract_text_from_upload(b"\x89PNG", "image/png", "x.png")
    assert text == ""
    assert meta["extractor"] == "image-passthrough"
