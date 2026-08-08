"""Perfilador comercial · el bot que reemplaza el Typeform de la web de la agencia.

Tres endpoints **públicos** (`/start`, `/turn`) y uno para el equipo (`/leads`).

⚠️ **Endpoints públicos que llaman a Claude = vector de gasto.** Cualquiera con
la URL puede quemar tokens. Tres topes, no uno:

  - rate limit por IP (mismo patrón que `lead_profile.py`),
  - `MAX_TURNOS` por conversación · una conversación que no cierra en 40 turnos
    no es una persona interesada,
  - `MAX_LARGO_MENSAJE` · un mensaje de 50KB infla el prompt de cada turno.

Sin esos topes, esto es una factura de Anthropic esperando a que alguien
encuentre la URL.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.config import get_settings
from app.db.database import get_db
from app.db.models import BotConversation, User, UserRole
from app.services import bot_lead_scoring
from app.services.conversation_engine import listo_para_cerrar, responder

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bot", tags=["Bot Perfilador"])

# Una conversación real cierra en 8-12 turnos. 40 es holgado y a la vez corta
# cualquier bucle automatizado.
MAX_TURNOS = 40
MAX_LARGO_MENSAJE = 2000

# Estático a propósito: el saludo no necesita una llamada de IA. Ahorra latencia
# en el primer contacto, que es donde más se abandona.
SALUDO = (
    "¡Hola! Soy el asistente de GrassHopper. Cuéntame qué estás buscando: "
    "¿un idioma, un pregrado, un posgrado, o todavía lo estás pensando?"
)


def _rate_limit_bot(request: Request) -> None:
    from app.core.rate_limiter import rate_limit

    return rate_limit(get_settings().rate_limit_bot_turn, scope="bot_turn")(request)


def _require_equipo(user: User) -> None:
    """La bandeja es del equipo comercial · nunca del estudiante."""
    if user.role not in (
        UserRole.GH_COMMERCIAL,
        UserRole.GH_ADVISOR,
        UserRole.SUPER_ADMIN,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · gh team only",
        )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class StartRequest(BaseModel):
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


class StartResponse(BaseModel):
    conversation_id: UUID
    message: str


class TurnRequest(BaseModel):
    conversation_id: UUID
    message: str = Field(min_length=1, max_length=MAX_LARGO_MENSAJE)


class TurnResponse(BaseModel):
    message: str
    completed: bool
    wants_orientation: bool


class LeadItem(BaseModel):
    id: UUID
    created_at: datetime
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    score: Optional[int]
    band: Optional[str]
    route: Optional[str]
    alarms: List[str]
    wants_orientation: bool
    is_completed: bool
    hechos: Dict[str, Any]


# ---------------------------------------------------------------------------
# Endpoints públicos
# ---------------------------------------------------------------------------


@router.post("/start", response_model=StartResponse, dependencies=[Depends(_rate_limit_bot)])
def start(request: StartRequest, db: DBSession = Depends(get_db)) -> StartResponse:
    """Abre una conversación anónima. No requiere cuenta."""
    conversacion = BotConversation(
        hechos={},
        transcript=[{"role": "assistant", "content": SALUDO}],
        utm_source=request.utm_source,
        utm_medium=request.utm_medium,
        utm_campaign=request.utm_campaign,
    )
    db.add(conversacion)
    db.commit()
    db.refresh(conversacion)
    return StartResponse(conversation_id=conversacion.id, message=SALUDO)


@router.post("/turn", response_model=TurnResponse, dependencies=[Depends(_rate_limit_bot)])
def turn(request: TurnRequest, db: DBSession = Depends(get_db)) -> TurnResponse:
    """Un turno de conversación · extrae, responde y vuelve a puntuar."""
    conversacion = (
        db.query(BotConversation).filter(BotConversation.id == request.conversation_id).first()
    )
    if conversacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation_not_found")

    historial = list(conversacion.transcript or [])
    if len(historial) >= MAX_TURNOS * 2:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="conversation_too_long",
        )

    respuesta, hechos, _descartados = responder(
        request.message,
        historial,
        dict(conversacion.hechos or {}),
        session_id=str(conversacion.id),
        db=db,
    )

    # El veredicto se recalcula en CADA turno, no solo al cerrar: mucha gente
    # abandona a mitad, y un lead a medias con score sigue sirviéndole al equipo
    # comercial. Sin esto, abandonar = desaparecer.
    veredicto = bot_lead_scoring.evaluar(hechos)
    completado = listo_para_cerrar(hechos)

    # Dicts/listas NUEVOS · las columnas JSON sin MutableDict no rastrean
    # mutaciones in-place (mismo motivo que `seed_session_from_onboarding`).
    conversacion.transcript = historial + [
        {"role": "user", "content": request.message},
        {"role": "assistant", "content": respuesta},
    ]
    conversacion.hechos = hechos
    conversacion.name = hechos.get("nombre") or conversacion.name
    conversacion.email = hechos.get("correo") or conversacion.email
    conversacion.phone = hechos.get("celular") or conversacion.phone
    conversacion.score = veredicto.score
    conversacion.band = veredicto.banda
    conversacion.route = veredicto.ruta
    conversacion.alarms = veredicto.alarmas
    conversacion.score_rationale = veredicto.motivos
    conversacion.wants_orientation = bot_lead_scoring.quiere_orientacion(hechos)
    conversacion.is_completed = completado
    db.commit()

    return TurnResponse(
        message=respuesta,
        completed=completado,
        wants_orientation=conversacion.wants_orientation,
    )


# ---------------------------------------------------------------------------
# Bandeja del equipo comercial
# ---------------------------------------------------------------------------


@router.get("/leads", response_model=List[LeadItem])
def leads(
    route: Optional[str] = Query(None, description="asesor · telemercadeo · descartar"),
    only_completed: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[LeadItem]:
    """Los leads que produjo el bot · lo más nuevo arriba.

    Existe porque `lead_profiles` demostró que capturar sin leer es lo mismo que
    no capturar: esa tabla se escribe desde un solo sitio y no la consulta nadie.
    """
    _require_equipo(current_user)

    consulta = db.query(BotConversation)
    if route:
        consulta = consulta.filter(BotConversation.route == route)
    if only_completed:
        consulta = consulta.filter(BotConversation.is_completed.is_(True))

    filas = consulta.order_by(BotConversation.created_at.desc()).limit(limit).all()
    return [
        LeadItem(
            id=fila.id,
            created_at=fila.created_at,
            name=fila.name,
            email=fila.email,
            phone=fila.phone,
            score=fila.score,
            band=fila.band,
            route=fila.route,
            alarms=list(fila.alarms or []),
            wants_orientation=bool(fila.wants_orientation),
            is_completed=bool(fila.is_completed),
            hechos=dict(fila.hechos or {}),
        )
        for fila in filas
    ]
