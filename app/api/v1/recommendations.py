"""Recommendations API · Sprint 6.

Endpoints:
  - POST /recommendations/generate    · genera (o reusa cache) y devuelve bundle
  - GET  /recommendations/me          · alias · devuelve cache si existe, genera si no
  - POST /recommendations/preferences · PATCH parcial budget_band/preferred_countries
  - POST /recommendations/retry       · forzar regeneración (atajo de FE para fallback)

Todos requieren auth (`get_current_user`).

GH-S6-BE-07/08 · added 2026-04-30.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, UserRole
from app.schemas.consolidated_profile import (
    ConsolidatedProfile,
    GenerateRecommendationsRequest,
    RecommendationsBundle,
    StudentPreferencesUpdate,
)
from app.services.consolidation_service import (
    ConsolidationFailure,
    NoTestsAvailable,
    invalidate_cache,
)
from app.services.recommendation_service import (
    RecommendationFailure,
    generate_recommendations,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _ensure_student(user: User) -> None:
    """Only students get personal recommendations.

    School staff / super_admin can read aggregated data via other endpoints.
    """
    if user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los estudiantes pueden generar recomendaciones personales.",
        )


def _bundle_from(
    user_id, profile: ConsolidatedProfile, recs, cache_row, cached: bool
) -> RecommendationsBundle:
    return RecommendationsBundle(
        user_id=user_id,
        profile=profile,
        recommendations=recs,
        cached=cached,
        generated_at=cache_row.generated_at if cache_row else None,
        profile_hash=cache_row.profile_hash if cache_row else None,
        status="ready",
    )


def _empty_bundle(user_id) -> RecommendationsBundle:
    """200 OK con bundle vacío cuando el estudiante todavía no tiene tests.

    B-010 (QA round 2) · `/recommendations/me` no debe devolver 503 cuando la
    razón es "sin tests" · es un estado esperado del onboarding.
    """
    return RecommendationsBundle(
        user_id=user_id,
        profile=None,
        recommendations=[],
        cached=False,
        profile_hash=None,
        status="empty",
    )


@router.post("/generate", response_model=RecommendationsBundle)
def post_generate(
    body: Optional[GenerateRecommendationsRequest] = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Trigger consolidation + recommendations · uses cache unless force_refresh."""
    _ensure_student(current_user)
    body = body or GenerateRecommendationsRequest()

    try:
        profile, recs, cache_row, cached = generate_recommendations(
            db,
            current_user,
            limit=body.limit,
            force_refresh=body.force_refresh,
        )
    except ConsolidationFailure as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except RecommendationFailure as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    return _bundle_from(current_user.id, profile, recs, cache_row, cached)


@router.get("/me", response_model=RecommendationsBundle)
def get_me(
    limit: int = 5,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Returns cached bundle if any · generates on first hit.

    B-010 (QA round 2): cuando el estudiante todavía no tiene tests
    psicométricos, devolvemos 200 con `status="empty"` en vez de 503 ·
    el FE muestra un empty state, no un error.
    """
    _ensure_student(current_user)

    try:
        profile, recs, cache_row, cached = generate_recommendations(
            db, current_user, limit=limit, force_refresh=False
        )
    except NoTestsAvailable:
        # Onboarding state · NOT an error. 200 OK + bundle vacío.
        logger.info(
            "recommendations.me · empty bundle (no tests yet)",
            extra={"user_id": str(current_user.id)},
        )
        return _empty_bundle(current_user.id)
    except ConsolidationFailure as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except RecommendationFailure as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    return _bundle_from(current_user.id, profile, recs, cache_row, cached)


@router.post("/retry", response_model=RecommendationsBundle)
def post_retry(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Shortcut · invalidate cache and regenerate."""
    _ensure_student(current_user)
    invalidate_cache(db, current_user.id)
    try:
        profile, recs, cache_row, cached = generate_recommendations(
            db, current_user, limit=5, force_refresh=True
        )
    except (ConsolidationFailure, RecommendationFailure) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    return _bundle_from(current_user.id, profile, recs, cache_row, cached)


@router.patch("/preferences", response_model=RecommendationsBundle)
def patch_preferences(
    body: StudentPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Update budget / preferred_countries on the user, then regenerate.

    Triggers cache invalidation because the input changed.
    """
    _ensure_student(current_user)

    changed = False
    if body.budget_band is not None:
        current_user.budget_band = body.budget_band
        changed = True
    if body.budget_max_usd is not None:
        current_user.budget_max_usd = body.budget_max_usd
        changed = True
    if body.preferred_countries is not None:
        # Clean: dedupe + non-empty strings
        cleaned = []
        seen = set()
        for c in body.preferred_countries:
            v = (c or "").strip()
            if v and v.lower() not in seen:
                seen.add(v.lower())
                cleaned.append(v)
        current_user.preferred_countries = cleaned
        changed = True

    if changed:
        db.commit()
        invalidate_cache(db, current_user.id)

    try:
        profile, recs, cache_row, cached = generate_recommendations(
            db, current_user, limit=5, force_refresh=True
        )
    except (ConsolidationFailure, RecommendationFailure) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    return _bundle_from(current_user.id, profile, recs, cache_row, cached)
