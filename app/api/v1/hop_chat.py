"""Chat real de Hop · Fase C pieza C (B-049) · 2026-06-09.

POST /api/v1/hop/chat — reemplaza las respuestas enlatadas client-side del
FE por una llamada real a Claude con el contexto del estudiante (perfil
consolidado cacheado + constraints + oferta opcional).

Auth: cualquier usuario autenticado (pensado para student).
Rate limit: 20/minute + 200/day por client-key (buckets separados vía scope).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.core.rate_limiter import rate_limit
from app.db.database import get_db
from app.db.models import User
from app.schemas.hop_chat import HopChatRequest, HopChatResponse
from app.services.hop_chat_service import run_hop_chat

router = APIRouter(prefix="/hop", tags=["Hop · chat IA"])

# Detail del contrato cuando la IA está caída (NO cambiar · el FE lo muestra).
AI_DOWN_DETAIL = "Hop no puede responder en este momento. Intenta de nuevo en unos minutos."


@router.post(
    "/chat",
    response_model=HopChatResponse,
    summary="B-049 · chat real de Hop (Claude) con contexto del estudiante",
    dependencies=[
        Depends(rate_limit("20/minute", scope="hop_chat_minute")),
        Depends(rate_limit("200/day", scope="hop_chat_day")),
    ],
)
def hop_chat(
    payload: HopChatRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HopChatResponse:
    reply, profile_used, oferta_context_used = run_hop_chat(
        db,
        current_user,
        message=payload.message,
        history=payload.history,
        oferta_id=payload.oferta_id,
    )

    if reply is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=AI_DOWN_DETAIL,
        )

    return HopChatResponse(
        reply=reply,
        profile_used=profile_used,
        oferta_context_used=oferta_context_used,
    )
