from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, EnglishTestResult
from app.data.english_test_questions import get_questions_for_client, calculate_score

router = APIRouter(prefix="/english-test", tags=["English Test"])


class SubmitAnswersRequest(BaseModel):
    answers: dict


class SectionScoreResponse(BaseModel):
    correct: int
    total: int
    percentage: int


class TestResultResponse(BaseModel):
    score: int
    total_questions: int
    percentage: int
    cefr_level: str
    section_scores: dict


@router.get("/questions")
def get_questions(current_user: User = Depends(get_current_user)):
    return get_questions_for_client()


@router.post("/submit", response_model=TestResultResponse)
def submit_test(
    request: SubmitAnswersRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    existing = db.query(EnglishTestResult).filter(
        EnglishTestResult.user_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="English test already completed",
        )

    result = calculate_score(request.answers)

    test_result = EnglishTestResult(
        user_id=current_user.id,
        answers=request.answers,
        score=result["score"],
        total_questions=result["total_questions"],
        cefr_level=result["cefr_level"],
        section_scores=result["section_scores"],
    )
    db.add(test_result)

    current_user.english_test_completed = True
    current_user.english_cefr_level = result["cefr_level"]

    db.commit()

    return TestResultResponse(
        score=result["score"],
        total_questions=result["total_questions"],
        percentage=result["percentage"],
        cefr_level=result["cefr_level"],
        section_scores=result["section_scores"],
    )


@router.get("/result")
def get_result(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    result = db.query(EnglishTestResult).filter(
        EnglishTestResult.user_id == current_user.id
    ).first()

    if not result:
        return None

    total = result.total_questions
    percentage = round((result.score / total) * 100) if total > 0 else 0

    return {
        "score": result.score,
        "total_questions": total,
        "percentage": percentage,
        "cefr_level": result.cefr_level,
        "section_scores": result.section_scores,
    }
