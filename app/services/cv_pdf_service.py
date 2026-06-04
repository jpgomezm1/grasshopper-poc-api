"""CV builder PDF service · F-001 etapa 3 (2026-06-04).

Genera la Hoja de Vida (CV) del estudiante a partir de datos que YA existen
en la plataforma — no llama a IA, así siempre se puede generar:

  1. Encabezado     · nombre · contacto · colegio · grado · nivel de inglés
  2. Perfil         · resumen del perfil consolidado (si existe en cache)
  3. Fortalezas     · fortalezas + áreas de interés + valores (del perfil)
  4. Tests          · highlights de los tests psicométricos completados
  5. Actividades    · extracurriculares (categoría · rol · horas · logros)
  6. Idiomas        · nivel de inglés (CEFR)

Mismo patrón que `clinical_pdf_service.py`: HTML con strings (sin Jinja2),
WeasyPrint lazy-import, y red de seguridad para el runtime GTK ausente en
máquinas Windows de dev (igual que B-014/B-023).

Storage: ninguno · devuelve bytes para descarga directa.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

# Reutilizamos los helpers ya probados del reporte público para no duplicar
# la extracción de highlights de cada test ni el formato de fecha es-CO.
from app.services.pdf_service import (
    _TEST_LABELS,
    _format_es_date,
    _highlight_for,
)

logger = logging.getLogger(__name__)

GENERATOR_VERSION = "cv_pdf_v1"
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

# Etiquetas legibles por categoría de actividad (coinciden con el FE/seed)
_CATEGORY_LABELS = {
    "deporte": "Deporte",
    "sport": "Deporte",
    "voluntariado": "Voluntariado",
    "volunteering": "Voluntariado",
    "arte": "Arte y cultura",
    "art": "Arte y cultura",
    "arts": "Arte y cultura",
    "academia": "Académico",
    "academic": "Académico / Clubes",
    "liderazgo": "Liderazgo",
    "leadership": "Liderazgo",
    "trabajo": "Experiencia laboral",
    "work": "Trabajo / Práctica",
    "otro": "Otros",
    "other": "Otros",
}


# ---------------------------------------------------------------------------
# Data container · primitivos · sin acceso a DB en el render
# ---------------------------------------------------------------------------


@dataclass
class CVActivity:
    category_label: str
    name: str
    role: Optional[str] = None
    hours_per_week: Optional[int] = None
    period: Optional[str] = None
    description: Optional[str] = None
    achievements: List[str] = field(default_factory=list)


@dataclass
class CVData:
    student_name: str
    generated_on: str
    email: Optional[str] = None
    school_name: Optional[str] = None
    grade: Optional[str] = None
    english_level: Optional[str] = None

    headline: Optional[str] = None
    summary: Optional[str] = None
    strengths: List[str] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    values: List[str] = field(default_factory=list)
    career_paths: List[str] = field(default_factory=list)

    # (label, highlight, description)
    test_highlights: List[tuple] = field(default_factory=list)
    activities: List[CVActivity] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Builder · mapea ORM → CVData (sin IA · todo determinístico)
# ---------------------------------------------------------------------------


def _period_label(start: Optional[date], end: Optional[date]) -> Optional[str]:
    if not start and not end:
        return None
    fmt = lambda d: f"{d.month:02d}/{d.year}" if d else "Actual"
    if start and end:
        return f"{fmt(start)} – {fmt(end)}"
    if start and not end:
        return f"{fmt(start)} – Actual"
    return fmt(end)


def build_cv_data(
    *,
    user: Any,
    activities: List[Any],
    test_results: Optional[List[Any]] = None,
    profile_data: Optional[Dict[str, Any]] = None,
    school_name: Optional[str] = None,
    generated_on: Optional[datetime] = None,
) -> CVData:
    """Construye el CVData a partir de objetos ORM/dicts. Read-only · sin DB."""
    onboarding = getattr(user, "onboarding_answers", None) or {}
    grade = None
    if isinstance(onboarding, dict):
        grade = onboarding.get("grade") or onboarding.get("grado")

    profile_data = profile_data or {}
    summary = (profile_data.get("summary_narrative") or "").strip() or None
    strengths = list(profile_data.get("strengths") or [])
    interests = list(profile_data.get("interests") or [])
    values_list = list(profile_data.get("values") or [])
    career_paths = list(profile_data.get("suggested_career_paths") or [])

    # Headline corto: primer career path o primera fortaleza
    headline = None
    if career_paths:
        headline = career_paths[0]
    elif strengths:
        headline = strengths[0]

    # Test highlights (de-dup por test_id, último gana)
    highlights: List[tuple] = []
    if test_results:
        seen: Dict[str, Any] = {}
        for tr in test_results:
            tid = (getattr(tr, "test_id", None) or "").lower()
            if tid:
                seen[tid] = tr
        for tid, tr in seen.items():
            label, desc = _TEST_LABELS.get(tid, (tid.upper(), ""))
            hl = _highlight_for(tid, getattr(tr, "scores", {}) or {})
            if hl and hl != "—":
                highlights.append((label, hl, desc))

    # Actividades
    cv_activities: List[CVActivity] = []
    for a in activities or []:
        cat = (getattr(a, "category", "") or "").lower()
        cv_activities.append(
            CVActivity(
                category_label=_CATEGORY_LABELS.get(cat, (cat or "Otros").capitalize()),
                name=getattr(a, "name", "") or "",
                role=getattr(a, "role", None),
                hours_per_week=getattr(a, "hours_per_week", None),
                period=_period_label(
                    getattr(a, "start_date", None), getattr(a, "end_date", None)
                ),
                description=getattr(a, "description", None),
                achievements=list(getattr(a, "achievements", None) or []),
            )
        )

    return CVData(
        student_name=getattr(user, "name", None) or "Estudiante",
        generated_on=_format_es_date(generated_on or datetime.utcnow()),
        email=getattr(user, "email", None),
        school_name=school_name,
        grade=grade,
        english_level=getattr(user, "english_cefr_level", None),
        headline=headline,
        summary=summary,
        strengths=strengths,
        interests=interests,
        values=values_list,
        career_paths=career_paths,
        test_highlights=highlights,
        activities=cv_activities,
    )


# ---------------------------------------------------------------------------
# HTML rendering · brand lima/navy · editorial-minimal
# ---------------------------------------------------------------------------


CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
body {
  font-family: 'Nunito', 'Helvetica Neue', Arial, sans-serif;
  color: #1f2430; font-size: 10.5pt; line-height: 1.5;
}
.header { border-bottom: 3px solid #C8D400; padding-bottom: 5mm; margin-bottom: 7mm; }
.name { font-size: 26pt; font-weight: 800; color: #164194; letter-spacing: -0.02em; margin: 0; }
.headline { font-size: 12pt; color: #5b6470; margin-top: 1mm; font-weight: 600; }
.contact { margin-top: 3mm; font-size: 9.5pt; color: #5b6470; }
.contact span { margin-right: 5mm; }
.contact b { color: #1f2430; font-weight: 700; }
h2 {
  font-size: 12.5pt; color: #164194; text-transform: uppercase;
  letter-spacing: 0.06em; margin: 7mm 0 3mm 0; padding-bottom: 1.5mm;
  border-bottom: 1px solid #e6e4d8;
}
.summary { color: #3a4150; margin: 0; }
.chips { margin: 1mm 0; }
.chip {
  display: inline-block; background: #f5f7d6; color: #5b6b00;
  border: 1px solid #d9e26a; border-radius: 20px;
  padding: 1mm 3mm; margin: 0 2mm 2mm 0; font-size: 9pt; font-weight: 600;
}
.chip.navy { background: #eef2fb; color: #164194; border-color: #c5d2ee; }
.test-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2.5mm; }
.test-card {
  border: 1px solid #e6e4d8; border-left: 3px solid #C8D400;
  border-radius: 4px; padding: 2.5mm 3.5mm; background: #fbfcf2;
}
.test-card .t-name { font-weight: 800; color: #164194; font-size: 10pt; }
.test-card .t-hl { font-weight: 800; color: #5b6b00; font-size: 13pt; margin: 0.5mm 0; }
.test-card .t-desc { color: #7a8290; font-size: 8.5pt; }
.activity { margin: 0 0 4mm 0; padding-left: 4mm; border-left: 2px solid #e6e4d8; }
.activity .a-top { display: flex; justify-content: space-between; }
.activity .a-name { font-weight: 800; color: #1f2430; font-size: 10.5pt; }
.activity .a-meta { color: #7a8290; font-size: 9pt; white-space: nowrap; }
.activity .a-cat { color: #164194; font-weight: 700; font-size: 8.5pt; text-transform: uppercase; letter-spacing: 0.04em; }
.activity .a-role { color: #5b6470; font-size: 9.5pt; }
.activity .a-desc { color: #3a4150; font-size: 9.5pt; margin-top: 0.5mm; }
.activity ul { margin: 1mm 0 0 0; padding-left: 5mm; }
.activity li { font-size: 9.5pt; margin: 0.5mm 0; }
.muted { color: #9aa0ab; font-style: italic; }
.footer { margin-top: 9mm; padding-top: 3mm; border-top: 1px solid #e6e4d8; color: #9aa0ab; font-size: 8pt; }
"""


