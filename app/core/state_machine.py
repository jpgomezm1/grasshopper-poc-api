"""Journey state machine matching frontend's JOURNEY_STEPS."""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum


class JourneyStage(str, Enum):
    """Journey stages."""
    LANDING = "LANDING"
    CONTEXT = "CONTEXT"
    INTERESTS = "INTERESTS"
    CONSTRAINTS = "CONSTRAINTS"
    SYNTHESIS = "SYNTHESIS"
    ROUTES = "ROUTES"
    DONE = "DONE"


class ViewType(str, Enum):
    """View types for journey steps."""
    WELCOME = "WELCOME"
    OPEN_TEXT = "OPEN_TEXT"
    SINGLE_CHOICE = "SINGLE_CHOICE"
    MULTI_CHOICE = "MULTI_CHOICE"
    REFLECTION = "REFLECTION"
    PARTIAL_SUMMARY = "PARTIAL_SUMMARY"
    ROUTES_PICKER = "ROUTES_PICKER"
    NEXT_STEP = "NEXT_STEP"


@dataclass
class JourneyStep:
    """Definition of a journey step."""
    id: str
    stage: JourneyStage
    view_type: ViewType
    title: Optional[str] = None
    question: Optional[str] = None
    text: Optional[str] = None
    placeholder: Optional[str] = None
    options: Optional[List[str]] = None
    max_select: Optional[int] = None
    helper: Optional[str] = None
    save_to: Optional[str] = None
    next_step: Optional[str] = None


# Journey steps configuration - mirrors frontend's JOURNEY_STEPS exactly
JOURNEY_STEPS: List[JourneyStep] = [
    JourneyStep(
        id="welcome",
        stage=JourneyStage.LANDING,
        view_type=ViewType.WELCOME,
        title="Antes de pensar en paises o programas...",
        text="Quiero entenderte un poco. No tienes que decidir nada hoy.",
        next_step="whyHere",
    ),
    JourneyStep(
        id="whyHere",
        stage=JourneyStage.CONTEXT,
        view_type=ViewType.OPEN_TEXT,
        question="Que te hizo llegar hasta aqui hoy?",
        placeholder="Cuentame en 1-2 frases...",
        save_to="whyHere",
        next_step="empathy",
    ),
    JourneyStep(
        id="empathy",
        stage=JourneyStage.CONTEXT,
        view_type=ViewType.REFLECTION,
        next_step="lifeStage",
    ),
    JourneyStep(
        id="lifeStage",
        stage=JourneyStage.CONTEXT,
        view_type=ViewType.SINGLE_CHOICE,
        question="Hoy te encuentras mas cerca de...",
        options=[
            "Terminando el colegio",
            "En la universidad",
            "Ya trabajando",
            "En transicion / no seguro",
        ],
        save_to="lifeStage",
        next_step="timeHorizon",
    ),
    JourneyStep(
        id="timeHorizon",
        stage=JourneyStage.CONTEXT,
        view_type=ViewType.SINGLE_CHOICE,
        question="Si esto saliera bien, cuando te gustaria que pasara?",
        options=[
            "En los proximos meses",
            "En 1 ano",
            "Mas adelante (solo explorando)",
        ],
        save_to="timeHorizon",
        next_step="clarityLevel",
    ),
    JourneyStep(
        id="clarityLevel",
        stage=JourneyStage.CONTEXT,
        view_type=ViewType.SINGLE_CHOICE,
        question="Hoy te sientes mas cerca de...",
        options=[
            "Tengo muchas dudas",
            "Tengo ideas sueltas",
            "Tengo algo claro y quiero validarlo",
        ],
        save_to="clarityLevel",
        next_step="interestType",
    ),
    JourneyStep(
        id="interestType",
        stage=JourneyStage.INTERESTS,
        view_type=ViewType.MULTI_CHOICE,
        question="Que tipo de experiencia te atrae mas ahora mismo?",
        helper="Elige hasta 2",
        max_select=2,
        options=[
            "Aprender algo practico",
            "Mejorar un idioma",
            "Vivir en otro pais",
            "Construir una carrera",
            "No estoy seguro aun",
        ],
        save_to="interestType",
        next_step="weeklyActivities",
    ),
    JourneyStep(
        id="weeklyActivities",
        stage=JourneyStage.INTERESTS,
        view_type=ViewType.SINGLE_CHOICE,
        question="Si piensas en una semana ideal, que preferirias estar haciendo?",
        options=[
            "Proyectos practicos",
            "Clases estructuradas",
            "Trabajo + estudio",
            "Actividades culturales",
            "Algo flexible",
        ],
        save_to="weeklyActivities",
        next_step="dontWant",
    ),
    JourneyStep(
        id="dontWant",
        stage=JourneyStage.INTERESTS,
        view_type=ViewType.OPEN_TEXT,
        question="Que sabes que NO quieres ahora?",
        placeholder="Ej: nada muy largo, o no quiero algo muy teorico...",
        save_to="dontWant",
        next_step="partialSummary1",
    ),
    JourneyStep(
        id="partialSummary1",
        stage=JourneyStage.INTERESTS,
        view_type=ViewType.PARTIAL_SUMMARY,
        next_step="budgetBand",
    ),
    JourneyStep(
        id="budgetBand",
        stage=JourneyStage.CONSTRAINTS,
        view_type=ViewType.SINGLE_CHOICE,
        question="Para cuidarte mejor, cual de estos rangos se siente mas realista?",
        options=[
            "Bajo",
            "Medio",
            "Flexible",
            "Prefiero no definirlo ahora",
        ],
        save_to="budgetBand",
        next_step="languageLevel",
    ),
    JourneyStep(
        id="languageLevel",
        stage=JourneyStage.CONSTRAINTS,
        view_type=ViewType.SINGLE_CHOICE,
        question="Como te sientes hoy con el idioma?",
        options=[
            "Basico",
            "Intermedio",
            "Avanzado",
            "Quiero aprender desde cero",
        ],
        save_to="languageLevel",
        next_step="geoPreference",
    ),
    JourneyStep(
        id="geoPreference",
        stage=JourneyStage.CONSTRAINTS,
        view_type=ViewType.SINGLE_CHOICE,
        question="Cuando piensas en irte, que pesa mas?",
        options=[
            "El pais",
            "El programa",
            "La experiencia",
            "Aun no lo se",
        ],
        save_to="geoPreference",
        next_step="synthesis",
    ),
    JourneyStep(
        id="synthesis",
        stage=JourneyStage.SYNTHESIS,
        view_type=ViewType.REFLECTION,
        title="Te reflejo lo que estoy entendiendo",
        next_step="routes",
    ),
    JourneyStep(
        id="routes",
        stage=JourneyStage.ROUTES,
        view_type=ViewType.ROUTES_PICKER,
        title="3 rutas que te quedan bien (hoy)",
        next_step="nextStep",
    ),
    JourneyStep(
        id="nextStep",
        stage=JourneyStage.DONE,
        view_type=ViewType.NEXT_STEP,
        title="Tu siguiente paso",
    ),
]

