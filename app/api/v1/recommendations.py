"""Recommendations API · Sprint 6.

Endpoints:
  - POST /recommendations/generate    · devuelve cache vigente o encola generación
  - GET  /recommendations/me          · cache si existe · encola en el primer hit
  - POST /recommendations/preferences · PATCH parcial budget_band/preferred_countries
  - POST /recommendations/retry       · forzar regeneración (atajo de FE para fallback)

Todos requieren auth (`get_current_user`).

GH-S6-BE-07/08 · added 2026-04-30.

FIX 503/H12 (R3 · 2026-07-08): la generación fresca (consolidación +
recomendación, 2 llamadas IA) tarda ~45s y el router de Heroku corta la
conexión a los 30s — el cliente recibía 503 aunque la generación completaba
server-side. Ahora NINGÚN endpoint genera en el request: si el bundle cacheado
está vigente se devuelve (rápido, como siempre); si hay que generar, se encola
en BackgroundTasks y se responde de inmediato `status="generating"` — el FE
hace polling a GET /recommendations/me hasta `ready`/`empty` (o 503 si la
generación en background falló, mismo contrato de error que antes).
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db, SessionLocal
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
    peek_recommendations_bundle,
    user_has_tests,
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


def _generating_bundle(user_id) -> RecommendationsBundle:
    """200 OK con `status="generating"` · la generación corre en background."""
    return RecommendationsBundle(
        user_id=user_id,
        profile=None,
        recommendations=[],
        cached=False,
        profile_hash=None,
        status="generating",
    )


# ── Fix 503/H12 · estado in-process de generaciones en background ──────────
# Un solo dyno web sirve la app, así que un guard módulo-level basta para
# evitar generaciones duplicadas mientras el FE hace polling. El timeout
# suelta el lock si un worker murió sin limpiar (deploy/restart a mitad).
_GENERATING: dict[str, float] = {}
_FAILURES: dict[str, str] = {}
_GENERATION_TIMEOUT_S = 240.0


def _run_generation_bg(user_id_str: str, limit: int, force_refresh: bool) -> None:
    """Worker de BackgroundTasks · sesión de DB propia (la del request se cierra)."""
    from uuid import UUID as _UUID

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == _UUID(user_id_str)).first()
        if user is None:
            return
        generate_recommendations(db, user, limit=limit, force_refresh=force_refresh)
        _FAILURES.pop(user_id_str, None)
    except NoTestsAvailable:
        # Estado de onboarding, no un error: el polling verá `empty`.
        _FAILURES.pop(user_id_str, None)
    except Exception as e:  # ConsolidationFailure / RecommendationFailure / otros
        logger.warning(
            "recommendations.bg_generation_failed",
            extra={"user_id": user_id_str, "error": str(e)},
        )
        _FAILURES[user_id_str] = str(e)
    finally:
        _GENERATING.pop(user_id_str, None)
        db.close()


def _resolve_bundle(
    background_tasks: BackgroundTasks,
    db: DBSession,
    user: User,
    limit: int,
    force_refresh: bool,
) -> RecommendationsBundle:
    """Camino común sin-IA-en-el-request de los 4 endpoints.

    Orden: cache vigente → ready · sin tests → NoTestsAvailable (el caller
    decide el contrato: /me→empty, /generate→503) · fallo previo en
    background → re-lanza (contrato de error de siempre: 503 con detail) ·
    lock activo → generating · si no, encola y devuelve generating.
    """
    uid = str(user.id)

    if not force_refresh:
        peeked = peek_recommendations_bundle(db, user, limit)
        if peeked is not None:
            profile, recs, cache_row = peeked
            return _bundle_from(user.id, profile, recs, cache_row, cached=True)

    if not user_has_tests(db, user):
        raise NoTestsAvailable(
            "El estudiante todavía no tiene tests psicométricos registrados."
        )

    now = time.time()
    started = _GENERATING.get(uid)
    if started is not None and (now - started) < _GENERATION_TIMEOUT_S:
        return _generating_bundle(user.id)

    failure = _FAILURES.pop(uid, None)
    if failure is not None and not force_refresh:
        # La generación en background falló: mismo contrato que el fallo
        # síncrono de antes (503 con detail). El próximo request re-encola.
        raise RecommendationFailure(failure)

    _GENERATING[uid] = now
    background_tasks.add_task(_run_generation_bg, uid, limit, force_refresh)
    logger.info(
        "recommendations.bg_generation_scheduled",
        extra={"user_id": uid, "force_refresh": force_refresh},
    )
    return _generating_bundle(user.id)


@router.post("/generate", response_model=RecommendationsBundle)
def post_generate(
    background_tasks: BackgroundTasks,
    body: Optional[GenerateRecommendationsRequest] = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Cache vigente → bundle · si hay que generar, encola y responde
    `status="generating"` (fix 503/H12)."""
    _ensure_student(current_user)
    body = body or GenerateRecommendationsRequest()

    try:
        return _resolve_bundle(
            background_tasks,
            db,
            current_user,
            limit=body.limit,
            force_refresh=body.force_refresh,
        )
    except (ConsolidationFailure, RecommendationFailure) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )


@router.get("/me", response_model=RecommendationsBundle)
def get_me(
    background_tasks: BackgroundTasks,
    limit: int = 5,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Cache vigente → bundle · primer hit encola y devuelve `generating`
    (este endpoint es también el objetivo del polling del FE).

    B-010 (QA round 2): cuando el estudiante todavía no tiene tests
    psicométricos, devolvemos 200 con `status="empty"` en vez de 503 ·
    el FE muestra un empty state, no un error.
    """
    _ensure_student(current_user)

    try:
        return _resolve_bundle(
            background_tasks, db, current_user, limit=limit, force_refresh=False
        )
    except NoTestsAvailable:
        # Onboarding state · NOT an error. 200 OK + bundle vacío.
        logger.info(
            "recommendations.me · empty bundle (no tests yet)",
            extra={"user_id": str(current_user.id)},
        )
        return _empty_bundle(current_user.id)
    except (ConsolidationFailure, RecommendationFailure) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )


@router.post("/retry", response_model=RecommendationsBundle)
def post_retry(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Shortcut · invalidate cache and regenerate (en background)."""
    _ensure_student(current_user)
    invalidate_cache(db, current_user.id)
    try:
        return _resolve_bundle(
            background_tasks, db, current_user, limit=5, force_refresh=True
        )
    except (ConsolidationFailure, RecommendationFailure) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )


@router.patch("/preferences", response_model=RecommendationsBundle)
def patch_preferences(
    body: StudentPreferencesUpdate,
    background_tasks: BackgroundTasks,
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
        return _resolve_bundle(
            background_tasks, db, current_user, limit=5, force_refresh=True
        )
    except (ConsolidationFailure, RecommendationFailure) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
