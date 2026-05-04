"""Pure unit tests for the clinical sprint · no DB · no LLM.

These tests validate:
- psychometrics_service deterministic pattern detection
- clinical_pdf_service HTML rendering with empty inputs
- clinical_recommendations_service heuristics

Companion tests `test_advisor_clinical.py` exercise the full stack via
TestClient · they require a working sqlite DB which the env currently
does not support (UUID compile issue affects 124 pre-existing tests too).
Once the env is fixed, those will run too. These pure-unit tests run
TODAY independent of DB.
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Psychometrics · deterministic primitives
# ---------------------------------------------------------------------------


def test_holland_top_picks_dominant_letter():
    from app.services.psychometrics_service import _holland_top
    assert _holland_top({"R": 30, "I": 85, "A": 40, "S": 50}) == "I"
    # No data
    assert _holland_top({}) is None
    # Holland_codes shape
    assert _holland_top({"holland_codes": [{"code": "S", "score": 90}]}) == "S"


def test_bigfive_traits_normalizes_letter_shape():
    from app.services.psychometrics_service import _bigfive_traits
    out = _bigfive_traits({"O": 0.8, "C": 0.5, "E": 0.3, "A": 0.6, "N": 0.5})
    assert round(out["openness"], 0) == 80
    assert round(out["extraversion"], 0) == 30


def test_bigfive_traits_keeps_0_100_scale():
    from app.services.psychometrics_service import _bigfive_traits
    out = _bigfive_traits({"openness": 75, "neuroticism": 40})
    assert out["openness"] == 75
    assert out["neuroticism"] == 40


def test_level_thresholds():
    from app.services.psychometrics_service import _level
    assert _level(80) == "alto"
    assert _level(50) == "medio"
    assert _level(20) == "bajo"
    assert _level(None) is None


def test_detect_cross_pattern_investigador():
    from app.services.psychometrics_service import _detect_cross_patterns
    tests = {
        "riasec": {"R": 30, "I": 85, "A": 40},
        "big5": {"openness": 80, "conscientiousness": 65, "extraversion": 50},
        "mbti": {"type": "INTJ"},
    }
    out = _detect_cross_patterns(tests)
    labels = [p.label for p in out]
    assert any("investigador" in l.lower() for l in labels)


def test_detect_inconsistency_holland_social_low_agreeableness():
    from app.services.psychometrics_service import _detect_inconsistencies
    tests = {
        "riasec": {"S": 80, "I": 30},
        "big5": {"agreeableness": 25},
    }
    out = _detect_inconsistencies(tests)
    labels = [i.label for i in out]
    assert any("Agreeableness" in l for l in labels), labels


# ---------------------------------------------------------------------------
# Clinical PDF · HTML rendering
# ---------------------------------------------------------------------------


def test_clinical_pdf_render_html_with_minimal_inputs():
    from app.schemas.clinical import (
        DossierAspirations,
        DossierDemographics,
        DossierResponse,
        PsychometricsResponse,
    )
    from app.services.clinical_pdf_service import render_clinical_html

    sid = uuid4()
    dossier = DossierResponse(
        student_user_id=sid,
        demographics=DossierDemographics(
            email="alumna@ejemplo.com",
            name="Alumna Ejemplo",
        ),
        notes_by_section={},
        aspirations=DossierAspirations(declared=[], inferred=[]),
        journey_answers={},
        has_consolidated_profile=False,
        tests_completed_count=0,
    )
    psy = PsychometricsResponse(
        student_user_id=sid,
        tests=[],
        tests_count=0,
    )
    html = render_clinical_html(
        student_name="Alumna Ejemplo",
        advisor_name="Carolina Mendez",
        dossier=dossier,
        psy=psy,
        analysis=None,
        recs=None,
        finalists=None,
        generated_at=datetime(2026, 5, 4, 12, 0, 0),
    )
    assert "Expediente clínico" in html
    assert "Alumna Ejemplo" in html
    assert "Carolina Mendez" in html
    assert "CONFIDENCIAL" in html
    assert "USO INTERNO" in html
    assert "Vista psicométrica" in html
    assert "Sin tests registrados" in html


def test_clinical_pdf_html_includes_referral_when_required():
    from app.schemas.clinical import (
        BehavioralPattern,
        ClinicalAnalysis,
        DossierAspirations,
        DossierDemographics,
        DossierResponse,
        PsychometricsResponse,
    )
    from app.services.clinical_pdf_service import render_clinical_html

    sid = uuid4()
    dossier = DossierResponse(
        student_user_id=sid,
        demographics=DossierDemographics(email="x@y.com"),
        notes_by_section={},
        aspirations=DossierAspirations(),
        journey_answers={},
    )
    psy = PsychometricsResponse(student_user_id=sid, tests=[], tests_count=0)
    analysis = ClinicalAnalysis(
        narrative="Texto clínico breve.",
        requires_clinical_referral=True,
        referral_reason="Marcadores emocionales severos",
    )
    html = render_clinical_html(
        student_name="X", advisor_name="Y",
        dossier=dossier, psy=psy, analysis=analysis,
        recs=None, finalists=None,
    )
    assert "DERIVACIÓN CLÍNICA EXTERNA" in html
    assert "Marcadores emocionales severos" in html


# ---------------------------------------------------------------------------
# Clinical analysis · rule-based pattern keyword scanner
# ---------------------------------------------------------------------------


def test_keyword_scanner_negative():
    from app.services.clinical_analysis_service import _scan_keywords, NEGATIVE_KEYWORDS
    corpus = "Me siento muy triste · tengo ansiedad casi siempre · siento miedo"
    n = _scan_keywords(corpus, NEGATIVE_KEYWORDS)
    assert n >= 3, f"Expected 3 keywords, got {n}"


def test_keyword_scanner_family_pressure():
    from app.services.clinical_analysis_service import _scan_keywords, FAMILY_PRESSURE_KEYWORDS
    corpus = "Mis papas quieren que sea ingeniero · mi mama dice que es lo mejor"
    n = _scan_keywords(corpus, FAMILY_PRESSURE_KEYWORDS)
    assert n >= 2


# ---------------------------------------------------------------------------
# Clinical PDF · finalists table rendering
# ---------------------------------------------------------------------------


def test_clinical_pdf_renders_finalists_table_when_present():
    from app.schemas.clinical import (
        DossierAspirations,
        DossierDemographics,
        DossierResponse,
        FinalistComparisonItem,
        FinalistsResponse,
        PsychometricsResponse,
    )
    from app.services.clinical_pdf_service import render_clinical_html

    sid = uuid4()
    dossier = DossierResponse(
        student_user_id=sid,
        demographics=DossierDemographics(email="x@y.com"),
        notes_by_section={},
        aspirations=DossierAspirations(),
        journey_answers={},
    )
    psy = PsychometricsResponse(student_user_id=sid, tests=[], tests_count=0)
    finalists = FinalistsResponse(
        student_user_id=sid,
        items=[
            FinalistComparisonItem(
                program_id="p1",
                program_name="Ingeniería Industrial",
                institution="Universidad X",
                country="Colombia",
                duration_months=48,
                cost_total=20000,
                currency="USD",
                advisor_pros="Está cerca de la familia",
                advisor_cons="No es internacional",
            ),
        ],
    )
    html = render_clinical_html(
        student_name="A", advisor_name="B",
        dossier=dossier, psy=psy, analysis=None,
        recs=None, finalists=finalists,
    )
    assert "Comparador de finalistas" in html
    assert "Ingeniería Industrial" in html
    assert "Está cerca de la familia" in html
