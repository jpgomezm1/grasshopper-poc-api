"""Super-admin only endpoints · GH-S8-BE-09/10/11.

- GET /admin/stats/overview        · aggregated KPIs (cached 5 min)
- GET /admin/reports/global        · alias of /admin/stats/overview
- GET /admin/audit-log             · paginated audit trail with filters
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import (
    AuditLog,
    License,
    LicenseStatus,
    Program,
    Report,
    School,
    SavedOferta,
    User,
    UserRole,
    VocationalTestResult,
)
from app.schemas.audit import (
    AdminStatsOverview,
    AuditLogListResponse,
    AuditLogResponse,
)


router = APIRouter(prefix="/admin", tags=["Admin"])


def _ensure_super_admin(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only super_admin can access admin reports.",
        )


# ----------------------------- in-memory cache for stats (5 min TTL) -----------------------------

_STATS_CACHE: dict = {"data": None, "ts": 0.0}
_STATS_TTL_S = 300  # 5 minutes


def _compute_stats(db: DBSession) -> AdminStatsOverview:
    now = datetime.utcnow()
    cutoff_30d = now - timedelta(days=30)

    total_schools = db.query(func.count(School.id)).scalar() or 0
    archived_schools = (
        db.query(func.count(School.id)).filter(School.archived_at.isnot(None)).scalar() or 0
    )
    active_schools = total_schools - archived_schools

    active_licenses = (
        db.query(func.count(License.id))
        .filter(
            License.status == LicenseStatus.ACTIVE.value,
            or_(License.expires_at.is_(None), License.expires_at > now),
        )
        .scalar()
        or 0
    )
    expired_licenses = (
        db.query(func.count(License.id))
        .filter(
            or_(
                License.status == LicenseStatus.EXPIRED.value,
                (License.expires_at.isnot(None)) & (License.expires_at <= now),
            )
        )
        .scalar()
        or 0
    )

    total_students = (
        db.query(func.count(User.id)).filter(User.role == UserRole.STUDENT).scalar() or 0
    )

    students_active_30d = (
        db.query(func.count(User.id))
        .filter(User.role == UserRole.STUDENT, User.updated_at >= cutoff_30d)
        .scalar()
        or 0
    )

    reports_generated_30d = (
        db.query(func.count(Report.id)).filter(Report.created_at >= cutoff_30d).scalar() or 0
    )

    tests_completed_30d = (
        db.query(func.count(VocationalTestResult.id))
        .filter(VocationalTestResult.created_at >= cutoff_30d)
        .scalar()
        or 0
    )

    # Top programs (by saved_ofertas in last 30d) · soft proxy because we
    # don't have a per-recommendation hit table yet.
    top_programs_rows = (
        db.query(SavedOferta.oferta_id, func.count(SavedOferta.id).label("hits"))
        .filter(SavedOferta.created_at >= cutoff_30d)
        .group_by(SavedOferta.oferta_id)
        .order_by(func.count(SavedOferta.id).desc())
        .limit(10)
        .all()
    )
    top_programs = [
        {"program_id": str(r[0]), "hits": int(r[1])} for r in top_programs_rows
    ]

    # Top schools by student count
    top_schools_rows = (
        db.query(School.id, School.name, func.count(User.id).label("students"))
        .outerjoin(User, (User.school_id == School.id) & (User.role == UserRole.STUDENT))
        .filter(School.archived_at.is_(None))
        .group_by(School.id, School.name)
        .order_by(func.count(User.id).desc())
        .limit(10)
        .all()
    )
    top_schools = [
        {"id": str(r[0]), "name": r[1], "students": int(r[2] or 0)} for r in top_schools_rows
    ]

    return AdminStatsOverview(
        total_schools=int(total_schools),
        active_schools=int(active_schools),
        archived_schools=int(archived_schools),
        active_licenses=int(active_licenses),
        expired_licenses=int(expired_licenses),
        total_students=int(total_students),
        students_active_30d=int(students_active_30d),
        reports_generated_30d=int(reports_generated_30d),
        tests_completed_30d=int(tests_completed_30d),
        top_programs=top_programs,
        top_schools=top_schools,
        cached_at=now,
    )


@router.get(
    "/stats/overview",
    response_model=AdminStatsOverview,
    summary="GH-S8-BE-09 · aggregated KPIs (cached 5 min)",
)
def stats_overview(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    refresh: bool = Query(False, description="Bypass cache"),
):
    _ensure_super_admin(current_user)
    now = time.time()
    if (
        not refresh
        and _STATS_CACHE["data"] is not None
        and (now - _STATS_CACHE["ts"]) < _STATS_TTL_S
    ):
        return _STATS_CACHE["data"]

    payload = _compute_stats(db)
    _STATS_CACHE["data"] = payload
    _STATS_CACHE["ts"] = now
    return payload


# Alias to match TASKS.md naming (`/admin/reports/global`).
@router.get(
    "/reports/global",
    response_model=AdminStatsOverview,
    summary="GH-S8-BE-09 · alias of /admin/stats/overview",
)
def reports_global(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    refresh: bool = Query(False),
):
    return stats_overview(db=db, current_user=current_user, refresh=refresh)


# ----------------------------- enriched dashboard -----------------------------
# GH-SUPERADMIN-EXPERIENCE · Bloque H · 2026-05-05
# Dashboard combines existing KPIs (stats_overview) with new live signals so
# the FE doesn't need 5 round-trips for the home page.

@router.get(
    "/dashboard/overview",
    summary="GH-SUPERADMIN · Bloque H · enriched dashboard payload",
)
def dashboard_overview(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    now = datetime.utcnow()
    last_7 = now - timedelta(days=7)
    last_28 = now - timedelta(days=28)

    base_stats = _compute_stats(db)

    # DAU / MAU (any role)
    dau = (
        db.query(func.count(func.distinct(User.id)))
        .filter(User.last_login_at >= now - timedelta(days=1))
        .scalar()
        or 0
    )
    wau = (
        db.query(func.count(func.distinct(User.id)))
        .filter(User.last_login_at >= last_7)
        .scalar()
        or 0
    )
    mau = (
        db.query(func.count(func.distinct(User.id)))
        .filter(User.last_login_at >= last_28)
        .scalar()
        or 0
    )

    # Active impersonation sessions count
    from app.db.models import ImpersonationSession, AdminAlert

    active_impersonations = (
        db.query(func.count(ImpersonationSession.id))
        .filter(ImpersonationSession.ended_at.is_(None))
        .scalar()
        or 0
    )

    # Active alerts grouped by severity
    alerts_rows = (
        db.query(AdminAlert.severity, func.count(AdminAlert.id))
        .filter(AdminAlert.resolved_at.is_(None))
        .group_by(AdminAlert.severity)
        .all()
    )
    alerts = {"critical": 0, "warning": 0, "info": 0}
    for sev, c in alerts_rows:
        alerts[sev] = int(c or 0)

    # Recent audit (last 20)
    recent = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )
    recent_activity = [
        {
            "id": str(r.id),
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "user_id": str(r.user_id) if r.user_id else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in recent
    ]

    # Weekly registrations timeseries (last 4 weeks)
    weekly_rows = (
        db.query(
            func.date_trunc("week", User.created_at).label("w"),
            func.count(User.id).label("c"),
        )
        .filter(User.created_at >= last_28)
        .group_by(func.date_trunc("week", User.created_at))
        .order_by(func.date_trunc("week", User.created_at))
        .all()
    ) if db.bind.dialect.name == "postgresql" else []
    weekly_registrations = [
        {"week": str(r.w), "count": int(r.c or 0)} for r in weekly_rows
    ]

    return {
        "base": base_stats.model_dump() if hasattr(base_stats, "model_dump") else base_stats,
        "live": {
            "dau": int(dau),
            "wau": int(wau),
            "mau": int(mau),
            "active_impersonations": int(active_impersonations),
        },
        "alerts": alerts,
        "recent_activity": recent_activity,
        "weekly_registrations": weekly_registrations,
    }


# ----------------------------- audit log -----------------------------

@router.get(
    "/audit-log",
    response_model=AuditLogListResponse,
    summary="GH-S8-BE-11 · paginated audit log with filters",
)
def list_audit_log(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    user_id: Optional[UUID] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
):
    _ensure_super_admin(current_user)

    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if resource_id:
        q = q.filter(AuditLog.resource_id == resource_id)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if since:
        q = q.filter(AuditLog.created_at >= since)
    if until:
        q = q.filter(AuditLog.created_at <= until)

    total = q.count()
    rows = (
        q.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # batch user emails
    user_ids = {r.user_id for r in rows if r.user_id}
    email_map: dict = {}
    if user_ids:
        for u in db.query(User.id, User.email).filter(User.id.in_(user_ids)).all():
            email_map[u.id] = u.email

    items = []
    for r in rows:
        items.append(
            AuditLogResponse(
                id=r.id,
                user_id=r.user_id,
                user_email=email_map.get(r.user_id) if r.user_id else None,
                action=r.action,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                payload=r.payload,
                ip_address=r.ip_address,
                user_agent=r.user_agent,
                created_at=r.created_at,
            )
        )

    total_pages = max(1, math.ceil(total / page_size)) if total else 0
    return AuditLogListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
