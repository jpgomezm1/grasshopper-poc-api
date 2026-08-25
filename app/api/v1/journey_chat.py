"""El Journey como chat continuo (`/journey-chat`) · JP, reunión 24-08.

    "en Journey yo lo que me imagino es que sea como un chat continuo que le
     vaya haciendo preguntas al usuario para irlo perfilando"

Endpoints nuevos, sobre una sesión YA creada (`POST /sessions`). No tocan el
wizard de siempre (`GET/POST /sessions/{id}...`): mientras el flag
`FLAG` esté apagado para el dueño de la sesión, `POST .../turno` devuelve
409 y nada de esto existe para quien esté a mitad del wizard.

Ver `app.services.journey_chat_service` para el porqué de esta capa (y por
qué no se amplió `journey_interprete` en su lugar).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.core.access import assert_session_access
from app.core.rate_limiter import rate_limit
from app.core.state_machine import get_next_step, get_step
from app.data import journey_chat_hechos as catalogo
from app.db.database import get_db
from app.db.models import JourneyStage as DBJourneyStage, Session as JourneySession, User
from app.services import journey_chat_service as chat
from app.services import parental_consent_service
from app.services.feature_flags_service import is_feature_enabled
from app.services.journey_service import build_journey_response, contexto_de_navegacion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/journey-chat", tags=["Journey · chat continuo"])

# Flag propio · DISTINTO del `journey_conversacional` que usa
# `journey_interprete`. Son dos mecanismos distintos (ver el docstring de
# `journey_chat_service`) y comparten flag los mezclaría en el rollout de
# uno y de otro sin poder apagarlos por separado.
FLAG = "journey_chat_continuo"


class Turno(BaseModel):
    role: str
    content: str


class TurnoRequest(BaseModel):
    mensaje: str = Field(..., min_length=1, max_length=4000)
    historial: List[Turno] = Field(default_factory=list)


class VideoOut(BaseModel):
    id: str
    url: str
    duracion_segundos: int
    tema: str


class InicioResponse(BaseModel):
    respuesta: str
    recolectado: Dict[str, Any]
    listo: bool


class TurnoResponse(BaseModel):
    respuesta: str
    # Lo que se sabe hasta ahora de este tramo · el front lo puede mostrar
    # como un resumen vivo (igual que `/onboarding-chat/turno`).
    recolectado: Dict[str, Any]
    faltan: int
    listo: bool
    video: Optional[VideoOut] = None
    # Cuando `listo=True` la conversación ya entregó la sesión al motor de
    # síntesis/rutas de siempre: el front puede seguir de una con esto, sin
    # pedir aparte `GET /sessions/{id}`.
    journey: Optional[Dict[str, Any]] = None


def _owner(db: DBSession, session: JourneySession) -> Optional[User]:
    if session.user_id is None:
        return None
    return db.query(User).filter(User.id == session.user_id).first()


def _gate_subject(session: JourneySession, current_user: User, db: DBSession) -> User:
    """A quién se le aplica el gate de menores · el DUEÑO de la sesión, no el
    caller (mismo criterio que `sessions.submit_event`, auditoría R5: un
    staff con acceso no debe poder avanzar el journey de un menor sin
    consentimiento parental)."""
    if session.user_id is not None and session.user_id != current_user.id:
        owner = _owner(db, session)
        if owner is not None:
            return owner
    return current_user


def _hechos_de_la_sesion(session: JourneySession) -> Dict[str, Any]:
    """Sólo las claves del catálogo del chat, leídas de `Session.answers`. El
    resto de `answers` (rutas elegidas, respuestas de pasos que este chat no
    toca) no se filtra a la conversación."""
    answers = session.answers or {}
    return {
        h.id: answers[h.id]
        for h in catalogo.HECHOS
        if answers.get(h.id) not in (None, "", [], {})
    }


def _flag_o_409(db: DBSession, session: JourneySession) -> None:
    if not is_feature_enabled(db, FLAG, _owner(db, session)):
        raise HTTPException(status_code=409, detail="journey_chat_no_habilitado")


def _ruta_conocida(onboarding: Optional[dict]) -> Optional[str]:
    """Una de las 5 rutas de la malla completa, si ya se sabe · sólo para
    elegir video por ruta. Import diferido y de sólo-lectura: no se toca
    `onboarding_hechos.py`, sólo se usa su función pura `ruta()`."""
    if not onboarding:
        return None
    from app.data.onboarding_hechos import ruta as _ruta

    return _ruta(onboarding)


@router.get("/{session_id}/inicio", response_model=InicioResponse)
def inicio(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """El primer mensaje, y lo que ya se sabe de este tramo (retoma una
    sesión que ya venía con algo sembrado del onboarding, B-02)."""
    session = assert_session_access(session_id, current_user, db)
    _flag_o_409(db, session)

    owner = _owner(db, session)
    onboarding = owner.onboarding_answers if owner else None
    contexto = contexto_de_navegacion(db, session)
    recolectados = _hechos_de_la_sesion(session)

    return InicioResponse(
        respuesta=chat.primer_mensaje(),
        recolectado=recolectados,
        listo=catalogo.listo_para_cerrar(recolectados, onboarding, contexto),
    )


@router.post(
    "/{session_id}/turno",
    response_model=TurnoResponse,
    dependencies=[
        Depends(rate_limit("20/minute", scope="journey_chat_minute")),
        Depends(rate_limit("200/day", scope="journey_chat_day")),
    ],
)
def turno(
    session_id: UUID,
    cuerpo: TurnoRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Un turno del chat continuo · extrae, responde, guarda en cada turno.

    Al llegar a `listo=True`, la sesión se entrega al motor de siempre
    caminando la cadena real de `state_machine` desde `geoPreference` (el
    último hecho de este catálogo) — así respeta cualquier `skip_if` real de
    los pasos siguientes (p. ej. `testInvitation` si su flag está encendido)
    en vez de asumir a mano que el próximo paso es `synthesis`.
    """
    session = assert_session_access(session_id, current_user, db)
    _flag_o_409(db, session)

    gate_subject = _gate_subject(session, current_user, db)
    if parental_consent_service.needs_parental_consent(gate_subject):
        raise HTTPException(status_code=403, detail="minor_parental_consent_required")

    owner = _owner(db, session)
    onboarding = owner.onboarding_answers if owner else None
    contexto = contexto_de_navegacion(db, session)
    previos = _hechos_de_la_sesion(session)

    respuesta, actualizados, listo, video = chat.responder(
        cuerpo.mensaje,
        [t.model_dump() for t in cuerpo.historial],
        previos,
        session_id=str(session.id),
        db=db,
        onboarding=onboarding,
        contexto=contexto,
        ruta=_ruta_conocida(onboarding),
    )

    # Se guarda EN CADA TURNO, no sólo al cerrar — igual que
    # `/onboarding-chat/turno`: perder una conversación de varios mensajes
    # porque se cerró la pestaña sería peor que el wizard de botones.
    answers = dict(session.answers or {})
    nuevas_claves = {k: v for k, v in actualizados.items() if answers.get(k) != v}
    if nuevas_claves:
        answers.update(nuevas_claves)
        session.answers = answers
        completados = list(session.completed_steps or [])
        for k in nuevas_claves:
            if k not in completados:
                completados.append(k)
        session.completed_steps = completados

    if listo:
        siguiente = get_next_step("geoPreference", answers, onboarding, contexto)
        if siguiente:
            session.current_step = siguiente
            paso = get_step(siguiente)
            if paso:
                session.current_stage = DBJourneyStage(paso.stage.value)

    try:
        db.commit()
    except Exception:  # pragma: no cover · guardar no puede tumbar el turno
        logger.warning(
            "no se pudo persistir el turno del journey chat",
            exc_info=True, extra={"session_id": str(session.id)},
        )
        db.rollback()
    else:
        db.refresh(session)

    journey_payload = None
    if listo:
        journey_payload = build_journey_response(db, session).model_dump(mode="json")

    video_out = None
    if video is not None:
        video_out = VideoOut(
            id=video.id, url=video.url,
            duracion_segundos=video.duracion_segundos, tema=video.tema,
        )

    return TurnoResponse(
        respuesta=respuesta,
        recolectado=actualizados,
        faltan=len(catalogo.faltantes(actualizados, onboarding, contexto)),
        listo=listo,
        video=video_out,
        journey=journey_payload,
    )
