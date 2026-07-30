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
    # A2 · `None` cuando no hay un resumen legible que mostrar. Antes se imprimía
    # "—", que es peor que una sigla: es una tarjeta sin dato.
    highlight: Optional[str]
    description: str
    # P1-2 · Lectura en prosa del resultado (feedback A2: "debe haber bajo cada test
    # un reporte corto, en palabras fáciles, de qué significa eso"). Sale de la
    # caché que genera P1-1: el PDF NUNCA llama a la IA — se generaría en cada
    # descarga y el reporte tardaría una eternidad. Si no hay lectura cacheada,
    # queda None y la tarjeta se ve como antes.
    reading: Optional[str] = None


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


def _cached_reading(test_result: Any) -> Optional[str]:
    """Resumen de la lectura del test, SOLO si ya está cacheada.

    P1-2 · Feedback A2: "debe haber bajo cada test un reporte corto, en palabras
    fáciles, de qué significa eso". La lectura completa la genera P1-1; acá se
    reutiliza el `summary` (2-3 frases): el formato del PDF no da para el desglose
    entero y el estudiante ya lo tiene en pantalla.

    Deliberadamente NO genera nada: si el PDF llamara a la IA por cada test, una
    descarga con 4 tests tardaría minutos y costaría en cada clic.

    Valida que el hash siga vigente — si el estudiante repitió el test, la lectura
    vieja no se imprime.
    """
    data = getattr(test_result, "interpretation", None)
    if not isinstance(data, dict):
        return None
    try:
        from app.services.test_interpretation_service import scores_hash

        vigente = getattr(test_result, "interpretation_hash", None) == scores_hash(
            getattr(test_result, "scores", {}) or {}
        )
    except Exception:
        vigente = False
    if not vigente:
        return None
    return (data.get("summary") or "").strip() or None


# A2 · Este mapa tenía TRES claves que no existen (`riasec`, `big5`, `anchors`) y le
# faltaban las tres reales (`career-anchors`, `vark`, `motivadores`). Los ids de verdad
# están en `app/data/vocational_tests.py`. El efecto: 3 de 8 tests caían al fallback
# `tid.upper()` y salían impresos como "CAREER-ANCHORS" con descripción vacía, en el
# PDF que se manda por correo a la familia — que es justo el que ella descargó y sobre
# el que escribió "muestra solo barras con siglas, sin ninguna explicación".
#
# Las claves viejas se conservan como alias: hay resultados guardados con ellas.
_TEST_LABELS = {
    "holland": ("Holland (RIASEC)", "Intereses profesionales"),
    "bigfive": ("Big Five", "Rasgos de personalidad"),
    "values": ("Valores laborales", "Lo que te mueve"),
    "career-anchors": ("Anclas de carrera", "Qué no estarías dispuesto a negociar"),
    "mbti": ("MBTI", "Tipo de personalidad"),
    "istrong": ("iStrong", "Áreas profesionales afines"),
    "vark": ("Estilos de aprendizaje (VARK)", "Cómo aprendes mejor"),
    "motivadores": ("Motivadores iniciales", "Qué te mueve a empezar"),
    # Alias históricos
    "riasec": ("Holland (RIASEC)", "Intereses profesionales"),
    "big5": ("Big Five", "Rasgos de personalidad"),
    "anchors": ("Anclas de carrera", "Qué no estarías dispuesto a negociar"),
}


def _format_es_date(dt: datetime) -> str:
    months = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return f"{dt.day} de {months[dt.month - 1]} de {dt.year}"


def _top_labels(test_id: str, scores: Dict[str, Any], cuantos: int) -> str:
    """Las N dimensiones más altas, con su NOMBRE, no con su sigla.

    Reutiliza los mapas de etiquetas de `test_interpretation_service` en vez de
    duplicarlos por tercera vez (ya están duplicados entre back y front · deuda
    anotada en P1-1).
    """
    from app.services.test_interpretation_service import _label_map

    etiquetas = _label_map(test_id)
    numericos = [
        (k, float(v))
        for k, v in scores.items()
        if k != "_extras" and isinstance(v, (int, float))
    ]
    if not numericos:
        return ""
    top = sorted(numericos, key=lambda kv: kv[1], reverse=True)[:cuantos]
    nombres = [
        (etiquetas.get(k, (k, ""))[0] if etiquetas else k) for k, _ in top
    ]
    return " · ".join(n for n in nombres if n)


def _highlight_for(test_id: str, scores: Dict[str, Any]) -> Optional[str]:
    """Un resumen corto y LEGIBLE del resultado de un test.

    A2 · La versión anterior devolvía siglas ("SIA", "O · N") o "—" para 6 de los 8
    tests, en el PDF que se manda por correo. Su queja fue literalmente esa: siglas
    sin explicación. Ahora devuelve nombres, y `None` —no "—"— cuando de verdad no
    hay nada que decir, para que la plantilla omita la línea en vez de imprimir un
    guion suelto.

    Los tests con `_extras` (MBTI, iStrong, VARK, Motivadores) traen su resultado ya
    interpretado por `scoring_service`; leerlo de ahí evita re-derivarlo mal.
    """
    if not scores:
        return None

    tid = (test_id or "").lower()
    extras = scores.get("_extras") if isinstance(scores.get("_extras"), dict) else {}

    # VARK y Motivadores ya traen una etiqueta pensada para leerse.
    if tid in {"vark", "motivadores"}:
        return (extras.get("label") or "").strip() or None

    if tid == "mbti":
        tipo = (extras.get("type") or scores.get("type") or "").strip()
        nombre = ((extras.get("type_info") or {}).get("name") or "").strip()
        if tipo and nombre:
            return f"{tipo} · {nombre}"
        return tipo or None

    if tid == "istrong":
        # iStrong guarda dos niveles: los GOT (letras tipo Holland: "R", "I", "A") y
        # los BIS, que son los intereses concretos ("R:mecanica"). Se usan los BIS
        # porque son los que dicen algo — "Mecánica e ingeniería aplicada" en vez de
        # "RIA", que es literalmente el código de su queja.
        from app.services.test_interpretation_service import _label_map

        etiquetas = _label_map("istrong")
        nombres = [
            etiquetas[b][0]
            for b in (extras.get("top_bis") or [])
            if b in etiquetas
        ]
        if nombres:
            return " · ".join(nombres[:2])
        # Sin BIS, se cae a los GOT — traducidos, nunca la letra suelta.
        gots = [
            etiquetas[g][0]
            for g in (extras.get("primary_got"), extras.get("secondary_got"))
            if g and g in etiquetas
        ]
        if gots:
            return " · ".join(gots)
        return _top_labels("istrong", scores, 2) or None

    if tid in {"holland", "riasec"}:
        return _top_labels("holland", scores, 3) or None

    if tid in {"bigfive", "big5"}:
        return _top_labels("bigfive", scores, 2) or None

    if tid == "values":
        return _top_labels("values", scores, 2) or None

    if tid in {"career-anchors", "anchors"}:
        return _top_labels("career-anchors", scores, 2) or None

    return None


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
                TestCard(
                    name=label,
                    highlight=highlight,
                    description=desc,
                    reading=_cached_reading(tr),
                )
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
                    description="Intereses profesionales",
                )
            )
        except Exception:
            # Fallback opcional · el PDF sale igual sin la tarjeta Holland,
            # pero dejamos señal para no depurar a ciegas.
            logger.warning(
                "PDF report: fallo el fallback de tarjeta Holland (se omite)",
                exc_info=True,
            )

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
