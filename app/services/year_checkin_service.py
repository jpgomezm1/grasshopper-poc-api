"""Check-in de evolución · el mensaje con el que arranca la conversación cuando
un estudiante vuelve en un grado nuevo.

Usa `year_memory_service.get_year_comparison` para saber si hay algo que
recordar (`is_new_grade`) y, sólo en ese caso, genera un mensaje personalizado
con Claude (prompt `year_checkin`). Si no hay memoria o el grado no cambió, no
llama a la IA — no tiene sentido gastar una llamada en un mensaje que no se va
a usar.

Igual que el resto de generación conversacional del repo (`onboarding_conversacional`,
`hop_chat_service`), si Claude falla el estudiante no se queda sin mensaje: cae
a una plantilla determinista que ya usa lo mismo que le habría dicho la IA (el
detalle concreto que contó antes), sólo que sin la redacción generada.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from app.core.ai_client import call_claude_with_meta, load_prompt
from app.db.models import User
from app.services.ai_usage_service import record_ai_usage
from app.services.year_memory_service import (
    PerfilDeclarado,
    YearComparison,
    get_year_comparison,
)

logger = logging.getLogger(__name__)

PROMPT_NAME = "year_checkin"
PROMPT_VERSION = "year_checkin_v1"
FEATURE = "year_checkin"


def _grado_label(grade: Optional[int]) -> str:
    if grade is None:
        return "su etapa anterior"
    return f"grado {grade}"


def _hilo_concreto(perfil: PerfilDeclarado) -> str:
    """Un solo detalle concreto para el fallback determinista.

    Prioriza lo más personal (pasión) y baja hacia lo más genérico
    (presupuesto) sólo si no hay nada mejor — mismo criterio que le pedimos a
    la IA en el prompt ("elige UN hilo concreto").
    """
    if perfil.pasion:
        return f"nos contaste que te apasiona {perfil.pasion.rstrip('.').lower()}"
    if perfil.objetivo:
        return f"nos contaste que tu meta era {perfil.objetivo.lower()}"
    if perfil.fortalezas:
        return f"nos contaste que una de tus fortalezas es {perfil.fortalezas.rstrip('.').lower()}"
    if perfil.hobbies:
        return f"nos contaste que disfrutas {perfil.hobbies.rstrip('.').lower()}"
    return "ya hablamos de tu camino antes"


def _resumen_anterior_para_prompt(perfil: PerfilDeclarado) -> str:
    if perfil.esta_vacio():
        return "(no quedó nada cualitativo guardado de ese año)"
    lineas = []
    if perfil.pasion:
        lineas.append(f"- Le apasiona: {perfil.pasion}")
    if perfil.hobbies:
        lineas.append(f"- En su tiempo libre: {perfil.hobbies}")
    if perfil.fortalezas:
        lineas.append(f"- Sus fortalezas: {perfil.fortalezas}")
    if perfil.objetivo:
        lineas.append(f"- Buscaba: {perfil.objetivo}")
    if perfil.interes_exterior:
        lineas.append(f"- Interés en el exterior: {perfil.interes_exterior}")
    if perfil.paises:
        lineas.append(f"- Países que le llamaban la atención: {', '.join(perfil.paises)}")
    if perfil.presupuesto:
        lineas.append(f"- Presupuesto: {perfil.presupuesto}")
    return "\n".join(lineas)


def _mensaje_fallback(comparacion: YearComparison) -> str:
    """Plantilla determinista · se usa si la IA no respondió.

    No es un mensaje genérico plano: usa el mismo dato concreto que se le
    hubiera dado a la IA, así que aunque no tenga la redacción del modelo,
    sigue demostrando memoria real y no rompe la promesa del check-in.
    """
    assert comparacion.previous is not None  # sólo se llama con is_new_grade=True
    hilo = _hilo_concreto(comparacion.previous.perfil)
    grado_antes = _grado_label(comparacion.previous.grade)
    grado_hoy = _grado_label(comparacion.today.grade)
    return (
        f"¡Qué bueno tenerte de vuelta! La última vez, en {grado_antes}, "
        f"{hilo}. Ahora que vas en {grado_hoy}, cuéntame: ¿eso sigue siendo "
        f"así o ha cambiado algo?"
    )


def build_checkin_message(
    db: DBSession, user: User, comparacion: YearComparison
) -> Optional[str]:
    """Genera el mensaje de check-in · None si no aplica (no es grado nuevo).

    `comparacion` se recibe ya calculada (no se vuelve a pedir aquí) para que
    el router/servicio que orquesta ambas piezas no pague la consulta dos
    veces y para que este servicio sea trivial de probar con un
    `YearComparison` armado a mano.
    """
    if not comparacion.is_new_grade or comparacion.previous is None:
        return None

    template = load_prompt(PROMPT_NAME)
    prompt = (
        template.replace("{grado_anterior}", _grado_label(comparacion.previous.grade))
        .replace("{resumen_anterior}", _resumen_anterior_para_prompt(comparacion.previous.perfil))
        .replace("{grado_actual}", _grado_label(comparacion.today.grade))
        .replace(
            "{campos_cambiados}",
            ", ".join(comparacion.changed_fields) if comparacion.changed_fields
            else "(ninguno todavía · es la primera vez que hablan este año)",
        )
    )

    respuesta, meta = call_claude_with_meta(
        prompt,
        session_id=str(user.id),
        feature=FEATURE,
        prompt_version=PROMPT_VERSION,
        max_tokens=300,
        temperature=0.6,
    )

    record_ai_usage(
        db,
        provider="anthropic",
        model=meta.get("model") or "unknown",
        feature=FEATURE,
        tokens_input=meta.get("tokens_input"),
        tokens_output=meta.get("tokens_output"),
        latency_ms=meta.get("latency_ms"),
        user_id=user.id,
    )

    if not respuesta:
        logger.warning(
            "year_checkin: la IA no respondió · usando plantilla determinista",
            extra={"user_id": str(user.id), "error_kind": meta.get("error_kind")},
        )
        return _mensaje_fallback(comparacion)

    return respuesta.strip()
