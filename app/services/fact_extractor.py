"""Extractor de hechos del perfilador · lo que dijo la persona → campos validados.

El bot conversa en texto libre (decisión de producto de JP: nada de chips ni
botones). Eso deja un punto único de fallo entre lo que la persona escribe y los
campos que alimentan el journey, el CRM y el dossier — si aquí se cuela un valor
inventado, `seed_answers_from_onboarding` lo siembra sin saberlo.

Cuatro cosas contienen ese riesgo, y ninguna es buena fe:

1. **Tool use forzado** (`ai_client.call_claude_tool`) · el modelo no puede
   responder prosa, y el `input` llega parseado por el SDK.
2. **Validación contra el vocabulario de la plataforma** · un valor que no esté
   en las opciones canónicas de `perfilador_typeform` NO se escribe. Se descarta
   y el hecho vuelve a la lista de faltantes.
3. **Umbral de confianza** · `baja` no se persiste, aunque el modelo la proponga.
4. **Confirmación conversacional** · el motor refleja lo entendido antes de
   cerrar, y lo que la persona corrija pisa lo extraído.

La regla de fondo: **ante la duda no se escribe nada**. Que se vuelva a preguntar
es barato; que el perfil afirme algo que la persona nunca dijo, no.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from app.core.ai_client import call_claude_tool, load_prompt
from app.data.perfilador_typeform import HECHOS, Hecho, get_hecho
from app.services.ai_usage_service import record_ai_usage

logger = logging.getLogger(__name__)

PROMPT_NAME = "bot_extractor"
PROMPT_VERSION = "bot_extractor_v1"
FEATURE = "bot_extraccion"

# `baja` nunca se persiste · ver punto 3 del docstring.
CONFIANZA_ACEPTADA = {"alta", "media"}

# Tope por campo de texto libre. Mismo criterio que la auditoría R5 aplicó a las
# respuestas de voz: sin tope, un mensaje larguísimo infla todos los prompts que
# después reciben este contexto.
MAX_TEXTO = 600

# Sí/no en las formas en que la gente realmente responde.
_VERDADERO = {"true", "si", "sí", "yes", "y", "1", "claro", "correcto"}
_FALSO = {"false", "no", "n", "0", "nunca", "negativo"}


def _tool_schema() -> Dict[str, Any]:
    """Schema del tool call · **estable entre turnos, a propósito**.

    El enum de `id` lista TODOS los hechos, no solo los que faltan. Es tentador
    acotarlo a los pendientes para guiar al modelo, pero las definiciones de
    tools se renderizan en la posición 0 del prompt: si cambian entre turnos,
    invalidan la caché de todo lo que va después. Cuáles faltan se dice en el
    prompt, que va después y puede cambiar barato.
    """
    return {
        "type": "object",
        "properties": {
            "hechos": {
                "type": "array",
                "description": "Un elemento por hecho que la persona dijo en este mensaje.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "enum": [h.id for h in HECHOS],
                            "description": "Cuál de los hechos del catálogo se está registrando.",
                        },
                        "valor": {
                            "type": "string",
                            "description": (
                                "El valor, como código de las opciones cuando el hecho "
                                "tiene opciones. Vacío si el hecho admite varios."
                            ),
                        },
                        "valores": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Solo para hechos que admiten varios valores.",
                        },
                        "confianza": {
                            "type": "string",
                            "enum": ["alta", "media", "baja"],
                            "description": "Qué tan explícito fue lo que dijo la persona.",
                        },
                    },
                    "required": ["id", "confianza"],
                },
            }
        },
        "required": ["hechos"],
    }


def _catalogo_para_prompt() -> str:
    """Los hechos y sus opciones, en el formato que lee el extractor."""
    lineas: List[str] = []
    for hecho in HECHOS:
        partes = [f"- `{hecho.id}` · {hecho.pregunta_typeform}"]
        if hecho.opciones:
            codigos = " · ".join(
                f"`{codigo}` ({etiqueta})" for codigo, etiqueta in hecho.opciones.items()
            )
            partes.append(f"  opciones: {codigos}")
        elif hecho.tipo == "booleano":
            partes.append("  responde `true` o `false`")
        elif hecho.tipo == "entero":
            partes.append("  un número entero")
        if hecho.tipo == "multi":
            partes.append("  admite varios · usa `valores`")
        lineas.append("\n".join(partes))
    return "\n".join(lineas)


def _recolectado_para_prompt(recolectados: Dict[str, Any]) -> str:
    con_valor = {k: v for k, v in recolectados.items() if v is not None}
    if not con_valor:
        return "(nada todavía · es el primer mensaje)"
    return "\n".join(f"- `{k}`: {v}" for k, v in con_valor.items())


def _normalizar_opcion(hecho: Hecho, crudo: str) -> Optional[str]:
    """Devuelve el código canónico, o None si no mapea limpiamente.

    Acepta el código exacto y también la etiqueta visible, porque el modelo a
    veces devuelve la que leyó en el catálogo. Lo que NO hace es adivinar por
    parecido: un valor que no está en las opciones se descarta, que es lo que
    impide que `budget` termine con un texto que `seed_answers_from_onboarding`
    no sabe traducir.
    """
    if not hecho.opciones:
        return None
    valor = (crudo or "").strip()
    if not valor:
        return None
    if valor in hecho.opciones:
        return valor
    plegado = valor.casefold()
    for codigo, etiqueta in hecho.opciones.items():
        if plegado == codigo.casefold() or plegado == etiqueta.casefold():
            return codigo
    return None


def _coercionar(hecho: Hecho, item: Dict[str, Any]) -> Optional[Any]:
    """Convierte lo que devolvió el modelo al tipo del hecho · None = descartar."""
    crudo = item.get("valor")
    crudos_lista = item.get("valores")

    if hecho.tipo == "multi":
        candidatos = crudos_lista if isinstance(crudos_lista, list) else []
        if not candidatos and isinstance(crudo, str) and crudo.strip():
            candidatos = [crudo]
        validos: List[str] = []
        for candidato in candidatos:
            if not isinstance(candidato, str):
                continue
            codigo = _normalizar_opcion(hecho, candidato)
            # De-dup conservando el orden en que los mencionó.
            if codigo and codigo not in validos:
                validos.append(codigo)
        return validos or None

    if not isinstance(crudo, str) or not crudo.strip():
        return None
    valor = crudo.strip()

    if hecho.tipo == "opcion":
        return _normalizar_opcion(hecho, valor)

    if hecho.tipo == "booleano":
        plegado = valor.casefold()
        if plegado in _VERDADERO:
            return True
        if plegado in _FALSO:
            return False
        return None

    if hecho.tipo == "entero":
        try:
            return int(valor)
        except ValueError:
            return None

    return valor[:MAX_TEXTO]


def extraer(
    mensaje: str,
    recolectados: Dict[str, Any],
    *,
    session_id: str,
    db: Optional[DBSession] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Extrae los hechos del último mensaje de la persona.

    Args:
        mensaje: lo que acaba de escribir.
        recolectados: lo que ya se tiene · el modelo no lo repite salvo corrección.
        session_id: para el tracking M-001 y los logs.
        db: sesión para `record_ai_usage`. Sin ella no se registra consumo.

    Returns:
        (hechos_validos, descartados). `hechos_validos` ya viene con las claves
        y los códigos del catálogo, listo para mezclar con lo recolectado.
        `descartados` son ids que el modelo propuso y no pasaron validación —
        se devuelven para poder depurar sin leer logs.
    """
    plantilla = load_prompt(PROMPT_NAME)
    prompt = (
        plantilla.replace("{catalogo}", _catalogo_para_prompt())
        .replace("{ya_recolectado}", _recolectado_para_prompt(recolectados))
        .replace("{mensaje}", mensaje)
    )

    salida, meta = call_claude_tool(
        prompt,
        tool_name="registrar_hechos",
        tool_description=(
            "Registra los hechos que la persona dijo en su último mensaje. "
            "Solo lo que dijo — nunca lo que probablemente quiso decir."
        ),
        input_schema=_tool_schema(),
        session_id=session_id,
        feature=FEATURE,
        temperature=0.0,
        prompt_version=PROMPT_VERSION,
    )

    # M-001 · se registra también el intento fallido (tokens None), para que el
    # panel de costos vea los errores y no solo los éxitos.
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

    if salida is None:
        # Sin extracción no se inventa nada: el motor repreguntará.
        return {}, []

    validos: Dict[str, Any] = {}
    descartados: List[str] = []

    for item in salida.get("hechos") or []:
        if not isinstance(item, dict):
            continue
        hecho_id = item.get("id")
        hecho = get_hecho(hecho_id) if isinstance(hecho_id, str) else None
        if hecho is None:
            descartados.append(str(hecho_id))
            continue
        if item.get("confianza") not in CONFIANZA_ACEPTADA:
            descartados.append(hecho.id)
            continue
        valor = _coercionar(hecho, item)
        if valor is None:
            descartados.append(hecho.id)
            continue
        validos[hecho.id] = valor

    if descartados:
        logger.info(
            "bot_extractor descartó hechos",
            extra={
                "session_id": session_id,
                "descartados": descartados,
                "aceptados": list(validos.keys()),
            },
        )

    return validos, descartados
