"""Lo que el estudiante contó con sus palabras → la opción canónica del paso.

El Journey se presenta como *"una conversación con Hop"* y no lo era: pintaba
burbujas con su avatar, pero cada paso era un `SINGLE_CHOICE` contra la máquina
de estados, sin una sola llamada al modelo. Hop no leía lo que respondías —
pasaba a la siguiente página del guion. Se nota más desde que Hopper chatea en
toda la app: mismo personaje, misma estética, pero uno escucha y el otro pasa
páginas.

## La regla que ordena todo este módulo

**El valor que se guarda NO cambia.** El texto libre es un *camino de entrada*
nuevo, no un formato nuevo. Si pulsar el botón guarda `"Proyectos prácticos"`,
escribir *"me gustaría estar armando cosas con las manos"* guarda **exactamente
`"Proyectos prácticos"`**. Aguas abajo nadie se entera de que hubo conversación.

No es purismo: las respuestas del Journey las leen SEIS servicios, entre ellos
`clinical_analysis_service` (el detector de riesgo suicida, que el CLAUDE.md
prohíbe tocar) y `crm_service` (escribe en Bitrix, el CRM de producción de la
clienta). Cambiar la forma del dato es tocarlos a todos por la puerta de atrás.

## Este módulo NO escribe nada

Devuelve una lectura y se aparta. Quien guarda sigue siendo `process_event` con
el evento `answer` de siempre —el mismo que dispara el botón—, así que el camino
que escribe en la sesión no cambió ni una línea y una caída del modelo no puede
tocarlo. El front manda el valor canónico por el endpoint de siempre.

## Tres cosas lo hacen seguro

1. **Sólo puede devolver una opción que ya existe.** `call_claude_tool` con las
   opciones del paso como `enum`, y después la validación de
   `fact_extractor.normalizar_opcion` contra esas mismas opciones. Si el modelo
   inventa una, se descarta. El vocabulario sale de `state_machine.JOURNEY_STEPS`
   en tiempo de ejecución: la copy es de la clienta y así el `enum` la sigue sin
   que nadie tenga que acordarse de este archivo.
2. **`None` es una respuesta válida y esperada.** Si se fue por las ramas o dijo
   algo ambiguo, Hop **repregunta**. Nunca se elige una opción "a ver si pega":
   una respuesta mal interpretada acaba en su perfil, en su hoja de vida y en el
   dossier que lee su asesora.
3. **Con confianza `media` se confirma** antes de guardar: *"entiendo que
   prefieres proyectos prácticos, ¿es así?"*. Un clic barato que evita un dato
   torcido.

El umbral es el mismo que el del extractor del onboarding (`alta` · `media` ·
`baja`), y por la misma razón: es el vocabulario con el que el modelo ya está
calibrado en este repo. La diferencia es qué se hace con `media` — allá se
persiste, aquí se pregunta. Allá la conversación sigue y puede corregirse en el
turno siguiente; aquí el paso se cierra y no hay segunda oportunidad.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession

from app.core.state_machine import JourneyStep, ViewType

logger = logging.getLogger(__name__)

# El flag vive en base (tabla `feature_flags`), como el de JR-2, y no en el
# entorno: encenderlo por rol para mostrárselo a la clienta no debería requerir
# un deploy de Heroku. `is_feature_enabled` es fail-closed —sin la fila, todo
# apagado—, así que producción sigue igual sin crear nada.
FLAG = "journey_conversacional"

# **Un paso primero.** El plan es explícito: se enciende uno, se mira en
# producción, y sólo entonces se amplía. Si el intérprete se equivoca
# sistemáticamente en un tipo de pregunta, es mucho mejor descubrirlo con un
# paso que con ocho.
#
# Es `weeklyActivities` y no el de etapa de vida —el candidato "natural"— por
# una razón medible: `lifeStage` se siembra desde el onboarding
# (`_ONBOARDING_LIFE_STAGE_MAP`, y `life_stage` es la PRIMERA pregunta del
# onboarding, con las 6 opciones mapeadas), así que `get_next_step` lo salta
# siempre para cualquiera que se haya registrado. Encenderlo ahí sería mirar
# producción y no ver nada. `weeklyActivities` no se siembra desde ningún lado,
# sus 5 opciones son concretas y bien separadas, y es de las preguntas que la
# gente contesta con rodeos de forma natural.
#
# Los pasos de pantalla (`WELCOME`, `REFLECTION`, `PARTIAL_SUMMARY`…) y los de
# efecto lateral (`TEST_INVITATION`, que saca a la persona del journey y depende
# del TEXTO de la opción) quedan fuera por lista explícita, no por descarte.
PASOS_HABILITADOS: tuple[str, ...] = ("weeklyActivities",)

PROMPT_NAME = "journey_interprete"
PROMPT_VERSION = "journey_interprete_v1"
FEATURE = "journey_interprete"

# Tope de la respuesta hablada. Es UNA respuesta a UNA pregunta, no un texto
# pegado: 2000 caracteres es holgado incluso dictando, y acota costo y prompt.
MAX_TEXTO = 2000

# Con el modelo caído la conversación no puede quedarse muda, y los botones
# siguen ahí: se le dice justo eso.
MENSAJE_SIN_MODELO = (
    "Perdona, se me enredó la respuesta. ¿Me lo cuentas otra vez, o prefieres "
    "elegir una de las opciones?"
)

# Sólo estas dos proponen una opción. `baja` no propone nada · ver punto 2.
_CONFIANZAS = ("alta", "media", "baja")
_CONFIANZA_QUE_PROPONE = ("alta", "media")


@dataclass
class Interpretacion:
    """Lo leído · nunca lo guardado.

    `opcion` es SIEMPRE una de las opciones del paso, o None. `necesita_confirmar`
    traduce la confianza a lo único que el front tiene que decidir: ¿avanzo o
    pregunto?
    """

    opcion: Optional[str]
    confianza: str
    respuesta_de_hop: str
    necesita_confirmar: bool


def paso_habilitado(step: Optional[JourneyStep]) -> bool:
    """¿Este paso admite texto libre, dejando el flag aparte?

    Se exige además que sea una pregunta de opciones con `save_to`: un paso de
    pantalla no tiene nada que interpretar, y sin `save_to` no habría dónde
    guardar la lectura.
    """
    if step is None or step.id not in PASOS_HABILITADOS:
        return False
    return (
        step.view_type == ViewType.SINGLE_CHOICE
        and bool(step.options)
        and bool(step.save_to)
    )


def acepta_texto_libre(db: DBSession, session, step: Optional[JourneyStep]) -> bool:
    """La decisión de si este paso conversa · **una sola vez, aquí**.

    La consume el backend (para aceptar o rechazar la interpretación) y el front
    (para pintar el campo de texto) a través de `acepta_texto_libre` en la
    respuesta del journey. Este repo ya se quemó dos veces con dos sitios
    decidiendo lo mismo y divergiendo (P0-8), así que el front no reimplementa
    la condición: la lee.

    Sesión anónima → False: sin usuario no hay flag que resolver, y el journey
    se comporta como siempre.
    """
    if not paso_habilitado(step):
        return False
    if getattr(session, "user_id", None) is None:
        return False

    from app.db.models import User
    from app.services.feature_flags_service import is_feature_enabled

    owner = db.query(User).filter(User.id == session.user_id).first()
    if owner is None:
        return False
    return is_feature_enabled(db, FLAG, owner)


def _esquema(step: JourneyStep) -> Dict[str, Any]:
    """El esquema del tool call · el `enum` son las opciones del paso.

    `opcion` **no** es obligatoria a propósito: omitirla es cómo el modelo se
    abstiene, y abstenerse tiene que ser posible. Lo obligatorio es declarar la
    confianza y decirle algo a la persona.
    """
    opciones: List[str] = list(step.options or [])
    return {
        "type": "object",
        "properties": {
            "opcion": {
                "type": "string",
                "enum": opciones,
                "description": (
                    "A qué opción del paso equivale lo que dijo. Omítela si no "
                    "corresponde limpiamente a ninguna."
                ),
            },
            "confianza": {
                "type": "string",
                "enum": list(_CONFIANZAS),
                "description": "Qué tan explícito fue lo que dijo la persona.",
            },
            "respuesta_de_hop": {
                "type": "string",
                "description": (
                    "Lo que Hop le dice: reacción si entendió, pregunta de "
                    "confirmación si duda, repregunta si no entendió."
                ),
            },
        },
        "required": ["confianza", "respuesta_de_hop"],
    }


def _opciones_para_prompt(step: JourneyStep) -> str:
    return "\n".join(f"- {opcion}" for opcion in (step.options or []))


def interpretar(
    texto: str,
    step: JourneyStep,
    *,
    session_id: str,
    db: Optional[DBSession] = None,
    user_id: Optional[Any] = None,
) -> Interpretacion:
    """Lee la respuesta hablada del paso. **No guarda nada.**

    Args:
        texto: lo que escribió (o dictó) la persona.
        step: el paso del journey, de donde salen la pregunta y las opciones.
        session_id: para logs y tracking M-001.
        db: sesión para `record_ai_usage`. Sin ella no se registra consumo.
        user_id: dueño de la sesión, para que el consumo quede atribuido.

    Nunca lanza: ante cualquier fallo devuelve una interpretación vacía con un
    mensaje de Hop. Los botones son la red de seguridad y el paso se completa
    igual, como hoy.
    """
    texto = (texto or "").strip()[:MAX_TEXTO]

    # Import diferido, como el resto de los servicios de IA de este repo: deja
    # el módulo importable sin credenciales y no penaliza el arranque.
    from app.core.ai_client import call_claude_tool, load_prompt
    from app.data.perfilador_typeform import Hecho
    from app.services.ai_usage_service import record_ai_usage
    from app.services.fact_extractor import normalizar_opcion

    prompt = (
        load_prompt(PROMPT_NAME)
        .replace("{pregunta}", step.question or "")
        .replace("{opciones}", _opciones_para_prompt(step))
        .replace("{respuesta}", texto)
    )

    salida, meta = call_claude_tool(
        prompt,
        tool_name="registrar_lectura",
        tool_description=(
            "Registra a qué opción del paso equivale lo que dijo la persona, y "
            "qué le responde Hop. Solo lo que dijo — nunca lo que probablemente "
            "quiso decir."
        ),
        input_schema=_esquema(step),
        session_id=session_id,
        feature=FEATURE,
        max_tokens=600,
        temperature=0.0,
        prompt_version=PROMPT_VERSION,
    )

    # M-001 · se registra también el intento fallido (tokens en None), para que
    # el panel de costos vea los errores y no sólo los éxitos.
    if db is not None:
        record_ai_usage(
            db,
            provider="anthropic",
            model=meta.get("model"),
            feature=FEATURE,
            tokens_input=meta.get("tokens_input"),
            tokens_output=meta.get("tokens_output"),
            latency_ms=meta.get("latency_ms"),
            user_id=user_id,
        )

    if not salida:
        logger.warning(
            "journey_interprete sin lectura del modelo",
            extra={
                "session_id": session_id,
                "step_id": step.id,
                "error_kind": meta.get("error_kind"),
            },
        )
        return Interpretacion(
            opcion=None,
            confianza="baja",
            respuesta_de_hop=MENSAJE_SIN_MODELO,
            necesita_confirmar=False,
        )

    confianza = salida.get("confianza")
    if confianza not in _CONFIANZAS:
        confianza = "baja"

    # La validación contra el vocabulario canónico se reusa del extractor. Aquí
    # el "código" y la "etiqueta" son la misma cadena —el texto de la opción, que
    # es lo que se guarda—, así que un valor inventado no tiene por dónde colarse.
    hecho = Hecho(
        id=step.save_to or step.id,
        pregunta_typeform=step.question or "",
        bloque="journey",
        tipo="opcion",
        opciones={opcion: opcion for opcion in (step.options or [])},
    )
    propuesta = salida.get("opcion")
    opcion = (
        normalizar_opcion(hecho, propuesta) if isinstance(propuesta, str) else None
    )

    if opcion is not None and confianza not in _CONFIANZA_QUE_PROPONE:
        # El modelo eligió una opción y a la vez dijo que no está seguro. Se le
        # cree lo segundo: es más barato repreguntar que torcer el perfil.
        opcion = None

    if opcion is None and propuesta:
        logger.info(
            "journey_interprete descartó la opción propuesta",
            extra={
                "session_id": session_id,
                "step_id": step.id,
                "confianza": confianza,
            },
        )

    respuesta_de_hop = salida.get("respuesta_de_hop")
    if not isinstance(respuesta_de_hop, str) or not respuesta_de_hop.strip():
        respuesta_de_hop = MENSAJE_SIN_MODELO
    respuesta_de_hop = respuesta_de_hop.strip()[:600]

    return Interpretacion(
        opcion=opcion,
        confianza=confianza,
        respuesta_de_hop=respuesta_de_hop,
        # Con `alta` avanza solo; con `media` la persona confirma con un clic.
        necesita_confirmar=bool(opcion) and confianza == "media",
    )
