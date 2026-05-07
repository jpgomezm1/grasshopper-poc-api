"""Clinical recommendations service · GH-ADVISOR-CLINICAL Bloque F.

Takes the existing public recommendations (top 5 from ConsolidatedProfileCache)
and enriches each one with a clinical narrative for the advisor:
- psychographic_fit
- risks_or_considerations
- development_areas
- success_probability + reason

Plus an `exploration_plan` (3-5 concrete steps before deciding).

Cache strategy: piggy-back on the existing ConsolidatedProfileCache freshness.
We re-render the clinical narrative only when the public cache changes.
Cache target: simple in-cache memo via the existing
ConsolidatedProfileCache.recommendations_data mutation (not safe ·
instead persist a separate per-row `clinical_overlay` if needed in S+1).

For now: cheap deterministic narrative based on profile traits + program
metadata · no LLM call required (keeps cost low + reproducible). Future:
upgrade to LLM-augmented if tone needs more depth.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    ConsolidatedProfileCache,
    Program,
    User,
)
from app.schemas.clinical import (
    ClinicalRecommendationItem,
    ClinicalRecommendationsResponse,
    ExplorationStep,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Heuristic narrative builders
# ---------------------------------------------------------------------------


def _format_psychographic_fit(profile: Dict[str, Any], program: Optional[Program]) -> str:
    interests = profile.get("interests") or []
    work_style = profile.get("work_style") or ""
    parts: List[str] = []
    if interests and program is not None:
        parts.append(
            f"Encaja con sus áreas de interés ({', '.join(interests[:3])})"
        )
    if work_style:
        parts.append(f"compatible con un estilo de trabajo {work_style.lower()}")
    if not parts:
        return "Encaja con su perfil declarado · explorar resonancia personal en sesión."
    return ". ".join(parts).capitalize() + "."


def _format_risks(profile: Dict[str, Any], program: Optional[Program]) -> Optional[str]:
    """Surface risks based on personality dimensions vs program demands."""
    dims = {d.get("name"): d.get("level") for d in (profile.get("personality_dimensions") or []) if isinstance(d, dict)}
    risks: List[str] = []
    cons = dims.get("Conscientiousness") or dims.get("Responsabilidad")
    if cons == "bajo" and program is not None and (program.duration_months or 0) >= 36:
        risks.append(
            f"Conscientiousness baja puede ser desafío en una carrera larga ({program.duration_months} meses)."
        )
    extr = dims.get("Extraversion") or dims.get("Extraversión")
    if extr == "bajo" and program is not None and "negocios" in (program.area or "").lower():
        risks.append(
            "Programas de negocios suelen exigir alta sociabilidad · monitorear ajuste."
        )
    if not risks:
        return None
    return " ".join(risks)


def _format_development_areas(profile: Dict[str, Any], program: Optional[Program]) -> Optional[str]:
    constraints = profile.get("constraints") or []
    parts: List[str] = []
    if program is not None and program.language_requirement:
        cefr = profile.get("english_cefr_level")
        if cefr is None:
            parts.append(
                f"Validar nivel real de {program.language_requirement} antes de aplicar."
            )
        elif cefr.upper() in ("A1", "A2", "B1") and "B2" in (program.language_requirement or "").upper():
            parts.append(
                f"Subir nivel de inglés de {cefr} a {program.language_requirement}."
            )
    if "presupuesto" in " ".join(constraints).lower():
        parts.append("Plan financiero · explorar becas y financiación.")
    if not parts:
        return None
    return " ".join(parts)


def _success_probability(
    profile: Dict[str, Any], program: Optional[Program], match_score: Optional[int]
) -> Tuple[Optional[str], Optional[str]]:
    if match_score is None:
        return None, None
    if match_score >= 80:
        return "high", "Alto match score con perfil consolidado · pocos riesgos identificados."
    if match_score >= 60:
        return "medium", "Match aceptable · revisar áreas de desarrollo previo a aplicar."
    return "low", "Match bajo · explorar si la elección responde a presión externa o desinformación."


def _build_exploration_plan(profile: Dict[str, Any]) -> List[ExplorationStep]:
    return [
        ExplorationStep(
            title="Visita virtual del campus",
            description=(
                "Explorar el sitio del programa · ver fotos · agendar una sesión informativa con admisiones."
            ),
        ),
        ExplorationStep(
            title="Conversación con un alumno actual",
            description=(
                "Buscar testimonios o pedir contacto con un estudiante actual · validar la cultura real del programa."
            ),
        ),
        ExplorationStep(
            title="Investigar perfil del egresado típico",
            description=(
                "Mirar LinkedIn de 3-5 egresados · qué hacen hoy · si esa trayectoria resuena."
            ),
        ),
        ExplorationStep(
            title="Tomar una clase corta o curso piloto",
            description=(
                "Coursera/EdX/programas de verano · probar la disciplina antes de comprometerse 4 años."
            ),
        ),
        ExplorationStep(
            title="Conversar con la familia",
            description=(
                "Compartir hallazgos · escuchar reservas · validar alineación de expectativas."
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_clinical_recommendations(
    db: DBSession, student: User, top_n: int = 5
) -> ClinicalRecommendationsResponse:
    cache = (
        db.query(ConsolidatedProfileCache)
        .filter(ConsolidatedProfileCache.user_id == student.id)
        .first()
    )
    if not cache or cache.invalidated_at is not None or not cache.recommendations_data:
        return ClinicalRecommendationsResponse(
            student_user_id=student.id,
            items=[],
            exploration_plan=[],
            cached=False,
            has_recommendations=False,
            insufficient_inputs_reason=(
                "El estudiante todavía no tiene recomendaciones generadas."
            ),
        )

    profile_dict: Dict[str, Any] = {}
    try:
        profile_dict = dict(cache.profile_data or {})
    except Exception:
        profile_dict = {}
    profile_dict["english_cefr_level"] = student.english_cefr_level

    raw = list(cache.recommendations_data or [])[:top_n]

    # Resolve programs by id for richer context
    program_ids = [r.get("program_id") for r in raw if r.get("program_id")]
    programs_by_id: Dict[str, Program] = {}
    if program_ids:
        for p in db.query(Program).filter(Program.program_id.in_(program_ids)).all():
            programs_by_id[p.program_id] = p

    items: List[ClinicalRecommendationItem] = []
    for r in raw:
        pid = r.get("program_id")
        program = programs_by_id.get(pid) if pid else None
        ms = r.get("match_score")
        try:
            ms_int = int(ms) if ms is not None else None
        except Exception:
            ms_int = None
        prob, prob_reason = _success_probability(profile_dict, program, ms_int)
        items.append(
            ClinicalRecommendationItem(
                program_id=r.get("program_id"),
                program_slug=r.get("program_slug"),
                program_name=r.get("program_name") or "Programa",
                institution=r.get("institution") or (program.institution if program else None),
                country=r.get("country") or (program.country if program else None),
                match_score=ms_int,
                why_match=r.get("why_match"),
                psychographic_fit=_format_psychographic_fit(profile_dict, program),
                risks_or_considerations=_format_risks(profile_dict, program),
                development_areas=_format_development_areas(profile_dict, program),
                success_probability=prob,  # type: ignore[arg-type]
                success_probability_reason=prob_reason,
            )
        )

    return ClinicalRecommendationsResponse(
        student_user_id=student.id,
        items=items,
        exploration_plan=_build_exploration_plan(profile_dict),
        cached=True,
        cached_at=cache.generated_at,
        has_recommendations=True,
    )
