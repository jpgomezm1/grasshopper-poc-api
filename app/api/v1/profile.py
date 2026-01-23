"""Profile API endpoints."""

from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import ProfileVersion
from app.schemas.profile import ProfileVersionResponse, ProfileSummary
from app.services.journey_service import get_session, save_profile_version
from app.services.ai_service import derive_motivations, derive_constraints

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/{session_id}", response_model=ProfileSummary)
def get_profile(
    session_id: UUID,
    db: DBSession = Depends(get_db),
):
    """Get profile summary for a session."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    answers = session.answers or {}
    motivations = derive_motivations(answers)
    constraints = derive_constraints(answers)

    # Derive stage label
    stage_labels = {
        "Terminando el colegio": "Preparandose para el siguiente paso",
        "En la universidad": "Explorando oportunidades",
        "Ya trabajando": "Buscando un cambio",
        "En transicion / no seguro": "En proceso de descubrimiento",
    }
    stage_label = stage_labels.get(answers.get("lifeStage", ""), "Explorando")

    # Derive clarity level
    clarity_levels = {
        "Tengo algo claro y quiero validarlo": "high",
        "Tengo ideas sueltas": "medium",
    }
    clarity_level = clarity_levels.get(answers.get("clarityLevel", ""), "low")

    return ProfileSummary(
        answers=answers,
        motivations=motivations,
        constraints=constraints,
        stage_label=stage_label,
        clarity_level=clarity_level,
    )


@router.get("/{session_id}/versions", response_model=List[ProfileVersionResponse])
def get_profile_versions(
    session_id: UUID,
    db: DBSession = Depends(get_db),
):
    """Get all profile versions for a session."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    versions = (
        db.query(ProfileVersion)
        .filter(ProfileVersion.session_id == session_id)
        .order_by(ProfileVersion.version.desc())
        .all()
    )

    return versions


@router.post("/{session_id}/versions", response_model=ProfileVersionResponse)
def create_profile_version(
    session_id: UUID,
    db: DBSession = Depends(get_db),
):
    """Save a new profile version."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    version = save_profile_version(db, session)
    return version
