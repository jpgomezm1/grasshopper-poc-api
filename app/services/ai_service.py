"""AI generation service for journey content."""

import logging
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.core.ai_client import load_prompt, call_claude_with_meta
from app.core.ai_json import parse_ai_json
from app.services.ai_usage_service import record_ai_usage

settings = get_settings()
from app.schemas.ai_outputs import (
    EmpathyReflectionOutput,
    PartialSummaryOutput,
    SynthesisOutput,
    SynthesisChip,
    RouteSuggestionOutput,
    GeneratedRoute,
    AdvisorBriefOutput,
)

logger = logging.getLogger(__name__)


def _track_journey_usage(
    db: Optional[DBSession],
    user_id: Optional[UUID],
    metadata: dict,
    feature: str,
) -> None:
    """Registra una llamada IA del journey en ai_usage_log (M-001).

    Best-effort: sin ``db`` (p.ej. tests que llaman la función suelta) no
    hace nada. ``user_id`` es ``None`` en journeys anónimos — la tabla lo
    permite. ``record_ai_usage`` nunca levanta.
    """
    if db is None:
        return
    record_ai_usage(
        db,
        provider="anthropic",
        model=metadata.get("model") or settings.ai_model,
        feature=feature,
        tokens_input=metadata.get("tokens_input"),
        tokens_output=metadata.get("tokens_output"),
        latency_ms=metadata.get("latency_ms"),
        user_id=user_id,
    )


# Fallback templates for when AI fails
FALLBACK_EMPATHY = "Tiene sentido. Gracias por contarlo. Vamos a convertir eso en claridad, paso a paso."

FALLBACK_SYNTHESIS = {
    "text": "Veo a alguien que está explorando opciones con curiosidad. Es un buen momento para descubrir qué caminos pueden funcionar para ti. ¿Te refleja esto?",
    "chips": [
        {"label": "Etapa", "value": "Explorando"},
        {"label": "Horizonte", "value": "Flexible"},
        {"label": "Interés principal", "value": "Crecimiento"},
        {"label": "Consideración clave", "value": "En descubrimiento"},
    ],
    "key_motivations": ["Exploración", "Crecimiento"],
    "constraints": [],
}

FALLBACK_ROUTES = [
    {
        "key": "LANGUAGE_PLUS_EXPERIENCE",
        "name": "Ruta Idioma + Experiencia",
        "why": "Perfecta si quieres mejorar un idioma mientras vives algo nuevo, sin comprometerte a algo demasiado largo.",
        "what_it_looks_like": "Curso intensivo + actividades culturales + objetivos semanales claros.",
        "next_step": "Definir duración ideal y ritmo (intensivo vs flexible).",
    },
    {
        "key": "PRACTICAL_SKILLS_SHORT",
        "name": "Ruta Habilidades Prácticas (corto)",
        "why": "Si te motiva aprender haciendo, esta ruta te da enfoque práctico y resultados rápidos.",
        "what_it_looks_like": "Programa corto orientado a proyectos + portafolio + feedback.",
        "next_step": "Elegir area (negocios, tech, diseno, etc.) y preferencia de modalidad.",
    },
    {
        "key": "DEGREE_PATHWAY",
        "name": "Ruta Pregrado (con camino claro)",
        "why": "Si estas pensando en construir una carrera afuera, esta ruta ordena requisitos, idioma y tiempos.",
        "what_it_looks_like": "Exploración de programas + requisitos + plan de preparación por etapas.",
        "next_step": "Aterrizar país vs programa y requisitos de idioma.",
    },
]


def derive_motivations(answers: Dict[str, Any]) -> List[str]:
    """Derive motivations from answers (fallback logic)."""
    motivations = []

    interest_type = answers.get("interestType", []) or []
    if "Mejorar un idioma" in interest_type:
        motivations.append("Crecimiento lingüístico")
    if "Vivir en otro país" in interest_type:
        motivations.append("Experiencia internacional")
    if "Aprender algo práctico" in interest_type:
        motivations.append("Habilidades prácticas")
    if "Construir una carrera" in interest_type:
        motivations.append("Desarrollo profesional")

    weekly = answers.get("weeklyActivities", "")
    if weekly == "Proyectos prácticos":
        motivations.append("Aprendizaje aplicado")
    if weekly == "Actividades culturales":
        motivations.append("Inmersión cultural")

    return motivations if motivations else ["Exploración"]


