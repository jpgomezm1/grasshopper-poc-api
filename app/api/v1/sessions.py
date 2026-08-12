"""Session API endpoints."""

import logging
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import User, Session
from app.schemas.session import (
    SessionCreate,
    SessionEventCreate,
    SessionResponse,
    JourneyResponse,
    JourneyInterpretacionCreate,
    JourneyInterpretacionResponse,
)
from app.services.journey_service import (
    create_session,
    get_session,
    build_journey_response,
    process_event,
    seed_session_from_onboarding,
)
from app.services import bitrix_sync_service
from app.services import parental_consent_service
from app.api.v1.auth import get_current_user, get_optional_current_user
from app.core.access import assert_session_access
from app.core.rate_limiter import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=JourneyResponse)
def create_new_session(
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_optional_current_user),
):
    """Create a new journey session.

    Para un usuario autenticado devolvemos su sesión VINCULADA (get-or-create),
    sembrada con los datos del onboarding (B-02), en vez de crear una sesión
    anónima nueva. Así el Journey siempre opera sobre una sesión con dueño
    —evita el 403 de `assert_session_access` si el front llega aquí antes de
    hidratar `gh_session_id`— y no se fragmenta en varias sesiones. La siembra
    solo rellena lo vacío, así que no pisa un Journey ya en progreso.

    Creación anónima: se permite para empezar antes de registrarse; el avance
    del Journey (`submit_event`) exige auth, así que la sesión se vincula al
    autenticarse. Auditoría R5: con rate limit por IP (antes acumulaba filas
    huérfanas sin tope).
    """
    if current_user is not None:
        # Auditoría R5 · orden determinista: si un race dejó sesiones
        # duplicadas, TODOS los endpoints usan la más antigua (la canónica).
        session = (
            db.query(Session)
            .filter(Session.user_id == current_user.id)
            .order_by(Session.created_at.asc())
            .first()
        )
        if session is None:
            session = Session(user_id=current_user.id)
            db.add(session)
        seed_session_from_onboarding(session, current_user.onboarding_answers)
        db.commit()
        db.refresh(session)
        return build_journey_response(db, session)

    # Rate limit por IP SOLO para creación anónima (auditoría R5).
    from app.core.rate_limiter import rate_limit

    rate_limit("30/hour", scope="anon_sessions")(request)

    session = create_session(db)
    return build_journey_response(db, session)


@router.get("/{session_id}", response_model=JourneyResponse)
def get_session_state(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current session state and view.

    GH-F1-IDOR: requires authentication. Enforces session ownership via
    assert_session_access (student→own; school_staff→same school; admin→all).
    """
    assert_session_access(session_id, current_user, db)
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return build_journey_response(db, session)


@router.post("/{session_id}/events", response_model=JourneyResponse)
def submit_event(
    session_id: UUID,
    event: SessionEventCreate,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit an event and advance the journey flow.

    GH-F1-IDOR: requires authentication + session ownership.

    GH-S10-BE-03 · when the session transitions to is_completed=True for an
    authenticated user, schedule a Bitrix sync (lead + deal) in the background.
    """
    session = assert_session_access(session_id, current_user, db)

    # M-006 · gate: menor de 16 (edad conocida) sin consentimiento parental.
    # Auditoría R5 · el gate evalúa al DUEÑO de la sesión, no al caller: un
    # staff con acceso no debe poder avanzar el journey de un menor sin
    # consentimiento (antes se evaluaba al staff y el gate no aplicaba).
    gate_subject = current_user
    if session.user_id is not None and session.user_id != current_user.id:
        owner = db.query(User).filter(User.id == session.user_id).first()
        if owner is not None:
            gate_subject = owner
    if parental_consent_service.needs_parental_consent(gate_subject):
        raise HTTPException(
            status_code=403, detail="minor_parental_consent_required"
        )

    was_completed = bool(session.is_completed)
    response = process_event(
        db=db,
        session=session,
        event_type=event.event_type,
        step_id=event.step_id,
        payload=event.payload,
    )

    # Re-fetch the freshest state · process_event committed already
    db.refresh(session)
    if (
        not was_completed
        and session.is_completed
        and session.user_id is not None
    ):
        try:
            bitrix_sync_service.enqueue_journey_completed(
                background_tasks,
                session.user_id,
            )
            logger.info(
                "bitrix sync enqueued · session=%s user=%s",
                session.id,
                session.user_id,
            )
        except Exception as exc:  # pragma: no cover · defensive
            logger.warning("bitrix enqueue failed · %s", exc)

    return response


@router.post(
    "/{session_id}/interpretar",
    response_model=JourneyInterpretacionResponse,
    dependencies=[Depends(rate_limit("12/minute", scope="journey_interprete"))],
)
def interpretar_respuesta(
    session_id: UUID,
    cuerpo: JourneyInterpretacionCreate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lee una respuesta contada con palabras · **no guarda nada**.

    Devuelve a qué opción del paso equivale (o None, y entonces Hop repregunta)
    y qué le dice Hop. Guardar sigue siendo el `answer` de siempre contra
    `/events`: el mismo evento que dispara el botón, con el mismo valor
    canónico. Por eso los seis servicios que leen las respuestas del Journey no
    cambian, que es el punto de todo esto.

    Se separa del evento a propósito: así una caída del modelo no puede tocar el
    camino que escribe en la sesión, y los botones completan el paso igual.

    409 cuando el paso no conversa —flag apagado, paso fuera de la lista, o el
    front desincronizado pidiendo por un paso que no es el actual—: sin el
    campo de texto en pantalla, llegar aquí significa que el cliente está fuera
    de sincronía y debe recargar el estado.
    """
    session = assert_session_access(session_id, current_user, db)

    from app.core.state_machine import get_step
    from app.services import journey_interprete

    if cuerpo.step_id != session.current_step:
        raise HTTPException(status_code=409, detail="paso_desincronizado")

    step = get_step(cuerpo.step_id)
    if not journey_interprete.acepta_texto_libre(db, session, step):
        raise HTTPException(status_code=409, detail="paso_no_conversacional")

    texto = (cuerpo.texto or "").strip()
    if not texto:
        raise HTTPException(status_code=422, detail="texto_vacio")

    lectura = journey_interprete.interpretar(
        texto,
        step,
        session_id=str(session.id),
        db=db,
        user_id=session.user_id,
    )
    return JourneyInterpretacionResponse(
        opcion=lectura.opcion,
        confianza=lectura.confianza,
        respuesta_de_hop=lectura.respuesta_de_hop,
        necesita_confirmar=lectura.necesita_confirmar,
    )


@router.get("/{session_id}/raw", response_model=SessionResponse)
def get_raw_session(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get raw session data (for debugging).

    GH-F1-IDOR: requires authentication + session ownership.
    """
    session = assert_session_access(session_id, current_user, db)
    return session