def _chips(items: List[str], navy: bool = False) -> str:
    cls = "chip navy" if navy else "chip"
    return "".join(f'<span class="{cls}">{escape(str(i))}</span>' for i in items if i)


def _html_header(cv: CVData) -> str:
    contact_bits = []
    if cv.email:
        contact_bits.append(f"<span>✉ <b>{escape(cv.email)}</b></span>")
    if cv.school_name:
        contact_bits.append(f"<span>🏫 {escape(cv.school_name)}</span>")
    if cv.grade:
        contact_bits.append(f"<span>Grado: <b>{escape(str(cv.grade))}</b></span>")
    if cv.english_level:
        contact_bits.append(f"<span>Inglés: <b>{escape(cv.english_level)}</b></span>")
    headline = f'<div class="headline">{escape(cv.headline)}</div>' if cv.headline else ""
    return f"""
<div class="header">
  <h1 class="name">{escape(cv.student_name)}</h1>
  {headline}
  <div class="contact">{"".join(contact_bits)}</div>
</div>
"""


def _html_profile(cv: CVData) -> str:
    if not cv.summary and not cv.strengths and not cv.interests and not cv.values:
        return ""
    parts = ["<h2>Perfil</h2>"]
    if cv.summary:
        parts.append(f'<p class="summary">{escape(cv.summary)}</p>')
    if cv.strengths:
        parts.append("<h3 style='font-size:10pt;color:#5b6b00;margin:4mm 0 1mm;'>Fortalezas</h3>")
        parts.append(f'<div class="chips">{_chips(cv.strengths)}</div>')
    if cv.interests:
        parts.append("<h3 style='font-size:10pt;color:#164194;margin:3mm 0 1mm;'>Áreas de interés</h3>")
        parts.append(f'<div class="chips">{_chips(cv.interests, navy=True)}</div>')
    if cv.values:
        parts.append("<h3 style='font-size:10pt;color:#5b6b00;margin:3mm 0 1mm;'>Valores</h3>")
        parts.append(f'<div class="chips">{_chips(cv.values)}</div>')
    return "".join(parts)