# Create lookup dictionaries
STEPS_BY_ID: Dict[str, JourneyStep] = {step.id: step for step in JOURNEY_STEPS}
STAGES: List[str] = ["LANDING", "CONTEXT", "INTERESTS", "CONSTRAINTS", "SYNTHESIS", "ROUTES", "DONE"]


def get_step(step_id: str) -> Optional[JourneyStep]:
    """Get step by ID."""
    return STEPS_BY_ID.get(step_id)


def get_next_step(current_step_id: str) -> Optional[str]:
    """Get the next step ID."""
    step = get_step(current_step_id)
    return step.next_step if step else None


def get_step_index(step_id: str) -> int:
    """Get the index of a step."""
    for i, step in enumerate(JOURNEY_STEPS):
        if step.id == step_id:
            return i
    return 0


def get_stage_index(stage: str) -> int:
    """Get the index of a stage."""
    try:
        return STAGES.index(stage)
    except ValueError:
        return 0


def calculate_progress(step_id: str) -> Dict[str, Any]:
    """Calculate progress for a step."""
    step = get_step(step_id)
    step_index = get_step_index(step_id)
    total_steps = len(JOURNEY_STEPS)
    percentage = int(((step_index + 1) / total_steps) * 100)

    return {
        "stage": step.stage.value if step else "LANDING",
        "percentage": percentage,
    }


def get_actions_for_step(step_id: str) -> List[str]:
    """Get available actions for a step."""
    step = get_step(step_id)
    if not step:
        return ["continue"]

    actions = []

    # Most steps have continue
    if step.next_step:
        actions.append("continue")

    # Can go back if not at the beginning
    step_index = get_step_index(step_id)
    if step_index > 0:
        actions.append("back")

    return actions


def validate_answer(step_id: str, payload: Dict[str, Any]) -> bool:
    """Validate an answer for a step."""
    step = get_step(step_id)
    if not step:
        return False

    if step.view_type == ViewType.OPEN_TEXT:
        value = payload.get("value", "")
        return isinstance(value, str) and len(value.strip()) > 0

    if step.view_type == ViewType.SINGLE_CHOICE:
        value = payload.get("value")
        return value in (step.options or [])

    if step.view_type == ViewType.MULTI_CHOICE:
        values = payload.get("value", [])
        if not isinstance(values, list):
            return False
        max_select = step.max_select or len(step.options or [])
        return len(values) > 0 and len(values) <= max_select and all(v in (step.options or []) for v in values)

    # Reflections and other types don't need validation
    return True
