"""RM-1 · Redacta el mensaje de acompañamiento.

Separado de `outreach_service` a propósito: ese decide **a quién** se le escribe
y **por qué** (determinista, auditable); este decide **cómo se dice** (IA, con
respaldo).

## El respaldo no es un detalle

Si el modelo falla, se manda la plantilla determinista del motivo. Es el mismo
criterio de D-005 del POC, y aquí importa más que en otros sitios: un correo que
no sale porque la IA se cayó es un estudiante que no vuelve. La plantilla dice
menos, pero dice algo cierto.

Se registra en `OutreachLog.es_plantilla` cuál de los dos salió, para poder
medir después si vale la pena la llamada al modelo.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from app.core.ai_client import call_claude_tool, load_prompt
from app.services.outreach_service import Motivo

logger = logging.getLogger(__name__)


# Tope duro. El modelo tiene instrucción de 400 caracteres; esto es la red por
# si la ignora — un correo de acompañamiento de 2.000 caracteres no se lee.
MAX_CUERPO = 600
MAX_CTA = 40


@dataclass(frozen=True)
class Mensaje:
    cuerpo: str
    cta: str
    es_plantilla: bool


# Respaldo determinista por motivo · lo que se manda si la IA falla.
# Redactado con las mismas reglas del prompt: una sola cosa, sin urgencia falsa,
# sin inventar nada del estudiante.
_PLANTILLAS = {
    "sin_tests": Mensaje(
        cuerpo=(
            "Tu perfil está a un test de distancia. Es lo que más cambia lo que "
            "podemos decirte sobre a qué te podrías dedicar, y toma pocos minutos."
        ),
        cta="Hacer un test",
        es_plantilla=True,
    ),
    "journey_a_medias": Mensaje(
        cuerpo=(
            "Dejaste tu recorrido a medias y tus respuestas siguen guardadas. "
            "Puedes retomarlo justo donde lo dejaste."
        ),
        cta="Retomar",
        es_plantilla=True,
    ),
    "sin_rutas": Mensaje(
        cuerpo=(
            "Ya tienes lo necesario para que te generemos tus rutas "
            "profesionales. Es el paso que junta todo lo que respondiste."
        ),
        cta="Ver mis rutas",
        es_plantilla=True,
    ),
    "ingles_pendiente": Mensaje(
        cuerpo=(
            "El nivel de inglés define a qué programas puedes aplicar. Si quieres, "
            "presenta el examen y ajustamos lo que te recomendamos."
        ),
        cta="Presentar el examen",
        es_plantilla=True,
    ),
}

_PLANTILLA_GENERICA = Mensaje(
    cuerpo=(
        "Pasamos a saludarte y a recordarte que tu proceso sigue abierto cuando "
        "quieras retomarlo."
    ),
    cta="Entrar",
    es_plantilla=True,
)


def _esquema() -> dict:
    """Estable entre llamadas · las definiciones de tools se renderizan en la
    posición 0 del prompt y un esquema que cambia rompe el caché."""
    return {
        "type": "object",
        "properties": {
            "cuerpo": {
                "type": "string",
                "description": "El mensaje · 2-3 frases · 80-400 caracteres",
            },
            "cta": {
                "type": "string",
                "description": "Texto del botón · máximo 30 caracteres",
            },
        },
        "required": ["cuerpo", "cta"],
    }


def plantilla_de_respaldo(motivo: Motivo) -> Mensaje:
    """El texto determinista de este motivo · publica porque la consume el
    preview del panel, no solo este modulo."""
    return _PLANTILLAS.get(motivo.clave, _PLANTILLA_GENERICA)


def redactar(
    motivo: Motivo,
    *,
    nombre: Optional[str],
    user_id: str,
    db: Optional[DBSession] = None,
) -> Mensaje:
    """Devuelve el mensaje · nunca lanza.

    Cualquier fallo cae en la plantilla del motivo: un correo que no sale porque
    el modelo se cayó es un estudiante que no vuelve.
    """
    primer_nombre = (nombre or "").strip().split(" ")[0] if nombre else "Hola"
    try:
        plantilla = load_prompt("outreach_message")
        prompt = plantilla.format(
            nombre=primer_nombre or "—",
            contexto=motivo.contexto,
        )
        datos, _meta = call_claude_tool(
            prompt,
            tool_name="escribir_mensaje",
            tool_description="Escribe el mensaje de acompañamiento para el estudiante.",
            input_schema=_esquema(),
            session_id=user_id,
            feature="outreach_message",
            max_tokens=500,
            temperature=0.4,  # algo de variedad · si no, todos leen igual
        )
    except Exception as exc:  # pragma: no cover · la red no se prueba aquí
        logger.warning("RM-1 · redacción falló, va la plantilla · %s", exc)
        return plantilla_de_respaldo(motivo)

    if not datos:
        return plantilla_de_respaldo(motivo)

    cuerpo = str(datos.get("cuerpo") or "").strip()
    cta = str(datos.get("cta") or "").strip()
    # Un cuerpo vacío o de una palabra no es un mensaje. Mejor la plantilla, que
    # al menos dice algo cierto.
    if len(cuerpo) < 40:
        return plantilla_de_respaldo(motivo)

    return Mensaje(
        cuerpo=cuerpo[:MAX_CUERPO],
        cta=(cta or plantilla_de_respaldo(motivo).cta)[:MAX_CTA],
        es_plantilla=False,
    )
