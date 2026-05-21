"""Admin · AI Audit panel · M-001 (2026-05-21).

GH-LOCAL-CLIENT-MODULES · cliente pidió un panel donde su equipo califique
recomendaciones de Hop con 👍/👎 + comentario. Endpoints:

- POST   /admin/ai-audit/feedback        · cualquier clinical/admin role
- GET    /admin/ai-audit                 · super_admin, gh_commercial, gh_advisor
- GET    /admin/ai-audit/aggregates      · super_admin, gh_commercial, gh_advisor
- GET    /admin/ai-audit/export.csv      · super_admin only
- DELETE /admin/ai-audit/feedback/{id}   · super_admin only (corrección manual)

Note: clinical-only roles (psy) NO escriben feedback aquí (su feedback
clínico vive en `session_notes`). Aquí solo escriben quienes evalúan
calidad de IA: gh_commercial, gh_advisor, super_admin.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import (
    AI_FEEDBACK_RATINGS,
    AiRecommendationFeedback,
    User,
    UserRole,
)
from app.schemas.ai_audit import (
    AiFeedbackAggregates,
    AiFeedbackCreate,
    AiFeedbackList,
    AiFeedbackOut,
)
from app.services import ai_audit_service
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/admin/ai-audit", tags=["Admin · AI Audit"])


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------


def _require_audit_writer(user: User) -> None:
    """Quienes pueden CREATE feedback."""
    if user.role not in (
        UserRole.SUPER_ADMIN,
        UserRole.GH_COMMERCIAL,
        UserRole.GH_ADVISOR,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only gh_commercial, gh_advisor or super_admin can rate AI recommendations.",
        )


def _require_audit_reader(user: User) -> None:
    """Quienes pueden LIST + aggregates."""
    if user.role not in (
        UserRole.SUPER_ADMIN,
        UserRole.GH_COMMERCIAL,
        UserRole.GH_ADVISOR,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only gh_commercial, gh_advisor or super_admin can view AI audit data.",
        )


def _require_super(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only super_admin.",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/feedback",
    response_model=AiFeedbackOut,
    status_code=201,
    summary="M-001 · register 👍/👎 feedback on an AI recommendation",
)
def post_feedback(
    body: AiFeedbackCreate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_audit_writer(current_user)
    if body.rating not in AI_FEEDBACK_RATINGS:
        raise HTTPException(status_code=400, detail=f"rating must be one of {AI_FEEDBACK_RATINGS}")
    row = ai_audit_service.create_feedback(
        db,
        rated_by=current_user,
        recommendation_type=body.recommendation_type,
        rating=body.rating,
        recommendation_ref=body.recommendation_ref,
        context=body.context,
        comment=body.comment,
    )
    return ai_audit_service.to_out(
        row,
        rater_name=current_user.name or current_user.email,
        rater_role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
    )


@router.get(
    "",
    response_model=AiFeedbackList,
    summary="M-001 · paginated list of recent AI feedback",
)
def list_feedback(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    recommendation_type: Optional[str] = Query(None),
    rating: Optional[str] = Query(None),
    rated_by_user_id: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    _require_audit_reader(current_user)
    rows, total = ai_audit_service.list_feedback(
        db,
        page=page,
        page_size=page_size,
        recommendation_type=recommendation_type,
        rating=rating,
        rated_by_user_id=rated_by_user_id,
        date_from=date_from,
        date_to=date_to,
    )
    # Batch fetch raters for name/role.
    rater_ids = {r.rated_by_user_id for r in rows if r.rated_by_user_id is not None}
    raters_by_id: dict[UUID, User] = {}
    if rater_ids:
        for u in db.query(User).filter(User.id.in_(rater_ids)).all():
            raters_by_id[u.id] = u

    items = [
        ai_audit_service.to_out(
            r,
            rater_name=(raters_by_id.get(r.rated_by_user_id).name if r.rated_by_user_id and raters_by_id.get(r.rated_by_user_id) else None),
            rater_role=(
                raters_by_id.get(r.rated_by_user_id).role.value
                if r.rated_by_user_id
                and raters_by_id.get(r.rated_by_user_id)
                and hasattr(raters_by_id[r.rated_by_user_id].role, "value")
                else None
            ),
        )
        for r in rows
    ]
    return AiFeedbackList(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/aggregates",
    response_model=AiFeedbackAggregates,
    summary="M-001 · counts + positive rate by type for the last N days",
)
def aggregates(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = Query(30, ge=1, le=365),
):
    _require_audit_reader(current_user)
    return ai_audit_service.aggregates(db, days=days)


@router.get(
    "/export.csv",
    summary="M-001 · CSV export of all feedback (super_admin · max 10k rows)",
)
def export_csv(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    _require_super(current_user)
    rows, _total = ai_audit_service.list_feedback(
        db,
        page=1,
        page_size=10_000,
        date_from=date_from,
        date_to=date_to,
    )
    rater_ids = {r.rated_by_user_id for r in rows if r.rated_by_user_id is not None}
    raters_by_id: dict[UUID, User] = {}
    if rater_ids:
        for u in db.query(User).filter(User.id.in_(rater_ids)).all():
            raters_by_id[u.id] = u
    body = ai_audit_service.to_csv(rows, raters_by_id)
    filename = f"ai-audit-{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete(
    "/feedback/{feedback_id}",
    status_code=204,
    summary="M-001 · super_admin · delete a feedback entry (corrección)",
)
def delete_feedback(
    feedback_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super(current_user)
    row = (
        db.query(AiRecommendationFeedback)
        .filter(AiRecommendationFeedback.id == feedback_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="feedback not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)
