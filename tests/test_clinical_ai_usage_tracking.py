"""Tracking M-001 en el análisis clínico (clinical_analysis_service.generate).

`_call_llm` ya extraía la metadata (tokens/latency/error_kind) pero `generate`
la descartaba → el análisis clínico (caro: ~Sonnet con corpus grande) no
aparecía en ai_usage_log. Ahora `generate` registra con
feature="clinical_analysis" tras llamar a la IA, en éxito Y en error (en
error tokens=None → costo None, pero el panel ve el intento).

Mockea `_call_llm` directo (los stubs del SDK ya se prueban en
test_clinical_llm_hardening.py).
"""
from __future__ import annotations

import pytest

from app.services import clinical_analysis_service as svc


def _student():
    return type("S", (), {"id": "u-1", "clinical_analysis_cached_at": None})()


def _patch_pipeline(monkeypatch):
    """Mocks comunes para llegar a _call_llm dentro de generate()."""
    monkeypatch.setattr(svc, "insufficient_inputs_reason", lambda db, s: None)
    monkeypatch.setattr(
        svc, "_gather_inputs",
        lambda db, s: {
            "demographic_block": "", "consolidated_block": "", "tests_block": "",
            "journey_answers_block": "", "journal_block": "",
        },
    )
    monkeypatch.setattr(
        svc, "load_prompt",
        lambda name: "{demographic_block}{consolidated_block}{tests_block}"
                     "{journey_answers_block}{journal_block}",
    )


def test_generate_records_ai_usage_on_error(monkeypatch):
    _patch_pipeline(monkeypatch)
    monkeypatch.setattr(
        svc, "_call_llm",
        lambda prompt, uid: (None, {
            "model": "claude-sonnet-4-6", "error_kind": "rate_limit",
            "latency_ms": 12, "tokens_input": None, "tokens_output": None,
        }),
    )

    calls: list[dict] = []
    monkeypatch.setattr(svc, "record_ai_usage", lambda db, **kw: calls.append(kw))

    with pytest.raises(svc.ClinicalAnalysisFailure):
        svc.generate(db=None, student=_student(), force=True)

    assert len(calls) == 1
    assert calls[0]["feature"] == "clinical_analysis"
    assert calls[0]["provider"] == "anthropic"
    assert calls[0]["tokens_input"] is None
    assert calls[0]["user_id"] == "u-1"


def test_generate_records_ai_usage_on_success(monkeypatch):
    _patch_pipeline(monkeypatch)
    monkeypatch.setattr(
        svc, "_call_llm",
        lambda prompt, uid: ('{"narrative": "ok"}', {
            "model": "claude-sonnet-4-6",
            "tokens_input": 1500, "tokens_output": 800, "latency_ms": 900,
        }),
    )

    calls: list[dict] = []
    monkeypatch.setattr(svc, "record_ai_usage", lambda db, **kw: calls.append(kw))

    # El tracking ocurre inmediatamente tras _call_llm; el parseo/persistencia
    # posterior con db=None no es lo que probamos aquí.
    try:
        svc.generate(db=None, student=_student(), force=True)
    except Exception:
        pass

    assert len(calls) == 1
    assert calls[0]["feature"] == "clinical_analysis"
    assert calls[0]["tokens_input"] == 1500
    assert calls[0]["tokens_output"] == 800
    assert calls[0]["latency_ms"] == 900