def derive_constraints(answers: Dict[str, Any]) -> List[str]:
    """Derive constraints from answers (fallback logic)."""
    constraints = []

    if answers.get("budgetBand") == "Bajo":
        constraints.append("Presupuesto limitado")
    if answers.get("timeHorizon") == "En los próximos meses":
        constraints.append("Tiempo corto")

    language = answers.get("languageLevel", "")
    if language in ["Básico", "Quiero aprender desde cero"]:
        constraints.append("Necesita preparación de idioma")

    dont_want = (answers.get("dontWant") or "").lower()
    if "largo" in dont_want:
        constraints.append("Prefiere corta duración")
    if "teórico" in dont_want or "teorico" in dont_want:
        constraints.append("Prefiere práctico sobre teórico")

    return constraints


def generate_empathy_reflection(
    why_here: str,
    session_id: str,
    db: Optional[DBSession] = None,
    user_id: Optional[UUID] = None,
) -> EmpathyReflectionOutput:
    """
    Generate empathy reflection after 'whyHere' step.

    Args:
        why_here: User's response to "What brought you here?"
        session_id: Session ID for logging
        db: DB session para tracking M-001 (opcional)
        user_id: dueño del journey para tracking M-001 (None si anónimo)

    Returns:
        EmpathyReflectionOutput with text and detected emotion
    """
    try:
        prompt_template = load_prompt("reflection")
        prompt = prompt_template.format(user_input=why_here)

        response, meta = call_claude_with_meta(
            prompt,
            session_id=session_id,
            feature="journey_reflection",
            prompt_version="reflection_v1",
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )

        if response:
            _track_journey_usage(db, user_id, meta, "journey_reflection")
            return EmpathyReflectionOutput(
                text=response.strip(),
                detected_emotion=None,  # Could parse from response if needed
            )
    except Exception as e:
        logger.error(f"Failed to generate empathy reflection: {e}")

    # Fallback with simple keyword detection
    lowercased = why_here.lower()
    if any(word in lowercased for word in ["no se", "confundido", "perdido"]):
        fallback_text = "Entiendo que puede sentirse abrumador tener tantas opciones. Vamos paso a paso, sin presión. Lo importante es que estás aquí explorando."
    elif any(word in lowercased for word in ["mejorar", "crecer", "aprender"]):
        fallback_text = "Esa mentalidad de crecimiento es valiosa. Vamos a encontrar opciones que te permitan avanzar a tu ritmo."
    elif any(word in lowercased for word in ["trabajo", "carrera", "profesional"]):
        fallback_text = "Pensar en tu futuro profesional es importante. Hay muchas formas de construir ese camino, exploremos juntos."
    else:
        fallback_text = FALLBACK_EMPATHY

    return EmpathyReflectionOutput(text=fallback_text, detected_emotion=None)


def generate_partial_summary(
    answers: Dict[str, Any],
    session_id: str,
) -> PartialSummaryOutput:
    """
    Generate partial summary after interests section.

    Args:
        answers: User's answers so far
        session_id: Session ID for logging

    Returns:
        PartialSummaryOutput with bullets and motivation
    """
    # This is simpler and doesn't need AI - use deterministic logic
    bullets = []
    motivations = derive_motivations(answers)

    interest_type = answers.get("interestType", []) or []
    if interest_type:
        bullets.append(f"Te atrae: {' y '.join(interest_type).lower()}")

    weekly = answers.get("weeklyActivities")
    if weekly:
        bullets.append(f"Prefieres semanas con: {weekly.lower()}")

    dont_want = answers.get("dontWant")
    if dont_want:
        bullets.append(f"Quieres evitar: {dont_want.lower()}")

    if not bullets:
        bullets = ["Aún estamos conociéndote mejor"]

    return PartialSummaryOutput(
        bullets=bullets,
        motivation=motivations[0] if motivations else "Exploración",
    )


