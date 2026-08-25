"""El Journey como chat continuo · JP, reunión 24-08 (10:48 y 18:25).

    "esto del journey a mi todavia no me convence"
    "en Journey yo lo que me imagino es que sea como un chat continuo que le
     vaya haciendo preguntas al usuario para irlo perfilando"

## Por qué esto y no ampliar `journey_interprete`

Ya existe un mecanismo que deja contestar UN paso del wizard hablando en vez
de haciendo clic (`app.services.journey_interprete`, detrás del flag
`journey_conversacional`), con un plan explícito de ampliarlo paso a paso:
*"se enciende uno, se mira en producción, y sólo entonces se amplía"* — hay
hasta un test de gobierno (`test_solo_un_paso_esta_habilitado`) que avisa si
alguien lo amplía de golpe. Ese plan sigue vigente y **este módulo no lo
toca**: seguir ampliándolo sin los datos de producción que el propio plan
pide sería saltarse la decisión de quien lo diseñó.

Pero incluso ampliado del todo, `journey_interprete` no cambia la FORMA:
sigue siendo un wizard de una pregunta por pantalla que además admite texto.
Lo que describe JP —"un chat continuo"— es otra cosa: una sola conversación
que decide en cada turno qué falta, exactamente como YA hace
`app.services.onboarding_conversacional` sobre `app.data.onboarding_hechos`.
Este módulo es ESE patrón, aplicado a los hechos que hoy recorre el tramo
CONTEXT/INTERESTS/CONSTRAINTS del Journey (ver
`app.data.journey_chat_hechos`).

## Qué NO cambia

- `Session.answers` se llena con las MISMAS claves (`lifeStage`,
  `interestType`, `budgetBand`...) que ya llenaba el wizard — el contrato con
  `journey_service`, los servicios que leen el Journey aguas abajo, y el
  panel lateral (`ProfilePreview`) no se toca.
- La síntesis y las rutas (`SYNTHESIS`/`ROUTES_PICKER`, los pasos con IA más
  caros de este flujo) NO se reconstruyen aquí: cuando el chat termina de
  perfilar, la entrega vive en `app.api.v1.journey_chat` y usa el motor de
  siempre (`journey_service.build_journey_response` /
  `state_machine.get_next_step`) para esa parte — la que ya está probada y
  es la más cara de romper.
- Nadie que esté a mitad del wizard actual se ve afectado: este chat vive
  detrás de un flag nuevo y de endpoints nuevos
  (`/api/v1/journey-chat/...`). Con el flag apagado el wizard de botones
  sigue exactamente igual.

## Qué SÍ reusa

El extractor de hechos (`app.services.fact_extractor.extraer`, parametrizado
por catálogo — el mismo mecanismo que usa `onboarding_conversacional`): tool
use forzado, validación contra el vocabulario canónico (que aquí SALE de
`state_machine.JOURNEY_STEPS` en tiempo de import, no se copia a mano),
umbral de confianza. Duplicar ese blindaje garantizaría que una copia se
quedara atrás.

## Los pasos de pantalla que este chat NO cubre

`whyHere` (redundante con `main_goal`, ya capturado en el onboarding),
`empathy` y `partialSummary1` (pantallas de reflexión) y `testInvitation`
(JR-2, efecto lateral que depende del texto exacto de la opción) no son
hechos que recoger — son screens del wizard. Aquí, Hop reacciona a lo que la
persona cuenta DENTRO de la conversación misma en vez de en una pantalla
aparte: es más fiel a "un chat continuo" que insertar una pausa de reflexión
entre preguntas. El handoff (`app.api.v1.journey_chat`) retoma la cadena real
de `state_machine` justo DESPUÉS de `geoPreference`, así que si
`journey_test_invitation` estuviera encendido para alguien, este primer
alcance simplemente no se lo ofrece — mismo criterio conservador que ya usó
`journey_interprete` con ese mismo paso.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from app.core.ai_client import call_claude_chat, load_prompt
from app.data import journey_chat_hechos as catalogo
from app.data import journey_videos
from app.services.ai_usage_service import record_ai_usage
from app.services.fact_extractor import extraer

logger = logging.getLogger(__name__)

PROMPT_NAME = "journey_chat"
FEATURE = "journey_chat_continuo"

# Turnos previos que se le pasan al modelo · memoria corta sin que el prompt
# crezca sin control (mismo tope que `onboarding_conversacional`).
MAX_HISTORIAL = 16

MENSAJE_FALLBACK = "Perdona, se me enredó la respuesta. ¿Me lo cuentas otra vez?"

SALUDO = (
    "Ya te conozco un poco por lo que me contaste al entrar. Ahora quiero "
    "entender hacia dónde vas — con calma, a tu ritmo.\n\n"
    "Para empezar: hoy, ¿te sientes más cerca de terminar el colegio, estar "
    "en la universidad, ya trabajando, o en una transición?"
)

# `interestType` es el único hecho `multi` de este catálogo y su tope viene
# del paso original del wizard (`state_machine.get_step("interestType")
# .max_select`). `fact_extractor` no conoce límites por hecho — se recorta
# AQUÍ, después de extraer, para no tocar un módulo compartido con el resto
# del producto (onboarding, perfilador comercial) por un límite que sólo
# aplica a este hecho.
MAX_INTEREST_TYPE = 2


def primer_mensaje() -> str:
    """Con qué abre el chat · no lo genera el modelo (igual que
    `onboarding_conversacional.primer_mensaje`): es lo primero que lee la
    persona en esta pantalla y tiene que ser estable y revisable por la
    clienta, que revisa la copy."""
    return SALUDO


def _bloque_recolectado(recolectados: Dict[str, Any]) -> str:
    con_valor = {k: v for k, v in recolectados.items() if v not in (None, "", [], {})}
    if not con_valor:
        return "(nada todavía · es el primer mensaje de este tramo)"
    lineas = []
    for k, v in con_valor.items():
        h = catalogo.get_hecho(k)
        etiqueta = h.pregunta_typeform if h else k
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        lineas.append(f"- {etiqueta} → {v}")
    return "\n".join(lineas)


def _bloque_faltantes(pendientes: List[str]) -> str:
    """Una sola pregunta destacada, el resto como contexto · mismo criterio
    que `onboarding_conversacional._bloque_faltantes`: mostrarle varias a la
    vez lo hace agrupar dos hechos en un mensaje, que es lo que un chat
    continuo NO puede hacer sin volver a sentirse un formulario."""
    if not pendientes:
        return "(nada · ya tienes todo lo necesario para pasar a mostrarle algo)"

    lineas = [
        f"**Lo único que quieres averiguar ahora:** "
        f"{catalogo.que_averiguar(pendientes[0])}",
        "",
        "Formula tú la pregunta a partir de lo que acaba de contarte. Una "
        "sola pregunta por mensaje — meter dos vuelve esto un formulario.",
    ]
    despues = [catalogo.que_averiguar(x) for x in pendientes[1:4]]
    if despues:
        lineas += ["", "Queda para más adelante — **no lo preguntes todavía**:"]
        lineas += [f"- {x}" for x in despues]
    return "\n".join(lineas)


def _bloque_cierre(listo: bool) -> str:
    if not listo:
        return ""
    return (
        "## Ya puedes cerrar\n\n"
        "Tienes lo necesario. Cierra en tu próximo mensaje: dile en una o dos "
        "frases lo que entendiste de él —con sus palabras, no con "
        "etiquetas— y que ya vas a mostrarle algo con sentido. No hagas más "
        "preguntas."
    )


def _bloque_onboarding(onboarding: Optional[dict]) -> str:
    """Lo que ya sabe del registro · para que Hop no vuelva a preguntar lo
    mismo ni suene a que empieza de cero. Es la misma queja, dos veces:
    Sandra y Verónica, sobre el journey ANTERIOR (P1-4/S9): *"me hizo 13
    preguntas y me va a volver a decir que comencemos"*."""
    if not onboarding:
        return "(sesión sin registro previo · no asumas nada de él todavía)"
    piezas = []
    metas = onboarding.get("main_goal")
    if metas:
        piezas.append(f"Ya te dijo qué busca resolver: {metas}")
    pasion = onboarding.get("voice_passion")
    if pasion:
        piezas.append(f"Ya te contó qué le apasiona: {pasion}")
    return "\n".join(f"- {p}" for p in piezas) or "(nada más relevante todavía)"


