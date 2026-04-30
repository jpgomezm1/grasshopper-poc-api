"""PDF rendering service · Sprint 7.

GH-S7-BE-01/02/03 · D-015 (WeasyPrint chosen).

Public API:
    render_report_pdf(payload: ReportPayload) -> bytes
    build_payload(user, profile, recommendations, school) -> ReportPayload
    PAGE_COUNT  · constant exposed for QA

Why this module:
- Single rendering surface for the 6-page A4 co-branded report.
- The HTML+CSS template lives next door (templates/report_pdf.html).
- WeasyPrint is imported lazily so unit tests that don't render real PDFs
  don't need Cairo/Pango installed (CI / local dev OK).

Layout (per S3-DESIGN-04 wireframe + S6 deliverables):
    1. Portada                · co-brand strip + student name + date
    2. Perfil consolidado     · summary_narrative + strengths
    3. Resultados de tests    · 4 cards (Holland/MBTI/Big5/iStrong)
    4. Valores y motivaciones · derived from profile.values + work_style
    5. Rutas profesionales    · suggested_career_paths
    6. Programas recomendados · top recommendations from S6

Co-branding:
- Grasshopper logo always shown (default asset under static/)
- School logo shown when User.school.logo_url is set (resolved upstream)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Page count is part of the contract · QA validates it
PAGE_COUNT = 6
GENERATOR_VERSION = "report_pdf_v1"
TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "report_pdf.html"
DEFAULT_LOGO_PATH = Path(__file__).parent.parent / "templates" / "static" / "grasshopper_logo.svg"


# -----------------------------------------------------------------------------
# Payload
# -----------------------------------------------------------------------------


@dataclass
class TestCard:
    """A test result rendered as a card in page 3."""
    name: str
    highlight: str
    description: str


@dataclass
class ProgramItem:
    """A recommended program rendered as a card in page 6."""
    title: str
    institution: str
    location: str
    duration: str
    match_score: int
    why_match: str
    budget_fit: Optional[str] = None


@dataclass
class ReportPayload:
    """Everything the template needs · pre-resolved · no DB access in render.

    All fields are plain primitives so the template is trivially testable
    and serialization is stable for snapshot tests.
    """

    # Header / cover
    student_name: str
    student_grade: Optional[str]
    school_name: Optional[str]
    school_logo_url: Optional[str]
    grasshopper_logo_path: str
    generated_on: str  # human-readable date in es-CO
    locale: str = "es-CO"

    # Page 2 · profile
    summary_narrative: str = ""
    strengths: List[str] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)

    # Page 3 · tests
    test_cards: List[TestCard] = field(default_factory=list)

    # Page 4 · values & motivations
    values: List[str] = field(default_factory=list)
    work_style: Optional[str] = None
    learning_style: Optional[str] = None

    # Page 5 · career paths
    career_paths: List[str] = field(default_factory=list)

    # Page 6 · recommended programs
    programs: List[ProgramItem] = field(default_factory=list)

    # Footer
    contact_email_grasshopper: str = "hola@grasshopper.co"
    contact_url_grasshopper: str = "www.grasshopper.co"
    contact_email_school: Optional[str] = None
    confidentiality_note: str = "Documento confidencial · uso personal y familiar"

    def to_template_context(self) -> Dict[str, Any]:
        """Serialize for Jinja consumption."""
        return {
            **asdict(self),
            "page_count": PAGE_COUNT,
            "generator_version": GENERATOR_VERSION,
        }


# -----------------------------------------------------------------------------
# Payload builder · maps DB models → template context
# -----------------------------------------------------------------------------


_TEST_LABELS = {
    "riasec": ("Holland (RIASEC)", "Intereses vocacionales"),
    "holland": ("Holland (RIASEC)", "Intereses vocacionales"),
    "mbti": ("MBTI", "Tipo de personalidad"),
    "bigfive": ("Big Five", "Rasgos de personalidad"),
    "big5": ("Big Five", "Rasgos de personalidad"),
    "values": ("Valores laborales", "Lo que te mueve"),
    "istrong": ("iStrong", "Áreas afines"),
    "anchors": ("Anclas de carrera", "Motivadores profesionales"),
}


def _format_es_date(dt: datetime) -> str:
    months = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return f"{dt.day} de {months[dt.month - 1]} de {dt.year}"


def _highlight_for(test_id: str, scores: Dict[str, Any]) -> str:
    """Pick a short, human-readable highlight from a test's scores blob."""
    if not scores:
        return "—"

    tid = (test_id or "").lower()

    if tid in {"riasec", "holland"}:
        # Top 3 letters from RIASEC scores
        try:
            top = sorted(
                ((k, float(v)) for k, v in scores.items() if isinstance(v, (int, float))),
                key=lambda kv: kv[1],
                reverse=True,
            )[:3]
            code = "".join(k[0].upper() for k, _ in top if k)
            return code or "—"
        except Exception:
            return "—"

    if tid == "mbti":
        return str(scores.get("type") or scores.get("code") or "—")

    if tid in {"bigfive", "big5"}:
        try:
            top = sorted(
                ((k, float(v)) for k, v in scores.items() if isinstance(v, (int, float))),
                key=lambda kv: kv[1],
                reverse=True,
            )[:2]
            label = " · ".join(k.capitalize() for k, _ in top)
            return label or "—"
        except Exception:
            return "—"

    if tid == "istrong":
        # iStrong stores top areas (D-011 banco propio)
        top_areas = scores.get("top_areas") or scores.get("areas") or []
        if isinstance(top_areas, list) and top_areas:
            initials = "".join(str(a)[0].upper() for a in top_areas[:3] if a)
            return initials or "—"
        return "—"

    if tid == "values":
        top_values = scores.get("top_values") or scores.get("values") or []
        if isinstance(top_values, list) and top_values:
            return " · ".join(str(v).capitalize() for v in top_values[:2])
        return "—"

    return "—"


