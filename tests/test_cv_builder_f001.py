"""Unit tests · CV builder (F-001 etapa 3 · 2026-06-04).

No requieren WeasyPrint/GTK: validan `build_cv_data` + `render_cv_html`.
El render real a PDF se prueba en el deploy Linux (Heroku), igual que el
PDF clínico/reporte.
"""
import datetime
from types import SimpleNamespace as NS

from app.services import cv_pdf_service as cv


def _user(**kw):
    base = dict(
        name="Camila Vargas",
        email="camila@cumbres.edu",
        english_cefr_level="B2",
        onboarding_answers={"grade": "11A"},
    )
    base.update(kw)
    return NS(**base)


def test_build_cv_data_maps_all_sections():
    acts = [
        NS(
            category="sport",
            name="Selección de voleibol",
            role="Capitana",
            hours_per_week=6,
            start_date=datetime.date(2024, 2, 1),
            end_date=None,
            description="Lidero entrenamientos.",
            achievements=["Subcampeona regional 2025"],
        ),
    ]
    tests = [
        NS(test_id="riasec", scores={"investigative": 88, "artistic": 75, "social": 60}),
        NS(test_id="mbti", scores={"type": "ENFP"}),
    ]
    profile = {
        "summary_narrative": "Camila combina análisis con sensibilidad social. " * 4,
        "strengths": ["Liderazgo", "Pensamiento crítico"],
        "interests": ["Ingeniería biomédica", "Investigación"],
        "values": ["Servicio"],
        "suggested_career_paths": ["Ciencias de la salud · Biomédica"],
    }
    data = cv.build_cv_data(
        user=_user(),
        activities=acts,
        test_results=tests,
        profile_data=profile,
        school_name="Colegio Cumbres",
    )

    assert data.student_name == "Camila Vargas"
    assert data.grade == "11A"
    assert data.english_level == "B2"
    assert data.headline == "Ciencias de la salud · Biomédica"
    # RIASEC top-3 → IAS · MBTI → ENFP
    hl = {label: highlight for label, highlight, _ in data.test_highlights}
    assert hl["Holland (RIASEC)"] == "IAS"
    assert hl["MBTI"] == "ENFP"
    assert len(data.activities) == 1
    assert data.activities[0].category_label == "Deporte"
    assert data.activities[0].period == "02/2024 – Actual"


def test_render_cv_html_contains_core_fields():
    data = cv.build_cv_data(
        user=_user(),
        activities=[],
        test_results=[],
        profile_data={"strengths": ["Liderazgo"], "interests": ["Diseño"]},
        school_name="Colegio Cumbres",
    )
    html = cv.render_cv_html(data)
    assert "Camila Vargas" in html
    assert "Colegio Cumbres" in html
    assert "Liderazgo" in html
    # Sin actividades → muestra el empty-state, no rompe
    assert "Aún no hay actividades" in html


def test_build_cv_data_without_profile_or_tests_is_safe():
    """El CV debe poder armarse aunque no haya perfil IA ni tests (siempre generable)."""
    data = cv.build_cv_data(
        user=_user(onboarding_answers={}),
        activities=[],
        test_results=None,
        profile_data=None,
        school_name=None,
    )
    assert data.summary is None
    assert data.headline is None
    assert data.test_highlights == []
    html = cv.render_cv_html(data)
    assert "Camila Vargas" in html


def test_render_cv_html_escapes_user_content():
    """Hardening F-001: datos editables por el usuario (nombre, descripción, logros)
    deben salir ESCAPADOS en el HTML→PDF · sin esto, HTML/CSS injection en el CV."""
    acts = [
        NS(
            category="other",
            name='<b>Club</b> "raro"',
            role="<i>líder</i>",
            hours_per_week=2,
            start_date=None,
            end_date=None,
            description="<script>alert(1)</script>",
            achievements=["<img src=x onerror=alert(2)>"],
        ),
    ]
    data = cv.build_cv_data(
        user=_user(name='<script>alert("xss")</script>'),
        activities=acts,
        test_results=[],
        profile_data={"strengths": ["<b>Liderazgo</b>"]},
        school_name="Colegio <Cumbres>",
    )
    html = cv.render_cv_html(data)
    # Ningún tag crudo inyectado por el usuario debe sobrevivir (los <> se escapan)
    assert "<script>" not in html
    assert "<img" not in html
    assert "<b>Club</b>" not in html
    # El contenido escapado sí debe estar presente
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html
    assert "&lt;Cumbres&gt;" in html


def test_period_label_end_only_branch():
    """Cubre el branch _period_label con solo end_date (sin start)."""
    data = cv.build_cv_data(
        user=_user(),
        activities=[
            NS(
                category="work",
                name="Práctica",
                role=None,
                hours_per_week=None,
                start_date=None,
                end_date=datetime.date(2025, 6, 1),
                description=None,
                achievements=[],
            )
        ],
        test_results=[],
        profile_data=None,
        school_name=None,
    )
    assert data.activities[0].period == "06/2025"