def responder(
    mensaje: str,
    historial: List[Dict[str, str]],
    recolectados: Dict[str, Any],
    *,
    session_id: str,
    db: Optional[DBSession] = None,
    onboarding: Optional[dict] = None,
    contexto: Optional[dict] = None,
    ruta: Optional[str] = None,
) -> Tuple[str, Dict[str, Any], bool, Optional[journey_videos.JourneyVideo]]:
    """Procesa un turno del chat continuo del Journey.

    Args:
        mensaje: lo que acaba de escribir la persona.
        historial: turnos previos (rol/contenido) · vive en el cliente, igual
            que en `onboarding_conversacional` — no hay tabla de conversación
            aquí, lo que importa persistir son los hechos.
        recolectados: lo ya sabido de ESTE tramo (subconjunto de
            `Session.answers`, sólo las claves de `journey_chat_hechos`).
        onboarding: `User.onboarding_answers` del dueño de la sesión, o None
            si es anónima — para `_bloque_onboarding` y para `aplica()`.
        contexto: lo que `skip_if` necesita y no se deduce de las respuestas
            (mismo shape que `journey_service.contexto_de_navegacion`).
        ruta: una de las 5 rutas de la malla (Cimientos), si se conoce — sólo
            para elegir video por ruta; None es un comportamiento válido.

    Returns:
        (respuesta, recolectados_actualizados, listo_para_cerrar, video_sugerido).
        `recolectados_actualizados` es un dict NUEVO · quien llama decide si
        lo persiste, para que un fallo a mitad de turno no deje el estado a
        medias.
    """
    nuevos, descartados = extraer(
        mensaje, recolectados, session_id=session_id, db=db, catalogo=catalogo,
    )
    if isinstance(nuevos.get("interestType"), list):
        nuevos["interestType"] = nuevos["interestType"][:MAX_INTEREST_TYPE]
    actualizados = {**recolectados, **nuevos}

    if descartados:
        logger.info(
            "journey_chat · hechos descartados por el extractor",
            extra={"session_id": session_id, "descartados": descartados},
        )

    pendientes = catalogo.faltantes(actualizados, onboarding, contexto)
    listo = catalogo.listo_para_cerrar(actualizados, onboarding, contexto)

    plantilla = load_prompt(PROMPT_NAME)
    system = (
        plantilla.replace("{onboarding}", _bloque_onboarding(onboarding))
        .replace("{recolectado}", _bloque_recolectado(actualizados))
        .replace("{faltantes}", _bloque_faltantes(pendientes))
        .replace("{cierre}", _bloque_cierre(listo))
    )

    recortado = list(historial or [])[-MAX_HISTORIAL:]
    mensajes = [{"role": t["role"], "content": t["content"]} for t in recortado]
    mensajes.append({"role": "user", "content": mensaje})

    respuesta, meta = call_claude_chat(
        mensajes, system=system, session_id=session_id, feature=FEATURE,
    )

    if db is not None:
        record_ai_usage(
            db,
            provider="anthropic",
            model=meta.get("model"),
            feature=FEATURE,
            tokens_input=meta.get("tokens_input"),
            tokens_output=meta.get("tokens_output"),
            latency_ms=meta.get("latency_ms"),
        )

    # Se ofrece un video del hecho que ACABA de completarse en este turno,
    # si la clienta ya cargó uno para ese momento y la persona no tiene
    # claridad alta (regla de JP, ver `journey_videos.elegir_video`).
    video = None
    for hecho_id in nuevos:
        video = journey_videos.elegir_video(hecho_id, actualizados, ruta)
        if video is not None:
            break

    if not respuesta:
        # Los hechos extraídos SÍ se conservan aunque la respuesta falle: la
        # persona ya dijo lo que dijo y perderlo la obliga a repetirse.
        logger.warning(
            "journey_chat sin respuesta del modelo",
            extra={"session_id": session_id, "error_kind": meta.get("error_kind")},
        )
        return MENSAJE_FALLBACK, actualizados, listo, video

    return respuesta, actualizados, listo, video