def generate_synthesis(
    answers: Dict[str, Any],
    session_id: str,
    db: Optional[DBSession] = None,
    user_id: Optional[UUID] = None,
) -> SynthesisOutput:
    """
    Generate full synthesis reflection.

    Args:
        answers: User's complete answers
        session_id: Session ID for logging
        db: DB session para tracking M-001 (opcional)
        user_id: dueño del journey para tracking M-001 (None si anónimo)

    Returns:
        SynthesisOutput with text, chips, motivations, and constraints
    """
    try:
        prompt_template = load_prompt("synthesis")

        interest_type = answers.get("interestType", []) or []
        prompt = prompt_template.format(
            life_stage=answers.get("lifeStage", "No especificado"),
            time_horizon=answers.get("timeHorizon", "No especificado"),
            clarity_level=answers.get("clarityLevel", "No especificado"),
            interest_type=", ".join(interest_type) if interest_type else "No especificado",
            weekly_activities=answers.get("weeklyActivities", "No especificado"),
            dont_want=answers.get("dontWant", "No especificado"),
            budget_band=answers.get("budgetBand", "No especificado"),
            language_level=answers.get("languageLevel", "No especificado"),
            geo_preference=answers.get("geoPreference", "No especificado"),
        )

        response, meta = call_claude_with_meta(
            prompt,
            session_id=session_id,
            feature="journey_synthesis",
            prompt_version="synthesis_v1",
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )

        if response:
            _track_journey_usage(db, user_id, meta, "journey_synthesis")
            try:
                data = parse_ai_json(response)
                return SynthesisOutput(
                    text=data["text"],
                    chips=[SynthesisChip(**chip) for chip in data["chips"]],
                    key_motivations=data["key_motivations"],
                    constraints=data["constraints"],
                )
            except (ValueError, KeyError) as e:
                logger.warning(f"Failed to parse synthesis response: {e}")

    except Exception as e:
        logger.error(f"Failed to generate synthesis: {e}")

    # Fallback
    motivations = derive_motivations(answers)
    constraints = derive_constraints(answers)

    stage_label = {
        "Terminando el colegio": "preparándose para el siguiente paso",
        "En la universidad": "explorando oportunidades",
        "Ya trabajando": "buscando un cambio",
        "En transición / no seguro": "en proceso de descubrimiento",
    }.get(answers.get("lifeStage", ""), "explorando")

    text = f"Veo a alguien que está {stage_label}"
    if motivations:
        text += f", motivado principalmente por {motivations[0].lower()}"
    if constraints:
        text += f". Es importante considerar: {', '.join(constraints).lower()}"
    text += ". ¿Te refleja esto?"

    return SynthesisOutput(
        text=text,
        chips=[
            SynthesisChip(label="Etapa", value=answers.get("lifeStage", "No definida")),
            SynthesisChip(label="Horizonte", value=answers.get("timeHorizon", "Flexible")),
            SynthesisChip(label="Interés principal", value=motivations[0] if motivations else "Explorando"),
            SynthesisChip(label="Consideración clave", value=constraints[0] if constraints else "Ninguna especial"),
        ],
        key_motivations=motivations,
        constraints=constraints,
    )


def generate_routes(
    answers: Dict[str, Any],
    session_id: str,
    db: Optional[DBSession] = None,
    user_id: Optional[UUID] = None,
) -> RouteSuggestionOutput:
    """
    Generate route suggestions.

    Args:
        answers: User's complete answers
        session_id: Session ID for logging
        db: DB session para tracking M-001 (opcional)
        user_id: dueño del journey para tracking M-001 (None si anónimo)

    Returns:
        RouteSuggestionOutput with max 3 routes
    """
    try:
        prompt_template = load_prompt("routes")

        motivations = derive_motivations(answers)
        constraints = derive_constraints(answers)

        interest_type = answers.get("interestType", []) or []
        prompt = prompt_template.format(
            life_stage=answers.get("lifeStage", "No especificado"),
            time_horizon=answers.get("timeHorizon", "No especificado"),
            clarity_level=answers.get("clarityLevel", "No especificado"),
            interest_type=", ".join(interest_type) if interest_type else "No especificado",
            weekly_activities=answers.get("weeklyActivities", "No especificado"),
            dont_want=answers.get("dontWant", "No especificado"),
            budget_band=answers.get("budgetBand", "No especificado"),
            language_level=answers.get("languageLevel", "No especificado"),
            geo_preference=answers.get("geoPreference", "No especificado"),
            motivations=", ".join(motivations),
            constraints=", ".join(constraints) if constraints else "Ninguna especial",
        )

        response, meta = call_claude_with_meta(
            prompt,
            session_id=session_id,
            feature="journey_routes",
            prompt_version="routes_v1",
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )

        if response:
            _track_journey_usage(db, user_id, meta, "journey_routes")
            try:
                data = parse_ai_json(response)
                routes = [GeneratedRoute(**route) for route in data["routes"][:3]]
                return RouteSuggestionOutput(routes=routes)
            except (ValueError, KeyError) as e:
                logger.warning(f"Failed to parse routes response: {e}")

    except Exception as e:
        logger.error(f"Failed to generate routes: {e}")

    # Fallback to static routes
    return RouteSuggestionOutput(
        routes=[GeneratedRoute(**route) for route in FALLBACK_ROUTES]
    )


