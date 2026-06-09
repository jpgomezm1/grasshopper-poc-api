"""Session API endpoints."""

import logging
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import User
from app.schemas.session import (
    SessionCreate,
    SessionEventCreate,
    SessionResponse,
    JourneyResponse,
)
from app.services.journey_service import (
    create_session,
    get_session,
    build_journey_response,
    process_event,
)
from app.services import bitrix_sync_service
from app.services import parental_consent_service
from app.api.v1.auth import get_current_user, get_optional_current_user
from app.core.access import assert_session_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=JourneyResponse)
def create_new_session(
    db: DBSession = Depends(get_db),
):
    """Create a new journey session.

    Anonymous creation is intentionally allowed — students may begin their
    journey before registering. The session is linked to a user only after
    they authenticate (POST /auth/link-session or on registration).
    """
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
    if parental_consent_service.needs_parental_consent(current_user):
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
