"""El onboarding de la plataforma, como conversación en vez de formulario.

Verónica, reunión 21-07: *"No podemos llevar la IA a ser como un formulario"* ·
*"con ocho preguntas fui capaz de entender a Sebastián; con trece ni lo entendí"*.

El formulario tiene 14 pasos y en el flujo "quiero estudiar en el exterior" —el de
su propio hijo— se recorren 13. Esto lo reemplaza: un turno de conversación puede
resolver varios hechos a la vez, y los cinco pasos de voz se vuelven simplemente
lo que la persona cuenta.

## Qué se reusa y qué no

El **extractor de hechos** es el mismo del bot comercial, parametrizado por
catálogo (`fact_extractor.extraer(..., catalogo=onboarding_hechos)`). Ahí vive el
riesgo real —escribir en el perfil un valor que la persona nunca dijo— y su
blindaje (tool use forzado, validación contra el vocabulario canónico de la
plataforma, umbral de confianza) tiene que ser idéntico en las dos
conversaciones. Duplicarlo garantizaría que una copia se quedara atrás.

El **motor de turno** no se reusa: el del perfilador arrastra su propio cierre
comercial (contraoferta de destinos, score del lead) que aquí no aplica.

## El contrato con el resto del producto

`a_onboarding_answers()` produce **exactamente** el diccionario que producía el
formulario, con las mismas claves y los mismos códigos. El recomendador, el gate
de menores, `seed_session_from_onboarding` y los prompts de IA siguen leyendo lo
que leían: no saben que la pantalla cambió.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from app.core.ai_client import call_claude_chat, load_prompt
from app.data import onboarding_hechos as catalogo
from app.services.ai_usage_service import record_ai_usage
# Se importa en vez de duplicarse · es una función pura sobre listas y está
# probada contra el modelo real: pedirle en el prompt que no repita una pregunta
# mejora el tono pero no alcanza. Sin esto, el onboarding preguntó el presupuesto
# dos turnos seguidos mientras la persona le daba etapa, fecha y destino — el
# "formulario con burbujas" que esto vino a reemplazar.
from app.services.conversation_engine import _rotar_si_no_respondieron
from app.services.fact_extractor import extraer

logger = logging.getLogger(__name__)

PROMPT_NAME = "onboarding_conversacional"
PROMPT_VERSION = "onboarding_conversacional_v1"
FEATURE = "onboarding_conversacion"

# Cuántos turnos previos se le pasan al modelo. Suficiente para que la
# conversación tenga memoria corta y no para que el prompt crezca sin control.
MAX_HISTORIAL = 16

# Si el modelo no responde, la conversación no puede quedarse muda: la persona
# está en el primer minuto del producto y un silencio se lee como que se rompió.
MENSAJE_FALLBACK = (
    "Perdona, se me enredó la respuesta. ¿Me lo cuentas otra vez?"
)

SALUDO = (
    "¡Hola! Soy Hop. Antes de mostrarte opciones quiero conocerte un poco.\n\n"
    "Cuéntame: ¿qué te apasiona y qué te gustaría lograr?"
)


def _bloque_recolectado(recolectados: Dict[str, Any]) -> str:
    con_valor = {k: v for k, v in recolectados.items() if v not in (None, "", [], {})}
    if not con_valor:
        return "(nada todavía · es el primer mensaje)"
    lineas = []
    for k, v in con_valor.items():
        h = catalogo.get_hecho(k)
        etiqueta = h.pregunta_typeform if h else k
        # Se le muestra la etiqueta legible y no el código: si ve `high_school`,
        # tiende a repetírselo a la persona tal cual.
        if h and h.opciones and isinstance(v, str):
            v = h.opciones.get(v, v)
        elif h and h.opciones and isinstance(v, list):
            v = ", ".join(h.opciones.get(x, x) for x in v)
        lineas.append(f"- {etiqueta} → {v}")
    return "\n".join(lineas)


def _bloque_faltantes(pendientes: List[str]) -> str:
    if not pendientes:
        return "(nada · ya tienes todo lo necesario)"
    lineas = []
    for i, hid in enumerate(pendientes[:6], 1):
        h = catalogo.get_hecho(hid)
        if not h:
            continue
        marca = " ← no lo deduzcas, pregúntalo" if hid in catalogo.DUROS else ""
        lineas.append(f"{i}. {h.pregunta_typeform}{marca}")
    return "\n".join(lineas)


def _bloque_cierre(recolectados: Dict[str, Any], pendientes: List[str]) -> str:
    if not catalogo.listo_para_cerrar(recolectados):
        return ""
    return (
        "## Ya puedes cerrar\n\n"
        "Tienes lo necesario. Cierra en tu próximo mensaje: dile en una o dos "
        "frases lo que entendiste de él —con sus palabras, no con etiquetas— y "
        "que ya puede empezar. No hagas más preguntas."
    )


def primer_mensaje() -> str:
    """Con qué abre la conversación · no lo genera el modelo.

    Es la primera frase que un estudiante lee del producto, y dejarla al modelo
    la volvería distinta en cada sesión y difícil de revisar por la clienta, que
    revisa la copy.
    """
    return SALUDO


def responder(
    mensaje: str,
    historial: List[Dict[str, str]],
    recolectados: Dict[str, Any],
    *,
    session_id: str,
    db: Optional[DBSession] = None,
) -> Tuple[str, Dict[str, Any], bool]:
    """Procesa un turno.

    Returns:
        (respuesta, recolectados_actualizados, listo_para_cerrar).
        `recolectados_actualizados` es un dict NUEVO · quien llama decide si lo
        persiste, y así un fallo a mitad de turno no deja el estado a medias.
    """
    # 1 · Qué dijo · lo nuevo pisa lo viejo, que es cómo funcionan las
    # correcciones ("no, en realidad estoy en décimo").
    nuevos, descartados = extraer(
        mensaje, recolectados, session_id=session_id, db=db, catalogo=catalogo,
    )
    actualizados = {**recolectados, **nuevos}

    if descartados:
        logger.info(
            "onboarding · hechos descartados por el extractor",
            extra={"session_id": session_id, "descartados": descartados},
        )

    # Qué falta, y si el bot ya preguntó por lo primero sin obtener respuesta,
    # eso baja: se retoma más adelante, cuando la conversación dé pie.
    pendientes = _rotar_si_no_respondieron(
        catalogo.faltantes(recolectados) if historial else [],
        catalogo.faltantes(actualizados),
    )

    plantilla = load_prompt(PROMPT_NAME)
    system = (
        plantilla.replace("{recolectado}", _bloque_recolectado(actualizados))
        .replace("{faltantes}", _bloque_faltantes(pendientes))
        .replace("{cierre}", _bloque_cierre(actualizados, pendientes))
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

    if not respuesta:
        # Los hechos extraídos SÍ se conservan aunque la respuesta falle: la
        # persona ya dijo lo que dijo y perderlo la obliga a repetirse.
        logger.warning(
            "onboarding conversacional sin respuesta del modelo",
            extra={"session_id": session_id,
                   "error_kind": meta.get("error_kind")},
        )
        return MENSAJE_FALLBACK, actualizados, catalogo.listo_para_cerrar(actualizados)

    return respuesta, actualizados, catalogo.listo_para_cerrar(actualizados)


def a_onboarding_answers(recolectados: Dict[str, Any]) -> Dict[str, Any]:
    """Lo recolectado, en el formato que guarda `PUT /me/onboarding`.

    **El año de nacimiento se convierte a `YYYY-12-31`**, igual que hacía el
    formulario, y esa fecha no es un detalle: el 31 de diciembre da la edad
    mínima posible para ese año, así que ante la duda la persona se clasifica
    como **menor** y se le pide consentimiento parental. Nunca al revés. Usar
    enero 1 invertiría exactamente esa garantía.
    """
    fuera = catalogo.a_onboarding_answers(recolectados)

    anio = fuera.get("birthdate")
    if isinstance(anio, int):
        fuera["birthdate"] = f"{anio:04d}-12-31"
    elif isinstance(anio, str) and anio.isdigit() and len(anio) == 4:
        fuera["birthdate"] = f"{anio}-12-31"

    return fuera
