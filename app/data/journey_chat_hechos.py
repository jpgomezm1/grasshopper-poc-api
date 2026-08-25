"""Catálogo de hechos del "chat continuo" del Journey.

JP, reunión 24-08 (10:48 y 18:25):

    "esto del journey a mi todavia no me convence"
    "en Journey yo lo que me imagino es que sea como un chat continuo que le
     vaya haciendo preguntas al usuario para irlo perfilando"

## De dónde sale este archivo

El tramo CONTEXT/INTERESTS/CONSTRAINTS de `app.core.state_machine.JOURNEY_STEPS`
(`lifeStage` → `geoPreference`) es hoy un wizard: una pantalla, un botón, la
siguiente. Este módulo es la MISMA lista de datos, expresada como hechos que
una conversación recoge en el orden que tenga sentido — el mismo cambio de
forma que `app.data.onboarding_hechos` ya le hizo al formulario de registro.

## Por qué las opciones NO se copian a mano

`_opciones_del_paso` lee las opciones REALES del paso homónimo en
`state_machine.JOURNEY_STEPS` en tiempo de import. Si alguien cambia la copy
de un botón allá (es copy de la clienta, cambia), este catálogo la sigue sin
que nadie tenga que acordarse de venir a actualizar este archivo — el mismo
mecanismo que ya usa `journey_interprete._esquema` para su único paso
habilitado.

## Por qué `aplica()` reusa `skip_if` de `state_machine`

`geoPreference` no se le pregunta a quien ya dijo en el onboarding que se
queda en Colombia; `languageLevel` no se le pregunta a quien ya tiene un
examen de inglés medido. Esas dos reglas YA existen, escritas una sola vez,
en `JOURNEY_STEPS[...].skip_if`. Reimplementarlas aquí crearía una segunda
fuente de verdad que un día diverge — el error que este repo ya cometió
cuatro veces (ver CLAUDE.md) — así que `aplica()` llama directo a esa función.

## Qué NO está aquí

`whyHere` (redundante con `main_goal` del onboarding) y los pasos de
pantalla (`empathy`, `partialSummary1`, `testInvitation`, `synthesis`,
`routes`, `nextStep`) no son hechos que recoger: son reacciones o pasos con
IA propia. El chat continuo cubre el tramo de preguntas y al terminar
entrega la sesión al motor de síntesis/rutas de siempre — ver
`app.services.journey_chat_service` y `app.api.v1.journey_chat`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.state_machine import get_step
from app.data.perfilador_typeform import Hecho


def _opciones_del_paso(step_id: str) -> Dict[str, str]:
    """código == etiqueta: el Journey no tiene un vocabulario de códigos aparte
    del texto que ve la persona · mismo truco que `journey_interprete._esquema`."""
    step = get_step(step_id)
    opciones = (step.options if step else None) or []
    return {o: o for o in opciones}


# Qué hay que averiguar · NO cómo preguntarlo (mismo criterio que
# `onboarding_hechos.QUE_AVERIGUAR`: pasarle al modelo el texto literal del
# botón hace que la conversación suene siempre igual).
QUE_AVERIGUAR: Dict[str, str] = {
    "lifeStage": "en qué momento está hoy · terminando el colegio, en la "
                 "universidad, ya trabajando, o en transición",
    "timeHorizon": "para cuándo le gustaría que esto avanzara, si le fuera bien",
    "clarityLevel": "qué tan claro tiene su rumbo hoy · dudas, ideas sueltas, "
                     "o algo que ya quiere validar",
    "interestType": "qué tipo de experiencia le atrae más ahora mismo · puede "
                     "mencionar hasta dos",
    "weeklyActivities": "cómo se imagina una semana ideal, en lo que haría",
    "dontWant": "algo que sepa que NO quiere ahora, si lo tiene claro",
    "declaredAspirations": "cómo se imagina en 5 años, sin que tenga que ser realista",
    "budgetBand": "qué rango de presupuesto se siente realista para su situación",
    "languageLevel": "cómo se siente hoy con el idioma",
    "geoPreference": "si piensa en moverse, qué pesa más para él: el país, el "
                      "programa, o la experiencia en sí",
}

HECHOS: List[Hecho] = [
    Hecho(
        id="lifeStage",
        pregunta_typeform="Hoy te encuentras más cerca de...",
        bloque="contexto",
        tipo="opcion",
        opciones=_opciones_del_paso("lifeStage"),
        obligatorio=True,
    ),
    Hecho(
        id="timeHorizon",
        pregunta_typeform="Si esto saliera bien, ¿cuándo te gustaría que pasara?",
        bloque="contexto",
        tipo="opcion",
        opciones=_opciones_del_paso("timeHorizon"),
        obligatorio=True,
    ),
    Hecho(
        id="clarityLevel",
        pregunta_typeform="Hoy te sientes más cerca de...",
        bloque="contexto",
        tipo="opcion",
        opciones=_opciones_del_paso("clarityLevel"),
        obligatorio=True,
        nota="Decide si se ofrece un video (Verónica, 24-08): con 'Tengo algo "
             "claro y quiero validarlo' se saltan · ver app.data.journey_videos.",
    ),
    Hecho(
        id="interestType",
        pregunta_typeform="¿Qué tipo de experiencia te atrae más ahora mismo?",
        bloque="intereses",
        tipo="multi",
        opciones=_opciones_del_paso("interestType"),
        obligatorio=True,
        nota="Tope de 2 · el catálogo no lo expresa (fact_extractor no admite "
             "límites por hecho), se recorta después de extraer en "
             "journey_chat_service para no tocar un módulo compartido.",
    ),
    Hecho(
        id="weeklyActivities",
        pregunta_typeform="Si piensas en una semana ideal, ¿qué preferirías estar haciendo?",
        bloque="intereses",
        tipo="opcion",
        opciones=_opciones_del_paso("weeklyActivities"),
        obligatorio=True,
    ),
    Hecho(
        id="dontWant",
        pregunta_typeform="¿Qué sabes que NO quieres ahora?",
        bloque="intereses",
        tipo="texto",
        obligatorio=False,
        nota="Degrada con gracia aguas abajo (ai_service usa 'No especificado' "
             "si falta) · no vale la pena insistir si no sale solo.",
    ),
    Hecho(
        id="declaredAspirations",
        pregunta_typeform="Si pudieras imaginar tu carrera ideal en 5 años, ¿qué te ves haciendo?",
        bloque="intereses",
        tipo="texto",
        obligatorio=False,
    ),
    Hecho(
        id="budgetBand",
        pregunta_typeform="Para cuidarte mejor, ¿cuál de estos rangos se siente más realista?",
        bloque="restricciones",
        tipo="opcion",
        opciones=_opciones_del_paso("budgetBand"),
        obligatorio=True,
    ),
    Hecho(
        id="languageLevel",
        pregunta_typeform="¿Cómo te sientes hoy con el idioma?",
        bloque="restricciones",
        tipo="opcion",
        opciones=_opciones_del_paso("languageLevel"),
        obligatorio=True,
        nota="`aplica()` lo salta si ya hay un examen de inglés medido · misma "
             "regla que `state_machine.JOURNEY_STEPS['languageLevel'].skip_if`.",
    ),
    Hecho(
        id="geoPreference",
        pregunta_typeform="Cuando piensas en irte, ¿qué pesa más?",
        bloque="restricciones",
        tipo="opcion",
        opciones=_opciones_del_paso("geoPreference"),
        obligatorio=True,
        nota="`aplica()` lo salta a quien ya dijo en el onboarding que se "
             "queda en su país · misma regla que `state_machine`.",
    ),
]

_POR_ID: Dict[str, Hecho] = {h.id: h for h in HECHOS}
OBLIGATORIOS: tuple = tuple(h.id for h in HECHOS if h.obligatorio)

# El orden en que conviene conversar · calca el orden del wizard original,
# que ya está probado con usuarios reales.
ORDEN_CONVERSACION: List[str] = [
    "lifeStage", "timeHorizon", "clarityLevel", "interestType",
    "weeklyActivities", "dontWant", "declaredAspirations",
    "budgetBand", "languageLevel", "geoPreference",
]


def get_hecho(hecho_id: str) -> Optional[Hecho]:
    return _POR_ID.get(hecho_id)


def que_averiguar(hecho_id: str) -> str:
    h = _POR_ID.get(hecho_id)
    return QUE_AVERIGUAR.get(hecho_id) or (h.pregunta_typeform if h else hecho_id)


def aplica(
    hecho_id: str,
    recolectados: Dict[str, Any],
    onboarding: Optional[dict] = None,
    contexto: Optional[dict] = None,
) -> bool:
    """¿Este hecho tiene sentido para esta persona? Reusa el `skip_if` YA
    DEFINIDO en `state_machine` para el paso homónimo — ver el docstring del
    módulo para por qué no se reimplementa aquí.

    Un hecho sin paso homónimo o sin `skip_if` siempre aplica.
    """
    step = get_step(hecho_id)
    if step is None or step.skip_if is None:
        return True
    ctx = {"answers": recolectados, "onboarding": onboarding or {}, **(contexto or {})}
    try:
        return not bool(step.skip_if(ctx))
    except Exception:
        # Ante la duda se pregunta · mismo criterio que `get_next_step`: una
        # condición mal escrita no puede dejar a la persona sin poder cerrar.
        return True


def faltantes(
    recolectados: Dict[str, Any],
    onboarding: Optional[dict] = None,
    contexto: Optional[dict] = None,
) -> List[str]:
    """Lo que falta por saber, obligatorios primero, en el orden de conversación."""

    def peso(h: Hecho) -> tuple:
        return (
            0 if h.id in OBLIGATORIOS else 1,
            ORDEN_CONVERSACION.index(h.id) if h.id in ORDEN_CONVERSACION
            else len(ORDEN_CONVERSACION),
        )

    pendientes = [
        h for h in HECHOS
        if recolectados.get(h.id) in (None, "", [], {})
        and aplica(h.id, recolectados, onboarding, contexto)
    ]
    return [h.id for h in sorted(pendientes, key=peso)]


def listo_para_cerrar(
    recolectados: Dict[str, Any],
    onboarding: Optional[dict] = None,
    contexto: Optional[dict] = None,
) -> bool:
    """Con los obligatorios que APLICAN basta · el resto ya se degrada con
    gracia en los prompts de síntesis/rutas (ver notas de `dontWant` /
    `declaredAspirations` arriba)."""
    return all(
        recolectados.get(i) not in (None, "", [], {})
        for i in OBLIGATORIOS
        if aplica(i, recolectados, onboarding, contexto)
    )
