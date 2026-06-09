"""Schemas del chat real de Hop · Fase C pieza C (B-049) · 2026-06-09.

Contrato fijado con el frontend (NO cambiar sin coordinar):

POST /api/v1/hop/chat
  Request : {"message": str (1..2000),
             "history": [{"role": "user"|"assistant", "content": str ≤4000}]
                        (default [] · máx 20 items),
             "oferta_id": str opcional}
  Response: {"reply": str, "profile_used": bool, "oferta_context_used": bool}
  503     : detail = "Hop no puede responder en este momento. Intenta de
             nuevo en unos minutos."
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class HopChatTurn(BaseModel):
    """Un turno previo de la conversación (lo manda el FE tal cual)."""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class HopChatRequest(BaseModel):
    """Request del chat de Hop."""

    message: str = Field(..., min_length=1, max_length=2000)
    history: List[HopChatTurn] = Field(default_factory=list, max_length=20)
    oferta_id: Optional[str] = Field(
        default=None,
        max_length=255,
        description="UUID, slug o program_id de un programa del catálogo "
        "para anclar la respuesta a esa oferta.",
    )


class HopChatResponse(BaseModel):
    """Response del chat de Hop."""

    reply: str
    profile_used: bool = Field(
        ..., description="True si el perfil consolidado cacheado alimentó el prompt."
    )
    oferta_context_used: bool = Field(
        ..., description="True si se encontró la oferta pedida y se inyectó al prompt."
    )
