"""El payload del parser se valida con el schema EXACTO del test_type.

Bug de robustez (Fase C): `ParsedPayload` es una Union NO discriminada
[MBTI, iStrong, Big5, RIASEC]. iStrong y RIASEC comparten holland_code + los
6 GOTs y RIASEC no añade campos obligatorios → un payload RIASEC válido
también valida como iStrong (que va ANTES en la Union), así que se colaba con
el tipo equivocado. El parser ya conoce el schema correcto por test_type
(_PROMPT_MAP); ahora valida el payload con ése y conserva la instancia tipada.
"""
from __future__ import annotations

import json

import pytest

from app.services import external_test_parser as parser
from app.schemas.external_tests import ParsedIStrong, ParsedRIASEC, ParsedMBTI


# payload con forma RIASEC (sin top_basic_interests) · AMBIGUO entre iStrong y RIASEC
_RIASEC_SHAPED = {
    "holland_code": "SAE",
    "realistic": 55, "investigative": 40, "artistic": 70,
    "social": 65, "enterprising": 50, "conventional": 30,
    "suggested_careers": ["Diseño", "Psicología"],
}

_ISTRONG_SHAPED = {
    "holland_code": "IER",
    "realistic": 60, "investigative": 80, "artistic": 35,
    "social": 40, "enterprising": 55, "conventional": 45,
    "top_basic_interests": ["Ciencia", "Tecnología"],
    "suggested_careers": ["Ingeniería"],
}

_MBTI_SHAPED = {
    "type_code": "ENFJ", "identity": "A",
    "e_score": 72, "s_score": 32, "t_score": 22, "j_score": 64,
    "strengths": ["Liderazgo"], "suggested_careers": ["Educación"],
}


def _run_parse(monkeypatch, test_type, payload):
    monkeypatch.setattr(
        parser, "extract_text_from_upload",
        lambda *a, **k: ("texto del documento", {"has_text_layer": True}),
    )
    envelope = json.dumps({"payload": payload, "confidence": 0.9})
    monkeypatch.setattr(parser, "_call_claude_text", lambda prompt: (envelope, {"model": "m"}))
    return parser.parse_external_test(
        test_type=test_type, file_bytes=b"x",
        content_type="application/pdf", filename="t.pdf",
    )


def test_riasec_payload_is_ambiguous_with_istrong():
    """Documenta la raíz del bug: el payload RIASEC también valida como iStrong."""
    # No lanza → ambos schemas lo aceptan → la Union sin discriminar es ambigua.
    ParsedIStrong.model_validate(_RIASEC_SHAPED)
    ParsedRIASEC.model_validate(_RIASEC_SHAPED)


def test_riasec_parsed_as_riasec_not_istrong(monkeypatch):
    outcome = _run_parse(monkeypatch, "riasec", _RIASEC_SHAPED)

    assert outcome.result is not None
    assert isinstance(outcome.result.payload, ParsedRIASEC)
    assert not isinstance(outcome.result.payload, ParsedIStrong)


def test_istrong_still_parsed_as_istrong(monkeypatch):
    """Regresión: el fix no rompe el caso iStrong (tiene top_basic_interests)."""
    outcome = _run_parse(monkeypatch, "istrong", _ISTRONG_SHAPED)

    assert outcome.result is not None
    assert isinstance(outcome.result.payload, ParsedIStrong)
    assert outcome.result.payload.top_basic_interests == ["Ciencia", "Tecnología"]


def test_mbti_still_parsed_as_mbti(monkeypatch):
    outcome = _run_parse(monkeypatch, "mbti", _MBTI_SHAPED)

    assert outcome.result is not None
    assert isinstance(outcome.result.payload, ParsedMBTI)
    assert outcome.result.payload.type_code == "ENFJ"


def test_wrong_shape_for_test_type_goes_to_needs_review(monkeypatch):
    """Un payload MBTI bajo test_type=riasec no valida → needs_review (antes
    podía colarse si algún otro miembro de la Union lo aceptaba)."""
    outcome = _run_parse(monkeypatch, "riasec", _MBTI_SHAPED)

    assert outcome.result is None
    assert outcome.parsing_status == "needs_review"
