"""Institutions catalog (read-only) · GH-LOCAL-CLIENT-CATALOG (2026-05-28).

Endpoints:
    GET /institutions               · paginated list + filters
    GET /institutions/facets        · aggregated counts for filter UI
    GET /institutions/{id}          · single record by id

Access: gh_advisor, gh_commercial, super_admin (internal commercial data).
"""
from __future__ import annotations

import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import GH_TEAM_ROLES, InstitutionCatalog, User
from app.schemas.institution import (
    InstitutionCatalogFacets,
    InstitutionCatalogListResponse,
    InstitutionCatalogResponse,
)
from app.services.auth_service import get_current_user


router = APIRouter(prefix="/institutions", tags=["Institutions"])


def _require_gh_or_admin(user: User) -> None:
    if user.role not in GH_TEAM_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · institutions catalog is restricted to the gh team",
        )


@router.get("", response_model=InstitutionCatalogListResponse)
def list_institutions(
    country: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    partner_group: Optional[str] = Query(None),
    agreement_status: Optional[str] = Query(None),
    active: Optional[bool] = Query(None),
    q: Optional[str] = Query(None, description="case-insensitive substring match on name/city"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_gh_or_admin(current_user)

    query = db.query(InstitutionCatalog)
    if country:
        query = query.filter(InstitutionCatalog.country == country)
    if category:
        query = query.filter(InstitutionCatalog.category == category)
    if partner_group:
        query = query.filter(InstitutionCatalog.partner_group == partner_group)
    if agreement_status:
        query = query.filter(InstitutionCatalog.agreement_status == agreement_status)
    if active is not None:
        query = query.filter(InstitutionCatalog.active == active)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            or_(
                func.lower(InstitutionCatalog.name).like(like),
                func.lower(InstitutionCatalog.city).like(like),
            )
        )

    total = query.count()
    items = (
        query.order_by(InstitutionCatalog.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return InstitutionCatalogListResponse(
        items=[InstitutionCatalogResponse.model_validate(it) for it in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/facets", response_model=InstitutionCatalogFacets)
def list_facets(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_gh_or_admin(current_user)

    def _agg(col):
        rows = (
            db.query(col, func.count(InstitutionCatalog.id))
            .filter(col.isnot(None))
            .group_by(col)
            .order_by(func.count(InstitutionCatalog.id).desc())
            .all()
        )
        return [{"value": v, "count": c} for v, c in rows if v is not None]

    return InstitutionCatalogFacets(
        countries=_agg(InstitutionCatalog.country),
        categories=_agg(InstitutionCatalog.category),
        partner_groups=_agg(InstitutionCatalog.partner_group),
        agreement_statuses=_agg(InstitutionCatalog.agreement_status),
        total=db.query(InstitutionCatalog).count(),
    )


@router.get("/{institution_id}", response_model=InstitutionCatalogResponse)
def get_institution(
    institution_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_gh_or_admin(current_user)
    obj = db.query(InstitutionCatalog).filter(InstitutionCatalog.id == institution_id).first()
    if obj is None:
        raise HTTPException(status_code=404, detail="institution not found")
    return InstitutionCatalogResponse.model_validate(obj)
