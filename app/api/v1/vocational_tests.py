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
from app.services.scoring_service import derive_test_extras
from app.services import parental_consent_service

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

    output = []
    for r in results:
        raw_scores = dict(r.scores or {})
        extras = raw_scores.pop("_extras", None)
        item = {
            "test_id": r.test_id,
            "scores": raw_scores,
            "completed_at": r.created_at.isoformat(),
        }
        if extras is not None:
            item["extras"] = extras
        output.append(item)
    return output


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

    # M-006 · gate: menor de 16 (edad conocida) sin consentimiento parental.
    if parental_consent_service.needs_parental_consent(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="minor_parental_consent_required",
        )

    scores = calculate_vocational_scores(test_id, request.answers)
    extras = derive_test_extras(test_id, request.answers)

    # Persist extras inside the JSON ``scores`` column so we don't need a
    # migration. Shape stays backward compatible: legacy tests keep the
    # category->percentage map; MBTI/iStrong add an ``_extras`` key.
    persisted_scores = dict(scores)
    if extras is not None:
        persisted_scores["_extras"] = extras

    existing = db.query(VocationalTestResult).filter(
        VocationalTestResult.user_id == current_user.id,
        VocationalTestResult.test_id == test_id,
    ).first()

    if existing:
        existing.answers = request.answers
        existing.scores = persisted_scores
    else:
        result = VocationalTestResult(
            user_id=current_user.id,
            test_id=test_id,
            answers=request.answers,
            scores=persisted_scores,
        )
        db.add(result)

    db.commit()

    # GH-S6 · invalidate the consolidated profile cache so the next
    # `GET /recommendations/me` regenerates with the new test data.
    try:
        from app.services.consolidation_service import invalidate_cache
        invalidate_cache(db, current_user.id)
    except Exception:
        # Never block the test submission for a cache invalidation failure
        pass

    response = {"test_id": test_id, "scores": scores}
    if extras is not None:
        response["extras"] = extras
    return response


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

    raw_scores = dict(result.scores or {})
    extras = raw_scores.pop("_extras", None)

    payload = {
        "test_id": result.test_id,
        "scores": raw_scores,
        "answers": result.answers,
        "completed_at": result.created_at.isoformat(),
    }
    if extras is not None:
        payload["extras"] = extras
    return payload
