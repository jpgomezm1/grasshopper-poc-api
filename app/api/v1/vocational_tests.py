from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, VocationalTestResult
from app.data.vocational_tests import (
    get_all_tests_summary,
    get_test_by_id,
    calculate_vocational_scores,
    VOCATIONAL_TESTS,
)

router = APIRouter(prefix="/vocational-tests", tags=["Vocational Tests"])


class SubmitVocationalRequest(BaseModel):
    answers: dict


@router.get("")
def list_tests(current_user: User = Depends(get_current_user)):
    return get_all_tests_summary()


# Static routes MUST come before /{test_id} to avoid path conflicts
@router.get("/results/all")
def get_all_results(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    results = db.query(VocationalTestResult).filter(
        VocationalTestResult.user_id == current_user.id
    ).all()

    return [
        {
            "test_id": r.test_id,
            "scores": r.scores,
            "completed_at": r.created_at.isoformat(),
        }
        for r in results
    ]


@router.get("/{test_id}")
def get_test(test_id: str, current_user: User = Depends(get_current_user)):
    test = get_test_by_id(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    return test


@router.post("/{test_id}/submit")
def submit_test(
    test_id: str,
    request: SubmitVocationalRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    test = get_test_by_id(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    scores = calculate_vocational_scores(test_id, request.answers)

    existing = db.query(VocationalTestResult).filter(
        VocationalTestResult.user_id == current_user.id,
        VocationalTestResult.test_id == test_id,
    ).first()

    if existing:
        existing.answers = request.answers
        existing.scores = scores
    else:
        result = VocationalTestResult(
            user_id=current_user.id,
            test_id=test_id,
            answers=request.answers,
            scores=scores,
        )
        db.add(result)

    db.commit()

    return {"test_id": test_id, "scores": scores}


@router.get("/{test_id}/result")
def get_test_result(
    test_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    result = db.query(VocationalTestResult).filter(
        VocationalTestResult.user_id == current_user.id,
        VocationalTestResult.test_id == test_id,
    ).first()

    if not result:
        return None

    return {
        "test_id": result.test_id,
        "scores": result.scores,
        "answers": result.answers,
        "completed_at": result.created_at.isoformat(),
    }
