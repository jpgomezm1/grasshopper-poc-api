"""Entender la convocatoria que el estudiante pegó · paso 1 de la adaptación.

El estudiante pega el texto de una vacante, un programa, una beca o una práctica,
y esto lo convierte en una estructura: qué exige, qué suma, qué habilidades pide.
Después `cv_tailor_service` compara esa estructura contra su hoja de vida.

Está partido en dos servicios y no en uno porque son dos preguntas distintas —
*"¿qué pide esto?"* y *"¿cómo le va a ella con esto?"*— y la primera no depende
del estudiante. La respuesta se guarda en `cv_targets.parsed`.

**Copia el molde de `linkedin_import_service`** en lo que importa: límites de
tamaño sobre el texto pegado, `temperature=0` porque estructurar no es escribir,
normalización que recorta cada campo, y **nunca escribe nada**. La diferencia es
que aquí se usa `call_claude_tool` (tool use forzado): la forma la garantiza el
SDK, así que no hay que parsear JSON a mano ni tolerar envoltorios.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Una convocatoria pegada entera rara vez pasa de unos miles de caracteres. El
# tope evita que alguien pegue un pliego de 80 páginas y dispare el costo.
MAX_CHARS = 15000
MIN_CHARS = 120

TIPOS_VALIDOS = ("job", "program", "scholarship", "internship", "other")


class CVTargetError(RuntimeError):
    """No se pudo interpretar la convocatoria que pegó la persona."""


# El esquema que el modelo está OBLIGADO a llenar (`tool_choice` forzado).
ESQUEMA_CONVOCATORIA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": list(TIPOS_VALIDOS),
            "description": "Qué tipo de convocatoria es.",
        },
        "title": {"type": "string", "description": "Cargo, programa o beca."},
        "organization": {"type": "string", "description": "Quién convoca."},
        "resumen": {"type": "string", "description": "1-2 frases en lenguaje sencillo."},
        "requisitos": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Lo que exige de forma explícita (excluyente).",
        },
        "deseables": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Lo que suma pero no es obligatorio.",
        },
        "habilidades": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Competencias que se piden, nombradas sueltas.",
        },
        "idiomas": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Idiomas exigidos, con nivel si lo menciona.",
        },
        "fechas": {"type": "string", "description": "Plazos o fechas de cierre."},
    },
    "required": ["kind"],
}


def _texto(valor: Any, limite: int) -> Optional[str]:
    if valor is None:
        return None
    limpio = str(valor).strip()
    return limpio[:limite] if limpio else None


def _lista(valor: Any, max_items: int, limite: int) -> List[str]:
    if not isinstance(valor, list):
        return []
    salida: List[str] = []
    for item in valor:
        t = _texto(item, limite)
        if t:
            salida.append(t)
    return salida[:max_items]


def normalizar(bruto: Dict[str, Any]) -> Dict[str, Any]:
    """Acota lo que devolvió el modelo · nunca se confía en crudo.

    El tool use garantiza la FORMA (que `requisitos` sea una lista de strings),
    no el TAMAÑO. Sin esto, un modelo verboso puede devolver 40 requisitos de un
    párrafo cada uno y eso termina en la base y en la pantalla.
    """
    kind = (_texto(bruto.get("kind"), 30) or "other").lower()
    if kind not in TIPOS_VALIDOS:
        kind = "other"

    return {
        "kind": kind,
        "title": _texto(bruto.get("title"), 200),
        "organization": _texto(bruto.get("organization"), 160),
        "resumen": _texto(bruto.get("resumen"), 600),
        "requisitos": _lista(bruto.get("requisitos"), 10, 220),
        "deseables": _lista(bruto.get("deseables"), 8, 220),
        "habilidades": _lista(bruto.get("habilidades"), 12, 100),
        "idiomas": _lista(bruto.get("idiomas"), 4, 80),
        "fechas": _texto(bruto.get("fechas"), 200),
    }


def parsear(texto: str, *, session_id: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Estructura la convocatoria. Devuelve ``(parsed, metadata_de_ia)``.

    La metadata alimenta el tracking de consumo (`ai_usage_logs`), igual que en
    `linkedin_import_service`: este servicio no escribe en la base, así que
    tampoco registra el consumo — lo hace quien lo llama, que sí tiene sesión.
    """
    texto = (texto or "").strip()
    if len(texto) < MIN_CHARS:
        raise CVTargetError(
            "Pega un poco más de la convocatoria: con tan poco texto no puedo "
            "saber qué están pidiendo."
        )
    if len(texto) > MAX_CHARS:
        texto = texto[:MAX_CHARS]

    # Import diferido, igual que el resto de servicios de IA de este repo: deja
    # el módulo importable sin credenciales y no penaliza el arranque.
    from app.core.ai_client import call_claude_tool, load_prompt

    prompt = load_prompt("cv_target_parse").format(convocatoria=texto)

    datos, meta = call_claude_tool(
        prompt,
        tool_name="registrar_convocatoria",
        tool_description=(
            "Registra de forma estructurada qué pide una convocatoria "
            "(vacante, programa, beca o práctica)."
        ),
        input_schema=ESQUEMA_CONVOCATORIA,
        session_id=session_id,
        feature="cv_target_parse",
        max_tokens=2000,
        temperature=0,
    )

    if not datos:
        raise CVTargetError(
            "No pude leer la convocatoria. Intenta pegar el texto completo del aviso."
        )

    return normalizar(datos), meta
