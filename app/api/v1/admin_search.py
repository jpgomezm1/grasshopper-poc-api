"""Global search endpoint · cross-entity search for super_admin (Bloque C)."""
from __future__ import annotations

from typing import List, Optional, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import Program, School, User, UserRole

router = APIRouter(prefix="/admin", tags=["Admin · Search"])


class SearchResult(BaseModel):
    type: Literal["user", "school", "program", "lead"]
    id: str
    label: str
    subtitle: Optional[str] = None
    navigate_to: str


class GlobalSearchResponse(BaseModel):
    query: str
    total: int
    results: List[SearchResult]


def _require_super_admin(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "super_admin only")


@router.get(
    "/search",
    response_model=GlobalSearchResponse,
    summary="GH-SUPERADMIN · Bloque C · unified search",
)
def global_search(
    q: str = Query(..., min_length=2, max_length=80),
    limit_per_type: int = Query(5, ge=1, le=20),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    needle = f"%{q.lower()}%"
    out: List[SearchResult] = []

    # Users
    user_rows = (
        db.query(User)
        .filter(or_(func.lower(User.email).like(needle), func.lower(User.name).like(needle)))
        .limit(limit_per_type)
        .all()
    )
    for u in user_rows:
        out.append(
            SearchResult(
                type="user",
                id=str(u.id),
                label=u.name or u.email,
                subtitle=f"{u.role.value} · {u.email}",
                navigate_to=f"/admin/users/{u.id}",
            )
        )

    # Schools
    school_rows = (
        db.query(School)
        .filter(func.lower(School.name).like(needle))
        .limit(limit_per_type)
        .all()
    )
    for s in school_rows:
        out.append(
            SearchResult(
                type="school",
                id=str(s.id),
                label=s.name,
                subtitle=f"Colegio · {s.city}" if getattr(s, "city", None) else "Colegio",
                navigate_to=f"/admin/schools/{s.id}",
            )
        )

    # Programs
    program_rows = (
        db.query(Program)
        .filter(or_(func.lower(Program.name).like(needle), func.lower(Program.institution).like(needle)))
        .limit(limit_per_type)
        .all()
    )
    for p in program_rows:
        out.append(
            SearchResult(
                type="program",
                id=str(p.id),
                label=p.name,
                subtitle=f"{p.institution} · {p.country}" if p.institution else (p.country or None),
                navigate_to=f"/admin/programs/{p.id}",
            )
        )

    # Leads (B2C students with bitrix_lead_id OR with lead_pipeline_status set)
    lead_rows = (
        db.query(User)
        .filter(
            User.role == UserRole.STUDENT,
            or_(User.bitrix_lead_id.isnot(None), User.lead_pipeline_status.isnot(None)),
            or_(func.lower(User.email).like(needle), func.lower(User.name).like(needle)),
        )
        .limit(limit_per_type)
        .all()
    )
    for u in lead_rows:
        out.append(
            SearchResult(
                type="lead",
                id=str(u.id),
                label=u.name or u.email,
                subtitle=f"Lead · {u.lead_pipeline_status or 'pending'}",
                navigate_to=f"/admin/crm/leads/{u.id}",
            )
        )

    return GlobalSearchResponse(query=q, total=len(out), results=out)
