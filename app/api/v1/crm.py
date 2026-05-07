"""CRM enriched router · GH-CRM-001 · Sprint CRM enriquecido 2026-05-03.

Surfaces:

    GET    /api/v1/admin/crm/leads
    GET    /api/v1/admin/crm/leads/{user_id}
    POST   /api/v1/admin/crm/leads/{user_id}/regenerate-analysis
    PATCH  /api/v1/admin/crm/leads/{user_id}/status
    GET    /api/v1/admin/crm/kpis
    GET    /api/v1/admin/crm/leads/export

Auth:
    All endpoints require super_admin OR gh_commercial.
    Detail / regenerate / patch additionally apply ownership gating for
    school_radar leads (see crm_service.can_access_lead).

Privacy: returns only metadata for journal + chat per D-025.
"""
from __future__ import annotations

import csv
import io
import logging
import time
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, UserRole
from app.schemas.crm import (
    CrmAiAnalysis,
    CrmKpisResponse,
    CrmLeadDetailResponse,
    CrmLeadListResponse,
    CrmPipelineStatusUpdate,
    CrmRegenerateAnalysisRequest,
)
from app.services import crm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/crm", tags=["CRM"])


# ---------------------------------------------------------------------------
# Auth guards
# ---------------------------------------------------------------------------


def _require_crm_access(user: User) -> None:
    if user.role not in (UserRole.SUPER_ADMIN, UserRole.GH_COMMERCIAL):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only super_admin or gh_commercial can access CRM.",
        )


def _resolve_target_user(db: DBSession, user_id: UUID) -> User:
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    return target


# ---------------------------------------------------------------------------
# In-memory KPI cache (5 min) · pattern reused from admin.py
# ---------------------------------------------------------------------------

_KPI_CACHE: dict = {"data": None, "ts": 0.0}
_KPI_TTL_S = 300


# ---------------------------------------------------------------------------
# GET /admin/crm/leads
# ---------------------------------------------------------------------------


@router.get(
    "/leads",
    response_model=CrmLeadListResponse,
    summary="GH-CRM-001 · paginated CRM lead list",
)
def list_leads(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    origin: Optional[str] = Query(None, regex="^(grasshopper|school_radar|all)$"),
    pipeline_status: Optional[str] = Query(
        None, regex="^(pending|contacted|qualified|converted|declined)$"
    ),
    score_band: Optional[str] = Query(None, regex="^(hot|warm|cold)$"),
    score_min: Optional[int] = Query(None, ge=0, le=100),
    score_max: Optional[int] = Query(None, ge=0, le=100),
    school_id: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None, max_length=120),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = Query(
        "score_desc",
        regex="^(score_desc|score_asc|created_desc|created_asc|last_activity_desc)$",
    ),
):
    _require_crm_access(current_user)
    return crm_service.list_leads(
        db,
        origin=origin if origin in ("grasshopper", "school_radar") else None,
        pipeline_status=pipeline_status,
        score_band_filter=score_band,
        score_min=score_min,
        score_max=score_max,
        school_id=school_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        page=page,
        page_size=page_size,
        sort=sort,
    )


# ---------------------------------------------------------------------------
# GET /admin/crm/kpis
# ---------------------------------------------------------------------------