def build_payload(
    *,
    user: Any,
    profile: Any,
    recommendations: List[Any],
    school: Any = None,
    grasshopper_logo_path: Optional[str] = None,
    school_logo_url: Optional[str] = None,
    generated_on: Optional[datetime] = None,
    test_results: Optional[List[Any]] = None,
    locale: str = "es-CO",
) -> ReportPayload:
    """Map ORM/Pydantic objects → ReportPayload.

    - `user`         · ORM User  (provides name · school · grade if available)
    - `profile`      · ConsolidatedProfile (Pydantic)  from S6
    - `recommendations` · List[RecommendedProgram] from S6
    - `school`       · ORM School (optional · derives name + logo)
    - `test_results` · List[VocationalTestResult] (optional · for cards)

    All inputs are read-only · no DB calls.
    """
    # --- Header ---
    grade = None
    onboarding = getattr(user, "onboarding_answers", None) or {}
    if isinstance(onboarding, dict):
        grade = onboarding.get("grade") or onboarding.get("grado")

    school_name = getattr(school, "name", None) if school else None
    school_logo = school_logo_url
    if school_logo is None and school is not None:
        school_logo = getattr(school, "logo_url", None)

    logo_path = grasshopper_logo_path or str(DEFAULT_LOGO_PATH)
    gen_on = generated_on or datetime.utcnow()

    # --- Pages 2-4 from profile ---
    summary_narrative = getattr(profile, "summary_narrative", "") or ""
    strengths = list(getattr(profile, "strengths", []) or [])
    interests = list(getattr(profile, "interests", []) or [])
    values_list = list(getattr(profile, "values", []) or [])
    work_style = getattr(profile, "work_style", None)
    learning_style = getattr(profile, "learning_style", None)
    career_paths = list(getattr(profile, "suggested_career_paths", []) or [])

    # --- Page 3 · tests ---
    test_cards: List[TestCard] = []
    if test_results:
        # de-dup by test_id, keep latest
        seen: Dict[str, Any] = {}
        for tr in test_results:
            tid = getattr(tr, "test_id", None) or ""
            if not tid:
                continue
            seen[tid.lower()] = tr
        for tid, tr in seen.items():
            label, desc = _TEST_LABELS.get(tid, (tid.upper(), ""))
            highlight = _highlight_for(tid, getattr(tr, "scores", {}) or {})
            test_cards.append(
                TestCard(name=label, highlight=highlight, description=desc)
            )
    # Fallback if no tests but profile has Holland codes
    if not test_cards and getattr(profile, "holland_codes", None):
        codes = getattr(profile, "holland_codes")
        try:
            label = "".join(c.code for c in codes[:3])
            test_cards.append(
                TestCard(
                    name="Holland (RIASEC)",
                    highlight=label,
                    description="Intereses vocacionales",
                )
            )
        except Exception:
            pass

    # --- Page 6 · programs ---
    programs: List[ProgramItem] = []
    for r in recommendations or []:
        countries = getattr(r, "countries", None) or []
        location = ", ".join(countries) if countries else ""
        institution = getattr(r, "program_name", "") or ""
        duration_label = getattr(r, "duration_label", None) or ""
        programs.append(
            ProgramItem(
                title=getattr(r, "program_name", "") or "",
                institution=institution,
                location=location,
                duration=duration_label,
                match_score=int(getattr(r, "match_score", 0) or 0),
                why_match=getattr(r, "why_match", "") or "",
                budget_fit=getattr(r, "budget_fit", None),
            )
        )

    return ReportPayload(
        student_name=getattr(user, "name", None) or "Estudiante",
        student_grade=grade,
        school_name=school_name,
        school_logo_url=school_logo,
        grasshopper_logo_path=logo_path,
        generated_on=_format_es_date(gen_on),
        locale=locale,
        summary_narrative=summary_narrative,
        strengths=strengths,
        interests=interests,
        test_cards=test_cards,
        values=values_list,
        work_style=work_style,
        learning_style=learning_style,
        career_paths=career_paths,
        programs=programs,
        contact_email_school=None,
    )


