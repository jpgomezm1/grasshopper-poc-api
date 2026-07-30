"""Journey state machine matching frontend's JOURNEY_STEPS."""

from typing import Callable, Optional, List, Dict, Any
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

    # P1-5 · Condición de aplicabilidad. Recibe el onboarding del dueño de la sesión
    # y devuelve True cuando el paso NO tiene sentido para esta persona.
    #
    # Hasta ahora la única razón para saltar un paso era "ya lo respondió"
    # (`save_to` con valor). Faltaba la otra: "no aplica". Por eso a quien decía
    # que quiere estudiar en su país se le seguía preguntando "cuando piensas en
    # irte, ¿qué pesa más?" — reproducido y capturado en el QA del 28-07.
    #
    # Se resuelve con una condición REAL y no sembrando una respuesta inventada:
    # registrar que alguien contestó algo que nunca contestó es justo el tipo de
    # dato falso que este sprint viene quitando.
    skip_if: Optional[Callable[[Dict[str, Any]], bool]] = None


# Journey steps configuration - mirrors frontend's JOURNEY_STEPS exactly
JOURNEY_STEPS: List[JourneyStep] = [
    JourneyStep(
        id="welcome",
        stage=JourneyStage.LANDING,
        view_type=ViewType.WELCOME,
        title="Antes de pensar en países o programas...",
        text="Quiero entenderte un poco. No tienes que decidir nada hoy.",
        next_step="whyHere",
    ),
    JourneyStep(
        id="whyHere",
        stage=JourneyStage.CONTEXT,
        view_type=ViewType.OPEN_TEXT,
        question="¿Qué te hizo llegar hasta aquí hoy?",
        placeholder="Cuéntame en 1-2 frases...",
        save_to="whyHere",
        next_step="empathy",
        # P1-4 / S9 · Esta pregunta es la PRIMERA del journey, justo después de que
        # la persona respondió 10-13 preguntas de onboarding. Y el onboarding ya le
        # preguntó lo mismo con otras palabras: "¿Qué quieres resolver con esta
        # orientación?" (`main_goal`).
        #
        # Es la queja que más repitieron las dos personas que probaron:
        #   Sandra  · "siento que me está volviendo a preguntar"
        #   Verónica· "me hizo 13 preguntas y me va a volver a decir que comencemos"
        #
        # No se siembra una respuesta —`whyHere` es texto libre y `main_goal` son
        # opciones, inventar la frase sería falsear lo que dijo—; simplemente no se
        # vuelve a preguntar.
        skip_if=lambda ctx: bool((ctx.get("onboarding") or {}).get("main_goal")),
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
        question="Hoy te encuentras más cerca de...",
        options=[
            "Terminando el colegio",
            "En la universidad",
            "Ya trabajando",
            "En transición / no seguro",
        ],
        save_to="lifeStage",
        next_step="timeHorizon",
    ),
    JourneyStep(
        id="timeHorizon",
        stage=JourneyStage.CONTEXT,
        view_type=ViewType.SINGLE_CHOICE,
        question="Si esto saliera bien, ¿cuándo te gustaría que pasara?",
        options=[
            "En los próximos meses",
            "En 1 año",
            "Más adelante (solo explorando)",
        ],
        save_to="timeHorizon",
        next_step="clarityLevel",
    ),
    JourneyStep(
        id="clarityLevel",
        stage=JourneyStage.CONTEXT,
        view_type=ViewType.SINGLE_CHOICE,
        question="Hoy te sientes más cerca de...",
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
        question="¿Qué tipo de experiencia te atrae más ahora mismo?",
        helper="Elige hasta 2",
        max_select=2,
        options=[
            "Aprender algo práctico",
            "Mejorar un idioma",
            "Vivir en otro país",
            "Construir una carrera",
            "No estoy seguro aún",
        ],
        save_to="interestType",
        next_step="weeklyActivities",
    ),
    JourneyStep(
        id="weeklyActivities",
        stage=JourneyStage.INTERESTS,
        view_type=ViewType.SINGLE_CHOICE,
        question="Si piensas en una semana ideal, ¿qué preferirías estar haciendo?",
        options=[
            "Proyectos prácticos",
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
        question="¿Qué sabes que NO quieres ahora?",
        placeholder="Ej: nada muy largo, o no quiero algo muy teórico...",
        save_to="dontWant",
        next_step="declaredAspirations",
    ),
    # GH-LOCAL-QA-RONDA2 · B-017 · 2026-05-21 · pregunta nueva para capturar
    # aspiraciones declaradas (antes el dossier mostraba aspirations.declared=[]
    # porque el journey no las recolectaba explícitamente).
    JourneyStep(
        id="declaredAspirations",
        stage=JourneyStage.INTERESTS,
        view_type=ViewType.OPEN_TEXT,
        question="Si pudieras imaginar tu carrera ideal en 5 años, ¿qué te ves haciendo?",
        placeholder="Déjate llevar — no tiene que ser realista ni definitivo...",
        save_to="declaredAspirations",
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
        question="Para cuidarte mejor, ¿cuál de estos rangos se siente más realista?",
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
        question="¿Cómo te sientes hoy con el idioma?",
        options=[
            "Básico",
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
        question="Cuando piensas en irte, ¿qué pesa más?",
        options=[
            "El país",
            "El programa",
            "La experiencia",
            "Aún no lo sé",
        ],
        save_to="geoPreference",
        next_step="synthesis",
        # P1-5 · La pregunta presupone que la persona se va a ir. A quien respondió
        # "En mi país" en el onboarding no se le hace: se le estaba preguntando
        # "cuando piensas en irte" cinco minutos después de decir que se queda.
        skip_if=lambda ctx: (ctx.get("onboarding") or {}).get("international_interest")
        == "intl_no",
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


def get_next_step(
    current_step_id: str,
    answers: Optional[Dict[str, Any]] = None,
    onboarding: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Get the next step ID.

    Se salta un paso por DOS razones distintas:

    1. **Ya está respondido** — su `save_to` tiene valor en `answers`. Es el caso
       de `lifeStage`/`timeHorizon` sembrados desde el onboarding (B-02): no
       volvemos a preguntar lo mismo.
    2. **No aplica a esta persona** — su `skip_if` da True con el `onboarding` del
       dueño de la sesión. P1-5: hasta ahora esta razón no existía, y por eso a
       quien decía que quiere estudiar en su país se le seguía preguntando "cuando
       piensas en irte, ¿qué pesa más?".

    Sin `answers` ni `onboarding`, comportamiento original (un solo salto).
    """
    step = get_step(current_step_id)
    if not step:
        return None
    next_id = step.next_step
    if not answers and not onboarding:
        return next_id

    answers = answers or {}
    ctx = {"answers": answers, "onboarding": onboarding or {}}

    while next_id:
        nxt = get_step(next_id)
        if not nxt:
            break
        ya_respondido = bool(nxt.save_to and answers.get(nxt.save_to))
        no_aplica = False
        if nxt.skip_if is not None:
            try:
                no_aplica = bool(nxt.skip_if(ctx))
            except Exception:
                # Una condición mal escrita no puede dejar al usuario atascado:
                # ante la duda, se muestra el paso.
                no_aplica = False
        if ya_respondido or no_aplica:
            next_id = nxt.next_step
        else:
            break
    return next_id


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

    # Auditoría R5 · el paso de rutas SOLO se completa vía evento 'selection'
    # con un route_key válido — un 'answer' vacío lo saltaba y completaba el
    # journey sin ruta elegida.
    if step.view_type == ViewType.ROUTES_PICKER:
        return False

    # Reflections and other types don't need validation
    return True
