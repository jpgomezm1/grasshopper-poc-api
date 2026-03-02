"""Profile API endpoints."""

from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import ProfileVersion, User, VocationalTestResult
from app.schemas.profile import ProfileVersionResponse, ProfileSummary, VocationalResultSummary
from app.services.journey_service import get_session, save_profile_version
from app.services.ai_service import derive_motivations, derive_constraints

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/{session_id}", response_model=ProfileSummary)
def get_profile(
    session_id: UUID,
    db: DBSession = Depends(get_db),
):
    """Get unified profile summary for a session (journey + English test + vocational tests)."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    answers = session.answers or {}
    motivations = derive_motivations(answers)
    constraints = derive_constraints(answers)

    # Derive stage label
    stage_labels = {
        "Terminando el colegio": "Preparándose para el siguiente paso",
        "En la universidad": "Explorando oportunidades",
        "Ya trabajando": "Buscando un cambio",
        "En transición / no seguro": "En proceso de descubrimiento",
    }
    stage_label = stage_labels.get(answers.get("lifeStage", ""), "Explorando")

    # Derive clarity level
    clarity_levels = {
        "Tengo algo claro y quiero validarlo": "high",
        "Tengo ideas sueltas": "medium",
    }
    clarity_level = clarity_levels.get(answers.get("clarityLevel", ""), "low")

    # Fetch English test and vocational test data from User
    english_cefr_level = None
    english_test_completed = False
    vocational_results: List[VocationalResultSummary] = []

    if session.user_id:
        user = db.query(User).filter(User.id == session.user_id).first()
        if user:
            english_cefr_level = user.english_cefr_level
            english_test_completed = user.english_test_completed

            voc_results = (
                db.query(VocationalTestResult)
                .filter(VocationalTestResult.user_id == user.id)
                .all()
            )
            vocational_results = [
                VocationalResultSummary(
                    test_id=vr.test_id,
                    scores=vr.scores,
                    completed_at=vr.created_at,
                )
                for vr in voc_results
            ]

    return ProfileSummary(
        answers=answers,
        motivations=motivations,
        constraints=constraints,
        stage_label=stage_label,
        clarity_level=clarity_level,
        english_cefr_level=english_cefr_level,
        english_test_completed=english_test_completed,
        vocational_results=vocational_results,
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
