"""Lead profile endpoints for quick vocational quiz (public, no auth required)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel, EmailStr
from typing import List, Optional

from app.config import get_settings
from app.db.database import get_db
from app.db.models import LeadProfile
from app.data.quick_profile_quiz import get_questions_for_client, calculate_profile

router = APIRouter(prefix="/lead-profile", tags=["Lead Profile"])


def _rate_limit_lead_submit(request: Request) -> None:
    """Endpoint público que inserta filas en DB · limita spam por IP."""
    from app.core.rate_limiter import rate_limit

    return rate_limit(
        get_settings().rate_limit_lead_submit, scope="lead_profile_submit"
    )(request)


class ContactInfo(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None


class SubmitQuizRequest(BaseModel):
    answers: dict
    contact: ContactInfo


class ProfileResultResponse(BaseModel):
    profile_type: str
    profile_name: str
    emoji: str
    description: str
    traits: List[str]
    recommendation: str


@router.get("/quiz")
def get_quiz_questions():
    """Get quiz questions (public endpoint, no auth required)."""
    return get_questions_for_client()


@router.post(
    "/submit",
    response_model=ProfileResultResponse,
    dependencies=[Depends(_rate_limit_lead_submit)],
)
def submit_quiz(
    request: SubmitQuizRequest,
    db: DBSession = Depends(get_db),
):
    """Submit quiz answers and contact info, get profile result.

    Public endpoint - no auth required.
    """
    # Calculate profile from answers
    profile_result = calculate_profile(request.answers)

    # Save lead profile to database
    lead = LeadProfile(
        name=request.contact.name,
        email=request.contact.email,
        phone=request.contact.phone,
        answers=request.answers,
        profile_result=profile_result,
    )
    db.add(lead)
    db.commit()

    return ProfileResultResponse(**profile_result)
