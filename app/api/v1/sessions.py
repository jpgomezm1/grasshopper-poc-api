"""Session API endpoints."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
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

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=JourneyResponse)
def create_new_session(
    db: DBSession = Depends(get_db),
):
    """Create a new journey session."""
    session = create_session(db)
    return build_journey_response(db, session)


@router.get("/{session_id}", response_model=JourneyResponse)
def get_session_state(
    session_id: UUID,
    db: DBSession = Depends(get_db),
):
    """Get current session state and view."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return build_journey_response(db, session)


@router.post("/{session_id}/events", response_model=JourneyResponse)
def submit_event(
    session_id: UUID,
    event: SessionEventCreate,
    db: DBSession = Depends(get_db),
):
    """Submit an event and advance the journey flow."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return process_event(
        db=db,
        session=session,
        event_type=event.event_type,
        step_id=event.step_id,
        payload=event.payload,
    )


@router.get("/{session_id}/raw", response_model=SessionResponse)
def get_raw_session(
    session_id: UUID,
    db: DBSession = Depends(get_db),
):
    """Get raw session data (for debugging)."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