# -----------------------------------------------------------------------------
# Renderer · lazy-loads weasyprint
# -----------------------------------------------------------------------------


def _load_template_html(payload: ReportPayload) -> str:
    """Render the Jinja2 template with the payload context.

    Falls back to a tiny inline template if templates/report_pdf.html is
    missing (defensive · should not happen in production).
    """
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Jinja2 not available · ensure FastAPI extras installed"
        ) from exc

    if not TEMPLATE_PATH.exists():
        logger.warning("report_pdf.html missing · using inline fallback")
        return _inline_fallback_template().render(**payload.to_template_context())

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_PATH.parent)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(TEMPLATE_PATH.name)
    return template.render(**payload.to_template_context())


def _inline_fallback_template():  # pragma: no cover
    from jinja2 import Template
    return Template(
        "<html><body><h1>{{ student_name }}</h1>"
        "<p>{{ summary_narrative }}</p></body></html>"
    )


def render_report_pdf(payload: ReportPayload) -> bytes:
    """Render the report HTML+CSS to PDF bytes using WeasyPrint.

    Raises:
        RuntimeError if WeasyPrint is not available (deploy issue · S12).
    """
    html_str = _load_template_html(payload)

    try:
        from weasyprint import HTML, CSS  # type: ignore
    except ImportError as exc:  # pragma: no cover · exercised in S12 build
        raise RuntimeError(
            "weasyprint not installed · agregá `weasyprint==60.2` a requirements.txt "
            "y el buildpack APT en Heroku (D-015 · runbook docs/RUNBOOK_REPORTS.md)"
        ) from exc

    base_url = str(TEMPLATE_PATH.parent)
    pdf_bytes = HTML(string=html_str, base_url=base_url).write_pdf()
    if not pdf_bytes:
        raise RuntimeError("WeasyPrint returned empty PDF · investigar template")

    logger.info(
        "pdf rendered student=%s pages~%d size=%d",
        payload.student_name,
        PAGE_COUNT,
        len(pdf_bytes),
    )
    return pdf_bytes


def render_report_html(payload: ReportPayload) -> str:
    """Render only the HTML (without WeasyPrint).

    Useful for unit tests that want to assert on the markup without
    requiring Cairo/Pango locally, and for QA visual inspection.
    """
    return _load_template_html(payload)
