"""Motor de conversación del perfilador · un turno = extraer + responder.

El Typeform que este bot reemplaza tiene **61 preguntas** para recoger ~20 hechos:
la inflación es el árbol de decisión (el destino se pregunta 10 veces, una por
rama). Una conversación no necesita ramas — pregunta lo que falta.

Por eso el motor no recorre un guion. Cada turno:

1. Extrae del mensaje los hechos que la persona dijo (`fact_extractor`).
2. Los mezcla con lo ya recolectado — lo nuevo pisa lo viejo, que es cómo
   funcionan las correcciones.
3. Calcula qué falta y en qué orden.
4. Le pasa al modelo **lo que falta**, no una pregunta fija, y deja que él elija
   cómo pedirlo dado lo que la persona acaba de decir.

Verónica, 21-07 (38:26): *"yo tengo que volverme tan inteligente de preguntar las
tantas preguntas necesite, pero tampoco volverlo casi que un formulario, porque
no hice nada"*.

**La métrica de éxito es turnos, no cobertura**: los mismos hechos en la mitad de
preguntas. Si el bot necesita 61 turnos, falló aunque los recoja todos.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from app.core.ai_client import call_claude_chat, load_prompt
from app.data.perfilador_typeform import (
    DESTINOS_CONTRAOFERTA,
    HECHOS,
    faltantes,
    get_hecho,
    ids_obligatorios,
)
from app.services.ai_usage_service import record_ai_usage
from app.services.fact_extractor import extraer

logger = logging.getLogger(__name__)

PROMPT_NAME = "bot_perfilador"
PROMPT_VERSION = "bot_perfilador_v1"
FEATURE = "bot_conversacion"

# Cap del historial que viaja al modelo · mismo criterio que `hop_chat_service`.
MAX_HISTORIAL = 12

# Cuántos hechos faltantes se le muestran al modelo por turno. Mostrarle los 25
# lo empuja a encadenar preguntas, que es justo la queja de la clienta.
MAX_FALTANTES_VISIBLES = 5

MENSAJE_FALLBACK = (
    "Perdón, se me cruzaron los cables. ¿Me lo repites?"
)


def _orden_de_prioridad(hecho_id: str) -> tuple:
    """Obligatorios primero, después el resto en el orden del catálogo.

    Dentro de los obligatorios manda el orden del catálogo, que ya está pensado
    como conversación: contacto → filtros duros → intención → destino → cierre.
    """
    obligatorios = ids_obligatorios()
    indice = [h.id for h in HECHOS].index(hecho_id)
    return (0 if hecho_id in obligatorios else 1, indice)


def _faltantes_priorizados(recolectados: Dict[str, Any]) -> List[str]:
    pendientes = [h.id for h in faltantes(recolectados)]
    return sorted(pendientes, key=_orden_de_prioridad)


def _rotar_si_no_respondieron(antes: List[str], ahora: List[str]) -> List[str]:
    """Baja el hecho que encabezaba la lista si sigue sin respuesta.

    Probado contra el modelo real: pedirle en el prompt que no repita una
    pregunta mejora el tono pero **no alcanza**. En la primera corrida insistió
    tres turnos seguidos con el pasaporte mientras la persona le daba destino,
    presupuesto y tipo de programa — que es exactamente el "formulario con
    burbujas" que este bot vino a reemplazar.

    Si el hecho que encabezaba la lista en el turno anterior sigue encabezándola,
    es porque el bot ya preguntó por él y no le respondieron. Se manda al final
    de la ventana: se retoma más adelante, cuando la conversación dé pie.
    """
    if antes and ahora and antes[0] == ahora[0] and len(ahora) > 1:
        return ahora[1:] + [ahora[0]]
    return ahora


def _bloque_recolectado(recolectados: Dict[str, Any]) -> str:
    lineas: List[str] = []
    for hecho in HECHOS:
        valor = recolectados.get(hecho.id)
        if valor is None:
            continue
        if hecho.opciones and isinstance(valor, str):
            valor = hecho.opciones.get(valor, valor)
        elif hecho.opciones and isinstance(valor, list):
            valor = ", ".join(hecho.opciones.get(v, v) for v in valor)
        elif isinstance(valor, bool):
            valor = "sí" if valor else "no"
        lineas.append(f"- {hecho.pregunta_typeform} → {valor}")
    return "\n".join(lineas) if lineas else "(nada todavía · acaba de llegar)"


def _bloque_faltantes(pendientes: List[str]) -> str:
    if not pendientes:
        return "(ya tienes todo lo esencial · toca confirmar y cerrar)"
    lineas: List[str] = []
    for hecho_id in pendientes[:MAX_FALTANTES_VISIBLES]:
        hecho = get_hecho(hecho_id)
        if hecho is None:
            continue
        linea = f"- {hecho.pregunta_typeform}"
        if hecho.opciones:
            linea += f"  ({' · '.join(hecho.opciones.values())})"
        lineas.append(linea)
    return "\n".join(lineas)


def _bloque_cierre(recolectados: Dict[str, Any], pendientes: List[str]) -> str:
    """Instrucción extra según en qué punto va la conversación."""
    if pendientes:
        return ""
    return (
        "## Ahora\n\n"
        "Ya tienes todo lo esencial. Resume en dos líneas lo que entendiste y "
        "pregúntale si vas bien, antes de despedirte."
    )


def responder(
    mensaje: str,
    historial: List[Dict[str, str]],
    recolectados: Dict[str, Any],
    *,
    session_id: str,
    db: Optional[DBSession] = None,
) -> Tuple[str, Dict[str, Any], List[str]]:
    """Procesa un turno completo del perfilador.

    Args:
        mensaje: lo que escribió la persona.
        historial: turnos previos ``[{"role": "user"|"assistant", "content": ...}]``.
        recolectados: hechos acumulados hasta ahora.
        session_id: para tracking M-001 y logs.
        db: sesión para registrar consumo de IA.

    Returns:
        (respuesta_del_bot, recolectados_actualizados, descartados_por_el_extractor).
        `recolectados_actualizados` es un dict NUEVO — el llamador decide si lo
        persiste, y así un fallo a mitad de turno no deja el estado a medias.
    """
    # 1 · Qué dijo. Lo nuevo pisa lo viejo: así funcionan las correcciones de la
    # confirmación ("no, en realidad son 20 mil").
    nuevos, descartados = extraer(mensaje, recolectados, session_id=session_id, db=db)
    actualizados = {**recolectados, **nuevos}

    # 2 · Qué falta, en el orden en que conviene pedirlo. Si el bot ya preguntó
    # por el primero y no le respondieron, ese baja: insistir es lo que vuelve
    # esto un formulario.
    pendientes = _rotar_si_no_respondieron(
        _faltantes_priorizados(recolectados) if historial else [],
        _faltantes_priorizados(actualizados),
    )

    plantilla = load_prompt(PROMPT_NAME)
    system = (
        plantilla.replace("{recolectado}", _bloque_recolectado(actualizados))
        .replace("{faltantes}", _bloque_faltantes(pendientes))
        .replace("{destinos}", " · ".join(DESTINOS_CONTRAOFERTA))
        .replace("{cierre}", _bloque_cierre(actualizados, pendientes))
    )

    recortado = list(historial or [])[-MAX_HISTORIAL:]
    mensajes = [{"role": t["role"], "content": t["content"]} for t in recortado]
    mensajes.append({"role": "user", "content": mensaje})

    respuesta, meta = call_claude_chat(
        mensajes,
        system=system,
        session_id=session_id,
        feature=FEATURE,
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
        # persona ya dijo lo que dijo, y perderlo la obliga a repetirse.
        logger.warning(
            "bot_perfilador sin respuesta del modelo",
            extra={"session_id": session_id, "error_kind": meta.get("error_kind")},
        )
        return MENSAJE_FALLBACK, actualizados, descartados

    return respuesta, actualizados, descartados


def listo_para_cerrar(recolectados: Dict[str, Any]) -> bool:
    """True cuando están todos los hechos obligatorios.

    No lo decide el modelo: si dependiera de que él lo declare, una conversación
    podría cerrarse sin correo ni celular y el lead no serviría para nada.
    """
    return all(recolectados.get(hecho_id) is not None for hecho_id in ids_obligatorios())