def generate_advisor_brief(
    answers: Dict[str, Any],
    routes: List[Dict[str, Any]],
    session_id: str,
    db: Optional[DBSession] = None,
    user_id: Optional[UUID] = None,
) -> AdvisorBriefOutput:
    """
    Generate advisor brief for contact form.

    Args:
        answers: User's complete answers
        routes: User's selected routes
        session_id: Session ID for logging
        db: DB session para tracking M-001 (opcional)
        user_id: dueño del journey para tracking M-001 (None si anónimo)

    Returns:
        AdvisorBriefOutput with summary and considerations
    """
    try:
        prompt_template = load_prompt("advisor_brief")

        motivations = derive_motivations(answers)
        constraints = derive_constraints(answers)

        primary_route = next((r for r in routes if r.get("is_primary")), None)
        other_routes = [r for r in routes if not r.get("is_primary")]

        interest_type = answers.get("interestType", []) or []
        prompt = prompt_template.format(
            life_stage=answers.get("lifeStage", "No especificado"),
            time_horizon=answers.get("timeHorizon", "No especificado"),
            clarity_level=answers.get("clarityLevel", "No especificado"),
            interest_type=", ".join(interest_type) if interest_type else "No especificado",
            weekly_activities=answers.get("weeklyActivities", "No especificado"),
            dont_want=answers.get("dontWant", "No especificado"),
            budget_band=answers.get("budgetBand", "No especificado"),
            language_level=answers.get("languageLevel", "No especificado"),
            geo_preference=answers.get("geoPreference", "No especificado"),
            motivations=", ".join(motivations),
            constraints=", ".join(constraints) if constraints else "Ninguna especial",
            primary_route=primary_route.get("name", "No seleccionada") if primary_route else "No seleccionada",
            other_routes=", ".join(r.get("name", "") for r in other_routes) if other_routes else "Ninguna",
        )

        response, meta = call_claude_with_meta(
            prompt,
            session_id=session_id,
            feature="journey_advisor_brief",
            prompt_version="advisor_brief_v1",
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )

        if response:
            _track_journey_usage(db, user_id, meta, "journey_advisor_brief")
            try:
                data = parse_ai_json(response)
                return AdvisorBriefOutput(
                    profile_summary=data["profile_summary"],
                    primary_route=data.get("primary_route"),
                    key_considerations=data["key_considerations"],
                    emotional_state=data.get("emotional_state"),
                )
            except (ValueError, KeyError) as e:
                logger.warning(f"Failed to parse advisor brief response: {e}")

    except Exception as e:
        logger.error(f"Failed to generate advisor brief: {e}")

    # Fallback
    motivations = derive_motivations(answers)
    constraints = derive_constraints(answers)
    clarity = {
        "Tengo algo claro y quiero validarlo": "Alto",
        "Tengo ideas sueltas": "Medio",
    }.get(answers.get("clarityLevel", ""), "Bajo")

    primary_route_obj = next((r for r in routes if r.get("is_primary")), None)

    considerations = []
    considerations.append(f"Etapa: {answers.get('lifeStage', 'No especificada')}")
    considerations.append(f"Horizonte temporal: {answers.get('timeHorizon', 'No especificado')}")
    if motivations:
        considerations.append(f"Motivación principal: {motivations[0]}")

    return AdvisorBriefOutput(
        profile_summary=f"Estudiante en etapa '{answers.get('lifeStage', 'no definida')}' con horizonte '{answers.get('timeHorizon', 'flexible')}' y nivel de claridad {clarity.lower()}.",
        primary_route=primary_route_obj.get("name") if primary_route_obj else None,
        key_considerations=considerations,
        emotional_state=f"Claridad {clarity.lower()}",
    )