@router.get(
    "/kpis",
    response_model=CrmKpisResponse,
    summary="GH-CRM-001 · KPI snapshot for the CRM dashboard",
)
def get_kpis(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_crm_access(current_user)
    now = time.time()
    cached = _KPI_CACHE.get("data")
    ts = _KPI_CACHE.get("ts", 0)
    if cached is not None and (now - ts) < _KPI_TTL_S:
        return cached
    fresh = crm_service.compute_kpis(db)
    _KPI_CACHE["data"] = fresh
    _KPI_CACHE["ts"] = now
    return fresh


# ---------------------------------------------------------------------------
# GET /admin/crm/leads/export
# ---------------------------------------------------------------------------


@router.get(
    "/leads/export",
    summary="GH-CRM-001 · export leads (csv|xlsx)",
)
def export_leads(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    format: str = Query("csv", regex="^(csv|xlsx)$"),
    origin: Optional[str] = Query(None, regex="^(grasshopper|school_radar|all)$"),
    pipeline_status: Optional[str] = Query(
        None, regex="^(pending|contacted|qualified|converted|declined)$"
    ),
    score_band: Optional[str] = Query(None, regex="^(hot|warm|cold)$"),
    score_min: Optional[int] = Query(None, ge=0, le=100),
    score_max: Optional[int] = Query(None, ge=0, le=100),
    school_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None, max_length=120),
):
    _require_crm_access(current_user)
    # Pull a wide page · avoid streaming massive datasets in this iteration.
    listing = crm_service.list_leads(
        db,
        origin=origin if origin in ("grasshopper", "school_radar") else None,
        pipeline_status=pipeline_status,
        score_band_filter=score_band,
        score_min=score_min,
        score_max=score_max,
        school_id=school_id,
        search=search,
        page=1,
        page_size=2000,
        sort="score_desc",
    )

    columns = [
        "user_id",
        "email",
        "name",
        "origin",
        "school_id",
        "school_name",
        "score",
        "score_band",
        "pipeline_status",
        "pipeline_status_at",
        "gh_contact_status",
        "gh_contact_requested_at",
        "tests_completed",
        "has_consolidated_profile",
        "last_activity_at",
        "created_at",
    ]

    def _row(item) -> list:
        return [
            str(item.user_id),
            item.email,
            item.name or "",
            item.origin,
            str(item.school_id) if item.school_id else "",
            item.school_name or "",
            item.score,
            item.score_band,
            item.pipeline_status or "",
            item.pipeline_status_at.isoformat() if item.pipeline_status_at else "",
            item.gh_contact_status or "",
            item.gh_contact_requested_at.isoformat()
            if item.gh_contact_requested_at
            else "",
            item.tests_completed,
            "true" if item.has_consolidated_profile else "false",
            item.last_activity_at.isoformat() if item.last_activity_at else "",
            item.created_at.isoformat(),
        ]

    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(columns)
        for it in listing.items:
            w.writerow(_row(it))
        buf.seek(0)
        filename = f"crm-leads-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.csv"
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
        )

    # xlsx path
    try:
        from openpyxl import Workbook
    except Exception:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="openpyxl not installed · only csv format is available.",
        )
    wb = Workbook()
    ws = wb.active
    ws.title = "CRM Leads"
    ws.append(columns)
    for it in listing.items:
        ws.append(_row(it))
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    filename = f"crm-leads-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.xlsx"
    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


# ---------------------------------------------------------------------------
# GET /admin/crm/leads/{user_id}
# ---------------------------------------------------------------------------


@router.get(
    "/leads/{user_id}",
    response_model=CrmLeadDetailResponse,
    summary="GH-CRM-001 · CRM lead detail",
)
def get_lead_detail(
    user_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_crm_access(current_user)
    target = _resolve_target_user(db, user_id)
    # Compute score quickly to enforce ownership gate
    detail = crm_service.get_lead_detail(db, target, include_ai=True)
    if not crm_service.can_access_lead(
        actor=current_user, target=target, target_score=detail.score_breakdown.score
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · this lead belongs to a colegio and has not opted-in.",
        )
    return detail


# ---------------------------------------------------------------------------
# POST /admin/crm/leads/{user_id}/regenerate-analysis
# ---------------------------------------------------------------------------


@router.post(
    "/leads/{user_id}/regenerate-analysis",
    response_model=CrmAiAnalysis,
    summary="GH-CRM-001 · regenerate AI analysis (cached 7d unless force)",
)
def regenerate_analysis(
    user_id: UUID,
    body: Optional[CrmRegenerateAnalysisRequest] = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_crm_access(current_user)
    target = _resolve_target_user(db, user_id)
    detail = crm_service.get_lead_detail(db, target, include_ai=False)
    if not crm_service.can_access_lead(
        actor=current_user, target=target, target_score=detail.score_breakdown.score
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · ownership gate.",
        )
    return crm_service.regenerate_ai_analysis(
        db, target, force=bool(body.force) if body else False
    )


# ---------------------------------------------------------------------------
# PATCH /admin/crm/leads/{user_id}/status
# ---------------------------------------------------------------------------


@router.patch(
    "/leads/{user_id}/status",
    response_model=CrmLeadDetailResponse,
    summary="GH-CRM-001 · move lead in the pipeline",
)
def patch_pipeline_status(
    user_id: UUID,
    body: CrmPipelineStatusUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_crm_access(current_user)
    target = _resolve_target_user(db, user_id)
    pre_detail = crm_service.get_lead_detail(db, target, include_ai=False)
    if not crm_service.can_access_lead(
        actor=current_user, target=target, target_score=pre_detail.score_breakdown.score
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden · ownership gate."
        )
    target = crm_service.update_pipeline_status(
        db,
        target,
        new_status=body.status,
        note=body.note,
        actor=current_user,
        request=request,
    )
    # Invalidate KPI cache so the FE refresh reflects the change quickly
    _KPI_CACHE["data"] = None
    _KPI_CACHE["ts"] = 0
    return crm_service.get_lead_detail(db, target, include_ai=True)
