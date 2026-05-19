"""Clinical PDF service · GH-ADVISOR-CLINICAL Bloque H.

Generates an internal 8-12 page PDF for the gh_advisor with:
1. Portada (estudiante · orientadora · fecha)
2. Ficha clínica (dossier todas las secciones)
3. Vista psicométrica (los 6 tests)
4. Análisis IA clínico (narrative · strengths · growth_areas · risks · sessions)
5. Patrones detectados con alertas
6. Recomendaciones con interpretación clínica (top 5)
7. Comparador finalistas (si advisor lo seleccionó)
8. Espacio para notas manuscritas

Different from the public PDF (`pdf_service.py`) which is the cálido / 6-page
report shown to the student.

Storage: stub local · returns bytes for direct download · no persistence.
"""
from __future__ import annotations

import logging
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.schemas.clinical import (
    ClinicalAnalysis,
    ClinicalRecommendationsResponse,
    DossierResponse,
    FinalistsResponse,
    PsychometricsResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()

GENERATOR_VERSION = "clinical_pdf_v1"
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


# ---------------------------------------------------------------------------
# HTML rendering · plain string (no Jinja2 dep) · trivially testable
# ---------------------------------------------------------------------------


CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body {
  font-family: 'Nunito', 'Helvetica Neue', Arial, sans-serif;
  color: #1f2937;
  font-size: 10.5pt;
  line-height: 1.5;
}
h1, h2, h3, h4 {
  color: #1e3a8a;
  font-family: 'Quicksand', 'Nunito', sans-serif;
  margin: 0 0 6mm 0;
}
h1 { font-size: 22pt; }
h2 { font-size: 15pt; border-bottom: 2px solid #d1fae5; padding-bottom: 3mm; margin-top: 8mm; }
h3 { font-size: 12pt; color: #065f46; margin-top: 5mm; }
.cover { text-align: center; padding-top: 40mm; }
.cover h1 { color: #065f46; font-size: 28pt; }
.cover .subtitle { color: #6b7280; font-size: 12pt; margin-top: 4mm; }
.cover .meta { margin-top: 30mm; font-size: 11pt; }
.page-break { page-break-before: always; }
.label { color: #6b7280; font-size: 9.5pt; }
.value { font-weight: 600; }
.kv { display: flex; gap: 4mm; margin: 1mm 0; }
.kv .label { min-width: 35mm; }
.section { margin-bottom: 6mm; }
ul { margin: 2mm 0; padding-left: 6mm; }
li { margin: 1mm 0; }
.note { background: #f0fdf4; border-left: 3px solid #16a34a; padding: 3mm 4mm; margin: 3mm 0; border-radius: 2px; }
.risk-high { background: #fef2f2; border-left: 3px solid #dc2626; padding: 3mm 4mm; margin: 3mm 0; border-radius: 2px; }
.risk-medium { background: #fffbeb; border-left: 3px solid #d97706; padding: 3mm 4mm; margin: 3mm 0; border-radius: 2px; }
.risk-low { background: #f0f9ff; border-left: 3px solid #0284c7; padding: 3mm 4mm; margin: 3mm 0; border-radius: 2px; }
.referral {
  background: #fef2f2;
  border: 2px solid #dc2626;
  padding: 4mm;
  margin: 5mm 0;
  border-radius: 4px;
  color: #991b1b;
  font-weight: 600;
}
.scores-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3mm;
}
.score-card {
  border: 1px solid #d1fae5;
  padding: 3mm;
  border-radius: 4px;
  background: #fafafa;
}
.score-card h4 { margin: 0 0 2mm 0; color: #065f46; font-size: 11pt; }
.muted { color: #6b7280; font-size: 9.5pt; }
.recommendation {
  border: 1px solid #e5e7eb;
  padding: 4mm;
  margin: 3mm 0;
  border-radius: 4px;
}
.recommendation h4 { margin: 0; color: #065f46; }
.notes-space {
  border: 1.5px dashed #cbd5e1;
  height: 60mm;
  margin: 4mm 0;
  border-radius: 4px;
}
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; }
th { background: #ecfccb; color: #365314; text-align: left; padding: 2mm 3mm; }
td { padding: 2mm 3mm; vertical-align: top; border-bottom: 1px solid #f0f0f0; }
.confidential {
  background: #fef2f2;
  color: #991b1b;
  padding: 2mm 4mm;
  border-radius: 3px;
  display: inline-block;
  font-size: 9pt;
  font-weight: 600;
}
"""


def _html_cover(student_name: str, advisor_name: str, generated_at: datetime) -> str:
    return f"""
<section class="cover">
  <h1>Expediente clínico</h1>
  <div class="subtitle">Documento interno · uso del orientador · CONFIDENCIAL</div>
  <div class="meta">
    <div><span class="label">Estudiante:</span> <span class="value">{escape(student_name)}</span></div>
    <div><span class="label">Orientadora:</span> <span class="value">{escape(advisor_name)}</span></div>
    <div><span class="label">Generado:</span> <span class="value">{generated_at.strftime('%Y-%m-%d %H:%M')}</span></div>
    <div style="margin-top:8mm;"><span class="confidential">USO INTERNO · NO COMPARTIR CON EL ESTUDIANTE</span></div>
  </div>
</section>
"""


def _html_dossier(dossier: DossierResponse) -> str:
    d = dossier.demographics
    rows = []
    rows.append(f'<div class="kv"><span class="label">Nombre:</span> <span class="value">{escape(d.name or "—")}</span></div>')
    rows.append(f'<div class="kv"><span class="label">Email:</span> <span class="value">{escape(d.email)}</span></div>')
    if d.age is not None:
        rows.append(f'<div class="kv"><span class="label">Edad:</span> <span class="value">{d.age}</span></div>')
    if d.school_name:
        rows.append(f'<div class="kv"><span class="label">Colegio:</span> <span class="value">{escape(d.school_name)}</span></div>')
    if d.english_cefr_level:
        rows.append(f'<div class="kv"><span class="label">Inglés (CEFR):</span> <span class="value">{escape(d.english_cefr_level)}</span></div>')
    if d.budget_band:
        rows.append(f'<div class="kv"><span class="label">Presupuesto:</span> <span class="value">{escape(d.budget_band)}</span></div>')
    if d.preferred_countries:
        rows.append(f'<div class="kv"><span class="label">Países preferidos:</span> <span class="value">{escape(", ".join(d.preferred_countries))}</span></div>')
    demo = "\n".join(rows)

    sections_html = []
    section_titles = {
        "demographics": "Datos demográficos (notas)",
        "family": "Contexto familiar",
        "academic": "Trayectoria académica",
        "hobbies": "Hobbies y actividades",
        "constraints": "Restricciones",
        "aspirations": "Aspiraciones",
        "general": "Notas generales",
    }
    for key, title in section_titles.items():
        notes = dossier.notes_by_section.get(key, [])
        if not notes:
            continue
        notes_html = "\n".join(
            f'<div class="note"><div class="muted">{n.created_at.strftime("%Y-%m-%d")}</div>'
            f'<div>{escape(n.content)}</div></div>'
            for n in notes
        )
        sections_html.append(f"<h3>{title}</h3>{notes_html}")

    aspirations = ""
    if dossier.aspirations.declared or dossier.aspirations.inferred:
        decl = ", ".join(dossier.aspirations.declared) or "—"
        inf = ", ".join(dossier.aspirations.inferred) or "—"
        aspirations = f"""
<h3>Aspiraciones declaradas vs inferidas</h3>
<div class="kv"><span class="label">Declaradas:</span> <span class="value">{escape(decl)}</span></div>
<div class="kv"><span class="label">Inferidas:</span> <span class="value">{escape(inf)}</span></div>
"""
    return f"""
<section class="page-break">
  <h2>Ficha clínica</h2>
  <div class="section">{demo}</div>
  {aspirations}
  {"".join(sections_html) if sections_html else '<div class="muted">Sin notas registradas aún.</div>'}
</section>
"""


def _html_psychometrics(psy: PsychometricsResponse) -> str:
    if psy.tests_count == 0:
        return '<section class="page-break"><h2>Vista psicométrica</h2><div class="muted">Sin tests registrados.</div></section>'

    cards = []
    for t in psy.tests:
        scores_str = ", ".join(
            f"{k}: {v}" for k, v in (t.scores or {}).items() if not isinstance(v, (dict, list))
        )[:300]
        cards.append(
            f'<div class="score-card"><h4>{escape(t.test_id.upper())}</h4>'
            f'<div class="muted">{escape(scores_str) or "—"}</div></div>'
        )
    grid = f'<div class="scores-grid">{"".join(cards)}</div>'

    patterns = ""
    if psy.cross_patterns:
        rows = []
        for p in psy.cross_patterns:
            rows.append(
                f'<div class="note"><strong>{escape(p.label)}</strong>'
                f'<div>{escape(p.description)}</div></div>'
            )
        patterns = f'<h3>Patrones cruzados</h3>{"".join(rows)}'

    inc = ""
    if psy.inconsistencies:
        rows = []
        for i in psy.inconsistencies:
            cls = f"risk-{i.severity}"
            rows.append(
                f'<div class="{cls}"><strong>{escape(i.label)}</strong>'
                f'<div>{escape(i.description)}</div></div>'
            )
        inc = f'<h3>Inconsistencias detectadas</h3>{"".join(rows)}'

    return f"""
<section class="page-break">
  <h2>Vista psicométrica · {psy.tests_count} tests</h2>
  {grid}
  {patterns}
  {inc}
</section>
"""


def _html_clinical_analysis(an: Optional[ClinicalAnalysis]) -> str:
    if not an:
        return '<section class="page-break"><h2>Análisis clínico</h2><div class="muted">No se ha generado el análisis IA aún.</div></section>'

    referral = ""
    if an.requires_clinical_referral:
        referral = (
            f'<div class="referral">CONSIDERAR DERIVACIÓN CLÍNICA EXTERNA · '
            f'{escape(an.referral_reason or "Ver protocolo")}</div>'
        )

    narrative_html = "".join(
        f"<p>{escape(p)}</p>" for p in (an.narrative or "").split("\n\n") if p.strip()
    )

    strengths = "".join(
        f"<li><strong>{escape(s.title)}.</strong> {escape(s.description)}</li>"
        for s in (an.strengths or [])
    )
    growth = "".join(
        f"<li><strong>{escape(g.title)}.</strong> {escape(g.description)}</li>"
        for g in (an.growth_areas or [])
    )
    risks = "".join(
        f'<div class="risk-{r.severity}"><strong>{escape(r.title)} · {r.severity.upper()}.</strong> {escape(r.description)}</div>'
        for r in (an.potential_risks or [])
    )
    sessions = "".join(
        f'<div class="note"><strong>{escape(s.topic)}.</strong> {escape(s.why)}'
        f'{(" · <em>" + escape(s.suggested_exercise) + "</em>") if s.suggested_exercise else ""}</div>'
        for s in (an.session_suggestions or [])
    )

    patterns = ""
    if an.behavioral_patterns:
        rows = []
        for p in an.behavioral_patterns:
            rows.append(
                f'<div class="risk-{p.severity}"><strong>{escape(p.pattern)}</strong> '
                f'(confianza {round(p.confidence, 2)})<div>{escape(p.evidence)}</div>'
                f'<div class="muted">Intervención sugerida: {escape(p.suggested_intervention)}</div></div>'
            )
        patterns = f'<h3>Patrones detectados</h3>{"".join(rows)}'

    return f"""
<section class="page-break">
  <h2>Análisis clínico</h2>
  {referral}
  <div class="section">{narrative_html}</div>
  <h3>Fortalezas psicológicas</h3>
  <ul>{strengths or "<li>—</li>"}</ul>
  <h3>Áreas de desarrollo</h3>
  <ul>{growth or "<li>—</li>"}</ul>
  <h3>Riesgos potenciales</h3>
  {risks or '<div class="muted">Sin riesgos significativos identificados.</div>'}
  <h3>Sugerencias para próxima sesión</h3>
  {sessions or '<div class="muted">—</div>'}
  {patterns}
</section>
"""


def _html_clinical_recommendations(rec: Optional[ClinicalRecommendationsResponse]) -> str:
    if not rec or not rec.has_recommendations:
        return '<section class="page-break"><h2>Recomendaciones con interpretación clínica</h2><div class="muted">Sin recomendaciones cacheadas.</div></section>'

    items_html = []
    for it in rec.items:
        sub = []
        if it.psychographic_fit:
            sub.append(f"<div><strong>Encaje:</strong> {escape(it.psychographic_fit)}</div>")
        if it.risks_or_considerations:
            sub.append(f"<div><strong>Consideraciones:</strong> {escape(it.risks_or_considerations)}</div>")
        if it.development_areas:
            sub.append(f"<div><strong>A desarrollar:</strong> {escape(it.development_areas)}</div>")
        if it.success_probability:
            sub.append(
                f"<div><strong>Probabilidad de éxito:</strong> {it.success_probability.upper()} · "
                f'{escape(it.success_probability_reason or "")}</div>'
            )
        items_html.append(
            f'<div class="recommendation">'
            f'<h4>{escape(it.program_name)}</h4>'
            f'<div class="muted">{escape(it.institution or "")} · {escape(it.country or "")}</div>'
            f'{"".join(sub)}'
            f'</div>'
        )

    plan = ""
    if rec.exploration_plan:
        steps = "".join(
            f"<li><strong>{escape(s.title)}.</strong> {escape(s.description)}</li>"
            for s in rec.exploration_plan
        )
        plan = f"<h3>Plan de exploración previo a decidir</h3><ol>{steps}</ol>"

    return f"""
<section class="page-break">
  <h2>Recomendaciones con interpretación clínica</h2>
  {"".join(items_html)}
  {plan}
</section>
"""


def _html_finalists(fin: Optional[FinalistsResponse]) -> str:
    if not fin or not fin.items:
        return ""
    rows = []
    for f in fin.items:
        rows.append(
            f"<tr>"
            f"<td><strong>{escape(f.program_name)}</strong><div class='muted'>{escape(f.institution or '')}</div></td>"
            f"<td>{escape(f.country or '')}</td>"
            f"<td>{f.duration_months or '—'} m</td>"
            f"<td>{f.cost_total or '—'} {escape(f.currency or '')}</td>"
            f"<td>{escape(f.psychographic_fit_short or '—')}</td>"
            f"<td>{escape(f.advisor_pros or '')}</td>"
            f"<td>{escape(f.advisor_cons or '')}</td>"
            f"</tr>"
        )
    return f"""
<section class="page-break">
  <h2>Comparador de finalistas</h2>
  <table>
    <thead>
      <tr>
        <th>Programa</th>
        <th>País</th>
        <th>Duración</th>
        <th>Costo</th>
        <th>Encaje psicográfico</th>
        <th>Pros (advisor)</th>
        <th>Contras (advisor)</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows)}
    </tbody>
  </table>
</section>
"""


def _html_notes_space() -> str:
    return """
<section class="page-break">
  <h2>Notas manuscritas</h2>
  <div class="muted">Espacio para escribir durante la sesión.</div>
  <div class="notes-space"></div>
  <div class="notes-space"></div>
  <div class="notes-space"></div>
</section>
"""


def render_clinical_html(
    student_name: str,
    advisor_name: str,
    dossier: DossierResponse,
    psy: PsychometricsResponse,
    analysis: Optional[ClinicalAnalysis],
    recs: Optional[ClinicalRecommendationsResponse],
    finalists: Optional[FinalistsResponse],
    generated_at: Optional[datetime] = None,
) -> str:
    gen = generated_at or datetime.utcnow()
    return f"""<!doctype html>
<html lang="es-CO">
<head>
  <meta charset="utf-8">
  <title>Expediente clínico · {escape(student_name)}</title>
  <style>{CSS}</style>
</head>
<body>
  {_html_cover(student_name, advisor_name, gen)}
  {_html_dossier(dossier)}
  {_html_psychometrics(psy)}
  {_html_clinical_analysis(analysis)}
  {_html_clinical_recommendations(recs)}
  {_html_finalists(finalists)}
  {_html_notes_space()}
</body>
</html>
"""


def render_clinical_pdf(
    student_name: str,
    advisor_name: str,
    dossier: DossierResponse,
    psy: PsychometricsResponse,
    analysis: Optional[ClinicalAnalysis],
    recs: Optional[ClinicalRecommendationsResponse],
    finalists: Optional[FinalistsResponse],
    generated_at: Optional[datetime] = None,
) -> bytes:
    """Render to PDF bytes via WeasyPrint (lazy import · same pattern as pdf_service)."""
    html = render_clinical_html(
        student_name=student_name,
        advisor_name=advisor_name,
        dossier=dossier,
        psy=psy,
        analysis=analysis,
        recs=recs,
        finalists=finalists,
        generated_at=generated_at,
    )
    try:
        from weasyprint import HTML  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "weasyprint not installed · agregá `weasyprint==60.2` a requirements.txt"
        ) from exc
    # GH-LOCAL-QA-RONDA2 · B-014 · GTK runtime (libgobject/cairo/pango) may be
    # missing on Windows dev boxes even when weasyprint imports fine. Catch
    # OSError from `HTML(...).write_pdf()` so the endpoint can convert it into
    # a clean 503 instead of bubbling up a stack trace. The CLINICAL_PDF_ENABLED
    # feature flag should be set to false in those environments; this is the
    # safety net in case it isn't.
    try:
        pdf_bytes = HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()
    except OSError as exc:
        raise RuntimeError(
            "GTK runtime missing on this host (libgobject/cairo/pango). "
            "Set CLINICAL_PDF_ENABLED=false in .env or install the GTK libs. "
            f"Underlying error: {exc}"
        ) from exc
    if not pdf_bytes:
        raise RuntimeError("WeasyPrint returned empty PDF for clinical · investigar")
    return pdf_bytes
