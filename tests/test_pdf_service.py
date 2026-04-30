"""Unit tests · pdf_service (GH-S7-BE-01/02/03 · D-015).

Avoid requiring Cairo/Pango locally: tests only exercise the HTML render
path. The WeasyPrint render path is exercised by an explicit smoke test
that is skipped if the library is missing.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services import pdf_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_profile(**overrides):
    base = dict(
        summary_narrative=(
            "Valeria muestra un perfil social-investigador con alta apertura a "
            "experiencias y fuerte responsabilidad. Disfruta acompañar a otros y "
            "explorar ideas a profundidad. Ambientes estructurados pero con espacio "
            "creativo son los que mejor potencian sus fortalezas."
        ),
        strengths=["Empatía", "Análisis", "Comunicación clara"],
        interests=["Educación", "Psicología", "Comunicación"],
        values=["Servicio", "Aprendizaje continuo"],
        work_style="Colaborativo y estructurado",
        learning_style="Práctico-experiencial",
        suggested_career_paths=["Educación", "Psicología clínica"],
        holland_codes=[],
        constraints=[],
        personality_dimensions=[],
        tests_used=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_user(**overrides):
    base = dict(
        id="u-1",
        name="Valeria Restrepo",
        school_id="s-1",
        onboarding_answers={"grade": "11°"},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_school(**overrides):
    base = dict(id="s-1", name="Colegio Andino", logo_url=None)
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_rec(**overrides):
    base = dict(
        program_id="p1",
        program_name="Bachelor in Education",
        why_match=("Tu perfil social + interés en educación encaja con un programa que "
                   "combina teoría educativa con práctica directa."),
        match_score=92,
        budget_fit="match",
        countries=["Canadá"],
        duration_label="4 años",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------


def test_build_payload_basics():
    payload = pdf_service.build_payload(
        user=_make_user(),
        profile=_make_profile(),
        recommendations=[_make_rec()],
        school=_make_school(),
    )
    assert payload.student_name == "Valeria Restrepo"
    assert payload.student_grade == "11°"
    assert payload.school_name == "Colegio Andino"
    assert payload.school_logo_url is None
    assert payload.summary_narrative.startswith("Valeria")
    assert len(payload.strengths) == 3
    assert len(payload.programs) == 1
    assert payload.programs[0].match_score == 92


def test_build_payload_without_school():
    payload = pdf_service.build_payload(
        user=_make_user(school_id=None),
        profile=_make_profile(),
        recommendations=[],
        school=None,
    )
    assert payload.school_name is None
    assert payload.school_logo_url is None


def test_build_payload_localized_date():
    payload = pdf_service.build_payload(
        user=_make_user(),
        profile=_make_profile(),
        recommendations=[],
        school=None,
        generated_on=datetime(2026, 4, 30),
    )
    assert "abril" in payload.generated_on
    assert "2026" in payload.generated_on
    assert "30" in payload.generated_on


def test_build_payload_test_cards_from_results():
    test_results = [
        SimpleNamespace(test_id="riasec", scores={"R": 30, "I": 65, "A": 50, "S": 80, "E": 40, "C": 25}),
        SimpleNamespace(test_id="mbti", scores={"type": "ENFJ"}),
        SimpleNamespace(test_id="bigfive", scores={"openness": 0.82, "conscientiousness": 0.78, "extraversion": 0.5, "agreeableness": 0.6, "neuroticism": 0.3}),
    ]
    payload = pdf_service.build_payload(
        user=_make_user(),
        profile=_make_profile(),
        recommendations=[],
        school=None,
        test_results=test_results,
    )
    names = {t.name for t in payload.test_cards}
    assert "Holland (RIASEC)" in names
    assert "MBTI" in names
    assert "Big Five" in names
    riasec = next(t for t in payload.test_cards if t.name == "Holland (RIASEC)")
    assert riasec.highlight == "SIA"  # Top 3: S, I, A
    mbti = next(t for t in payload.test_cards if t.name == "MBTI")
    assert mbti.highlight == "ENFJ"


# ---------------------------------------------------------------------------
# HTML render
# ---------------------------------------------------------------------------


def test_render_html_includes_student_and_school():
    payload = pdf_service.build_payload(
        user=_make_user(),
        profile=_make_profile(),
        recommendations=[_make_rec()],
        school=_make_school(),
    )
    html = pdf_service.render_report_html(payload)
    assert "Valeria Restrepo" in html
    assert "Colegio Andino" in html
    assert "Bachelor in Education" in html
    assert "Empatía" in html


def test_render_html_no_school_only_grasshopper_brand():
    payload = pdf_service.build_payload(
        user=_make_user(school_id=None),
        profile=_make_profile(),
        recommendations=[],
        school=None,
    )
    html = pdf_service.render_report_html(payload)
    assert "Valeria Restrepo" in html
    assert "Colegio Andino" not in html
    # Grasshopper logo path (svg) embedded
    assert "grasshopper_logo" in html


def test_render_html_has_all_six_pages():
    """6 pages: 1 cover + 5 .page divs (CSS @page handles paging)."""
    payload = pdf_service.build_payload(
        user=_make_user(),
        profile=_make_profile(),
        recommendations=[_make_rec()],
        school=_make_school(),
    )
    html = pdf_service.render_report_html(payload)
    assert html.count('class="page"') == 5
    assert html.count('class="cover"') == 1


def test_render_html_handles_empty_data_gracefully():
    """Estudiante recién registrado · sin tests, sin recomendaciones."""
    payload = pdf_service.build_payload(
        user=_make_user(school_id=None, onboarding_answers={}),
        profile=_make_profile(values=[], work_style=None, learning_style=None,
                              suggested_career_paths=[], strengths=["A", "B", "C"]),
        recommendations=[],
        school=None,
    )
    html = pdf_service.render_report_html(payload)
    assert "Sin resultados de tests" in html
    assert "No tenemos rutas profesionales" in html
    assert "Aún no hay programas" in html


# ---------------------------------------------------------------------------
# WeasyPrint smoke (skipped if not installed)
# ---------------------------------------------------------------------------


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _weasyprint_available(), reason="weasyprint not installed (S12 deploy concern)")
def test_render_real_pdf_bytes():
    payload = pdf_service.build_payload(
        user=_make_user(),
        profile=_make_profile(),
        recommendations=[_make_rec()],
        school=_make_school(),
    )
    pdf = pdf_service.render_report_pdf(payload)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 5_000  # sanity floor
