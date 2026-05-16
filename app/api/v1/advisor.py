"""Advisor lead API endpoints."""

import logging
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db, SessionLocal
from app.db.models import AdvisorLead, Route, User
from app.schemas.journey import AdvisorLeadCreate, AdvisorLeadResponse
from app.services.journey_service import get_session
from app.services.ai_service import generate_advisor_brief
from app.services import bitrix_sync_service
from app.api.v1.auth import get_current_user
from app.core.access import assert_session_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/advisor-leads", tags=["advisor"])


@router.post("", response_model=AdvisorLeadResponse)
def create_advisor_lead(
    lead_data: AdvisorLeadCreate,
    session_id: UUID,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit advisor contact form.

    GH-F1-IDOR: requires authentication + session ownership.
    """
    session = assert_session_access(session_id, current_user, db)

    # Check if lead already exists
    existing = (
        db.query(AdvisorLead)
        .filter(AdvisorLead.session_id == session_id)
        .first()
    )
    if existing:
        # Update existing lead
        existing.name = lead_data.name
        existing.email = lead_data.email
        existing.phone = lead_data.phone
        db.commit()
        db.refresh(existing)
        return existing

    # Get routes for brief generation
    routes = (
        db.query(Route)
        .filter(Route.session_id == session_id)
        .all()
    )

    routes_data = [
        {
            "name": r.name,
            "key": r.key,
            "why": r.why,
            "is_primary": r.is_primary,
        }
        for r in routes
    ]

    # Generate advisor brief
    answers = session.answers or {}
    brief_output = generate_advisor_brief(answers, routes_data, str(session_id))

    # Format brief as text
    brief_text = f"**Perfil del estudiante:**\n"
    brief_text += f"{brief_output.profile_summary}\n\n"

    if brief_output.primary_route:
        brief_text += f"**Ruta prioritaria:** {brief_output.primary_route}\n\n"

    brief_text += "**Consideraciones clave:**\n"
    for consideration in brief_output.key_considerations:
        brief_text += f"- {consideration}\n"

    if brief_output.emotional_state:
        brief_text += f"\n**Estado emocional:** {brief_output.emotional_state}"

    # Create lead
    lead = AdvisorLead(
        session_id=session_id,
        name=lead_data.name,
        email=lead_data.email,
        phone=lead_data.phone,
        advisor_brief=brief_text,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    # GH-S10-BE-03 · enqueue Bitrix sync of the AdvisorLead in background.
    # Uses a fresh DB session inside the task to avoid request-scoped state.
    lead_id_str = str(lead.id)

    def _runner_advisor() -> None:
        bg_db = SessionLocal()
        try:
            adv = (
                bg_db.query(AdvisorLead)
                .filter(AdvisorLead.id == UUID(lead_id_str))
                .first()
            )
            if adv is not None:
                bitrix_sync_service.sync_advisor_lead(bg_db, adv)
        except Exception as exc:  # pragma: no cover · defensive
            logger.warning("bitrix sync_advisor_lead bg failed · %s", exc)
        finally:
            bg_db.close()

    background_tasks.add_task(_runner_advisor)

    return lead


@router.get("/{session_id}", response_model=AdvisorLeadResponse)
def get_advisor_lead(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get advisor lead for a session.

    GH-F1-IDOR: requires authentication + session ownership.
    """
    assert_session_access(session_id, current_user, db)

    lead = (
        db.query(AdvisorLead)
        .filter(AdvisorLead.session_id == session_id)
        .first()
    )

    if not lead:
        raise HTTPException(status_code=404, detail="No advisor lead found")

    return lead


@router.get("/{session_id}/brief")
def get_advisor_brief_preview(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get advisor brief preview without submitting contact info.

    GH-F1-IDOR: requires authentication + session ownership.
    """
    session = assert_session_access(session_id, current_user, db)

    # Get routes
    routes = (
        db.query(Route)
        .filter(Route.session_id == session_id)
        .all()
    )

    routes_data = [
        {
            "name": r.name,
            "key": r.key,
            "why": r.why,
            "is_primary": r.is_primary,
        }
        for r in routes
    ]

    # Generate brief
    answers = session.answers or {}
    brief_output = generate_advisor_brief(answers, routes_data, str(session_id))

    # Format as text
    brief_text = f"**Perfil del estudiante:**\n"
    brief_text += f"- Etapa: {answers.get('lifeStage', 'No especificada')}\n"
    brief_text += f"- Horizonte temporal: {answers.get('timeHorizon', 'No especificado')}\n"
    brief_text += f"- Nivel de claridad: {brief_output.emotional_state or 'No determinado'}\n\n"

    brief_text += "**Motivaciones principales:**\n"
    for consideration in brief_output.key_considerations:
        brief_text += f"- {consideration}\n"

    if brief_output.primary_route:
        brief_text += f"\n**Ruta prioritaria:**\n{brief_output.primary_route}"

    return {"brief": brief_text}