def _html_tests(cv: CVData) -> str:
    if not cv.test_highlights:
        return ""
    cards = []
    for label, hl, desc in cv.test_highlights:
        cards.append(
            f'<div class="test-card"><div class="t-name">{escape(label)}</div>'
            f'<div class="t-hl">{escape(str(hl))}</div>'
            f'<div class="t-desc">{escape(desc or "")}</div></div>'
        )
    return f'<h2>Resultados de tests</h2><div class="test-grid">{"".join(cards)}</div>'


def _html_activities(cv: CVData) -> str:
    if not cv.activities:
        return (
            '<h2>Actividades extracurriculares</h2>'
            '<p class="muted">Aún no hay actividades registradas. '
            'Agrégalas en "Mis actividades" para enriquecer tu CV.</p>'
        )
    blocks = []
    for a in cv.activities:
        meta = []
        if a.period:
            meta.append(escape(a.period))
        if a.hours_per_week:
            meta.append(f"{a.hours_per_week} h/sem")
        meta_html = f'<div class="a-meta">{" · ".join(meta)}</div>' if meta else ""
        role_html = f'<div class="a-role">{escape(a.role)}</div>' if a.role else ""
        desc_html = f'<div class="a-desc">{escape(a.description)}</div>' if a.description else ""
        ach_html = ""
        if a.achievements:
            lis = "".join(f"<li>{escape(x)}</li>" for x in a.achievements if x)
            if lis:
                ach_html = f"<ul>{lis}</ul>"
        blocks.append(
            f'<div class="activity"><div class="a-cat">{escape(a.category_label)}</div>'
            f'<div class="a-top"><div class="a-name">{escape(a.name)}</div>{meta_html}</div>'
            f"{role_html}{desc_html}{ach_html}</div>"
        )
    return f'<h2>Actividades extracurriculares</h2>{"".join(blocks)}'


def render_cv_html(cv: CVData) -> str:
    return f"""<!doctype html>
<html lang="es-CO">
<head>
  <meta charset="utf-8">
  <title>Hoja de Vida · {escape(cv.student_name)}</title>
  <style>{CSS}</style>
</head>
<body>
  {_html_header(cv)}
  {_html_profile(cv)}
  {_html_tests(cv)}
  {_html_activities(cv)}
  <div class="footer">
    Hoja de Vida generada con Grasshopper · {escape(cv.generated_on)} ·
    documento personal del estudiante.
  </div>
</body>
</html>
"""


def render_cv_pdf(cv: CVData) -> bytes:
    """Render a PDF bytes vía WeasyPrint (lazy import · igual que clinical/report).

    Maneja el caso GTK ausente (Windows dev) levantando RuntimeError con un
    mensaje claro para que el endpoint devuelva 503 en vez de un 500 opaco.
    """
    html = render_cv_html(cv)

    _gtk_hint = (
        "GTK runtime missing on this host (libgobject/cairo/pango). "
        "El CV PDF se genera en Heroku/Linux; en Windows local instala GTK."
    )
    # OJO: en Windows, `import weasyprint` lanza OSError (libgobject) al IMPORTAR,
    # no al renderizar. Por eso el import va dentro del mismo try que atrapa GTK.
    try:
        from weasyprint import HTML  # type: ignore

        pdf_bytes = HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "weasyprint not installed · agregá `weasyprint==60.2` a requirements.txt"
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"{_gtk_hint} Underlying error: {exc}") from exc
    except BaseExceptionGroup as eg:  # py3.11+ · WeasyPrint puede envolver el OSError
        os_errors = [e for e in eg.exceptions if isinstance(e, OSError)]
        if os_errors:
            raise RuntimeError(f"{_gtk_hint} Underlying error: {os_errors[0]}") from eg
        raise
    if not pdf_bytes:
        raise RuntimeError("WeasyPrint returned empty PDF for CV · investigar")
    return pdf_bytes
