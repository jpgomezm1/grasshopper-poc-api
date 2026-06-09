"""Chat real de Hop · Fase C pieza C (B-049) · 2026-06-09.

Hasta ahora el FE servía respuestas enlatadas client-side. Este servicio
arma el contexto real del estudiante y llama a Claude:

  - Perfil consolidado CACHEADO (`consolidation_service.get_cached_profile`)
    · NUNCA dispara generación síncrona dentro del chat. Sin cache válido,
    Hop invita a completar journey/tests.
  - Constraints declarados del User (presupuesto · países · inglés CEFR).
  - Oferta opcional (`Program`) por UUID, slug o program_id. Campos
    financieros NULL se presentan como "a confirmar" (migración 048).
  - Historial capado server-side a los últimos 12 turnos.
  - Tracking M-001 vía `record_ai_usage` (best-effort, en éxito y error).
"""
from __future__ import annotations

import logging
import uuid as uuid_mod
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.core.ai_client import call_claude_chat, load_prompt
from app.db.models import Program, User
from app.schemas.hop_chat import HopChatTurn
from app.services.ai_usage_service import record_ai_usage
from app.services.consolidation_service import get_cached_profile

logger = logging.getLogger(__name__)
settings = get_settings()

PROMPT_NAME = "hop_chat"
PROMPT_VERSION = "hop_chat_v1"

# Cap server-side del historial · el contrato acepta hasta 20 turnos pero
# solo los últimos 12 viajan a la IA (costo/contexto).
MAX_HISTORY_TURNS = 12

NO_PROFILE_BLOCK = (
    "(El estudiante aún no tiene perfil consolidado — invítalo a completar "
    "su journey y tests)"
)
NO_OFERTA_BLOCK = "(El estudiante no está consultando ninguna oferta específica)"
A_CONFIRMAR = "a confirmar"


# ---------------------------------------------------------------------------
# Bloques de contexto
# ---------------------------------------------------------------------------


def _build_profile_block(db: DBSession, user: User) -> Tuple[str, bool]:
    """Perfil consolidado cacheado · (texto, profile_used).

    Usa SOLO el cache (sin regeneración síncrona). Un cache invalidado o
    vacío cuenta como "sin perfil".
    """
    row = get_cached_profile(db, user.id)
    if row is None or row.invalidated_at is not None or not row.profile_data:
        return NO_PROFILE_BLOCK, False

    data = row.profile_data if isinstance(row.profile_data, dict) else {}
    if not data:
        return NO_PROFILE_BLOCK, False

    lines: List[str] = []
    summary = data.get("summary_narrative")
    if summary:
        lines.append(f"Resumen: {summary}")
    for label, key in (
        ("Fortalezas", "strengths"),
        ("Intereses", "interests"),
        ("Valores", "values"),
        ("Caminos profesionales sugeridos", "suggested_career_paths"),
    ):
        items = data.get(key) or []
        if items:
            lines.append(f"{label}: {', '.join(str(i) for i in items)}")
    for label, key in (
        ("Estilo de aprendizaje", "learning_style"),
        ("Estilo de trabajo", "work_style"),
    ):
        value = data.get(key)
        if value:
            lines.append(f"{label}: {value}")

    if not lines:
        return NO_PROFILE_BLOCK, False
    return "\n".join(lines), True


def _build_constraints_block(user: User) -> str:
    """Constraints declarados en el User · siempre presente (con vacíos explícitos)."""
    budget_parts: List[str] = []
    if user.budget_band:
        budget_parts.append(f"banda {user.budget_band}")
    if user.budget_max_usd:
        budget_parts.append(f"tope {user.budget_max_usd} USD")
    budget = " · ".join(budget_parts) if budget_parts else "(sin información)"

    countries = list(user.preferred_countries or [])
    countries_txt = ", ".join(countries) if countries else "(sin información)"

    english = user.english_cefr_level or "(sin información)"

    return (
        f"Presupuesto declarado: {budget}\n"
        f"Países preferidos: {countries_txt}\n"
        f"Nivel de inglés (CEFR): {english}"
    )


def _find_program(db: DBSession, oferta_id: str) -> Optional[Program]:
    """Busca por UUID primero; fallback por slug y por program_id."""
    try:
        as_uuid = uuid_mod.UUID(str(oferta_id))
    except (ValueError, AttributeError, TypeError):
        as_uuid = None

    if as_uuid is not None:
        program = db.query(Program).filter(Program.id == as_uuid).first()
        if program is not None:
            return program

    program = db.query(Program).filter(Program.slug == oferta_id).first()
    if program is not None:
        return program

    return db.query(Program).filter(Program.program_id == oferta_id).first()


def _build_oferta_block(db: DBSession, oferta_id: Optional[str]) -> Tuple[str, bool]:
    """Bloque slim de la oferta · (texto, oferta_context_used)."""
    if not oferta_id:
        return NO_OFERTA_BLOCK, False

    program = _find_program(db, oferta_id)
    if program is None:
        logger.info("hop_chat oferta_id not found", extra={"oferta_id": oferta_id})
        return NO_OFERTA_BLOCK, False

    place = program.country or ""
    if program.city:
        place = f"{program.city}, {place}" if place else program.city

    if program.duration_months:
        duration = f"{program.duration_months} meses"
    else:
        duration = A_CONFIRMAR

    if program.cost_total:
        cost = f"{program.cost_total} {program.currency or 'USD'}"
    else:
        cost = A_CONFIRMAR

    language = program.language_requirement or A_CONFIRMAR

    if program.scholarships_for_latam is True:
        beca = "sí"
    elif program.scholarships_for_latam is False:
        beca = "no"
    else:
        beca = "sin curar"

    lines = [
        f"Programa: {program.name}",
        f"Institución: {program.institution}",
        f"Ubicación: {place or A_CONFIRMAR}",
        f"Tipo: {program.type}",
        f"Duración: {duration}",
        f"Costo total: {cost}",
        f"Requisito de idioma: {language}",
        f"Beca para estudiantes LatAm: {beca}",
    ]
    highlights = program.highlights or []
    if highlights:
        lines.append(
            "Highlights: " + ", ".join(str(h) for h in highlights if h)
        )

    return "\n".join(lines), True


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def run_hop_chat(
    db: DBSession,
    user: User,
    message: str,
    history: List[HopChatTurn],
    oferta_id: Optional[str] = None,
) -> Tuple[Optional[str], bool, bool]:
    """Ejecuta un turno del chat de Hop.

    Returns:
        (reply, profile_used, oferta_context_used). ``reply`` es None cuando
        la IA no respondió (el router lo traduce a 503 con el detail del
        contrato).
    """
    profile_block, profile_used = _build_profile_block(db, user)
    constraints_block = _build_constraints_block(user)
    oferta_block, oferta_used = _build_oferta_block(db, oferta_id)

    template = load_prompt(PROMPT_NAME)
    system = (
        template.replace("{profile_block}", profile_block)
        .replace("{constraints_block}", constraints_block)
        .replace("{oferta_block}", oferta_block)
    )

    # Cap server-side ANTES de armar messages (últimos N turnos).
    trimmed = list(history or [])[-MAX_HISTORY_TURNS:]
    messages = [{"role": t.role, "content": t.content} for t in trimmed]
    messages.append({"role": "user", "content": message})

    reply, metadata = call_claude_chat(
        messages,
        system=system,
        session_id=str(user.id),
        feature="hop_chat",
    )

    # Tracking M-001 · best-effort (record_ai_usage nunca lanza). Se registra
    # también el intento fallido (tokens None) para que el panel vea errores.
    record_ai_usage(
        db,
        provider="anthropic",
        model=metadata.get("model") or settings.ai_model,
        feature="hop_chat",
        tokens_input=metadata.get("tokens_input"),
        tokens_output=metadata.get("tokens_output"),
        latency_ms=metadata.get("latency_ms"),
        user_id=user.id,
    )

    return reply, profile_used, oferta_used
