"""Observability + integrations endpoints for super_admin.

Bloques covered:
  D · alertas inteligentes (/admin/alerts/*)
  I · external services health (/admin/health/external)
  J · AI cost ledger (/admin/integrations/ai-costs)
  K · error log dashboard (/admin/health/errors)
  L · usage by role (/admin/stats/usage)
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import (
    AdminAlert,
    AIUsageLog,
    ErrorLog,
    User,
    UserRole,
    VocationalTestResult,
)
from app.services.admin_alerts_service import run_checks


router = APIRouter(prefix="/admin", tags=["Admin · Observability"])


def _ensure_super_admin(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "super_admin only")


# --------------------------------------------------------------------------- #
# Bloque D · alertas inteligentes                                             #
# --------------------------------------------------------------------------- #

class AdminAlertOut(BaseModel):
    id: UUID
    type: str
    severity: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    title: str
    body: Optional[str] = None
    data: Optional[dict] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AdminAlertsActiveResponse(BaseModel):
    items: List[AdminAlertOut]
    counts: Dict[str, int]


@router.get("/alerts/active", response_model=AdminAlertsActiveResponse)
def alerts_active(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=200),
):
    _ensure_super_admin(current_user)
    rows = (
        db.query(AdminAlert)
        .filter(AdminAlert.resolved_at.is_(None))
        .order_by(AdminAlert.created_at.desc())
        .limit(limit)
        .all()
    )
    counts: Dict[str, int] = {"info": 0, "warning": 0, "critical": 0}
    for r in rows:
        if r.severity in counts:
            counts[r.severity] += 1
    return AdminAlertsActiveResponse(items=[AdminAlertOut.model_validate(r) for r in rows], counts=counts)


@router.post("/alerts/refresh", response_model=Dict[str, int])
def alerts_refresh(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Force re-run of all alert checks · returns per-check counts."""
    _ensure_super_admin(current_user)
    return run_checks(db)


@router.post("/alerts/{alert_id}/resolve", response_model=AdminAlertOut)
def alerts_resolve(
    alert_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    a = db.query(AdminAlert).filter(AdminAlert.id == alert_id).first()
    if not a:
        raise HTTPException(404, "Alert not found")
    if a.resolved_at is None:
        a.resolved_at = datetime.utcnow()
        a.resolved_by_user_id = current_user.id
        db.commit()
        db.refresh(a)
    return AdminAlertOut.model_validate(a)


# --------------------------------------------------------------------------- #
# Bloque I · external services health                                         #
# --------------------------------------------------------------------------- #

class HealthCheckResult(BaseModel):
    name: str
    status: str  # up | down | degraded
    latency_ms: Optional[int] = None
    last_check_at: datetime
    details: Optional[str] = None


class ExternalHealthResponse(BaseModel):
    services: List[HealthCheckResult]
    cached_until: datetime


_HEALTH_CACHE: dict = {"ts": 0.0, "data": None}
_HEALTH_TTL_S = 60


def _http_check(name: str, url: str, timeout: float = 5.0, expected_status: tuple = (200, 401, 403)) -> HealthCheckResult:
    start = time.time()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.head(url)
            elapsed = int((time.time() - start) * 1000)
            if r.status_code in expected_status:
                return HealthCheckResult(name=name, status="up", latency_ms=elapsed, last_check_at=datetime.utcnow())
            return HealthCheckResult(
                name=name,
                status="degraded",
                latency_ms=elapsed,
                last_check_at=datetime.utcnow(),
                details=f"HTTP {r.status_code}",
            )
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return HealthCheckResult(
            name=name,
            status="down",
            latency_ms=elapsed,
            last_check_at=datetime.utcnow(),
            details=str(e)[:200],
        )


def _db_check(db: DBSession) -> HealthCheckResult:
    start = time.time()
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        elapsed = int((time.time() - start) * 1000)
        return HealthCheckResult(name="Neon Postgres", status="up", latency_ms=elapsed, last_check_at=datetime.utcnow())
    except Exception as e:
        return HealthCheckResult(
            name="Neon Postgres",
            status="down",
            latency_ms=None,
            last_check_at=datetime.utcnow(),
            details=str(e)[:200],
        )


@router.get("/health/external", response_model=ExternalHealthResponse)
def external_health(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    refresh: bool = Query(False),
):
    _ensure_super_admin(current_user)
    now = time.time()
    if not refresh and _HEALTH_CACHE["data"] is not None and (now - _HEALTH_CACHE["ts"]) < _HEALTH_TTL_S:
        return _HEALTH_CACHE["data"]

    services: List[HealthCheckResult] = []

    # Heroku BE app
    heroku_url = os.getenv("PROD_BACKEND_URL", "https://grasshopper-poc-api-25eae3fc7571.herokuapp.com/health")
    services.append(_http_check("Heroku · Backend API", heroku_url))

    # Netlify FE
    netlify_url = os.getenv("PROD_FRONTEND_URL", "https://grasshopper-poc.netlify.app")
    services.append(_http_check("Netlify · Frontend", netlify_url))

    # DB
    services.append(_db_check(db))

    # Anthropic (HEAD on console domain · NOT api · we don't want to spend tokens or get auth-blocked)
    anthropic_url = "https://api.anthropic.com"
    services.append(_http_check("Anthropic API", anthropic_url, expected_status=(200, 401, 403, 404, 405)))

    # OpenAI
    openai_url = "https://api.openai.com/v1/models"
    services.append(_http_check("OpenAI API", openai_url, expected_status=(200, 401, 403)))

    # Bitrix CRM
    bitrix_url = os.getenv("BITRIX_BASE_URL")
    if bitrix_url:
        services.append(_http_check("Bitrix CRM", bitrix_url, expected_status=(200, 401, 403, 404, 405)))
    else:
        services.append(
            HealthCheckResult(
                name="Bitrix CRM",
                status="degraded",
                latency_ms=None,
                last_check_at=datetime.utcnow(),
                details="BITRIX_BASE_URL not configured",
            )
        )

    payload = ExternalHealthResponse(
        services=services,
        cached_until=datetime.utcnow() + timedelta(seconds=_HEALTH_TTL_S),
    )
    _HEALTH_CACHE["data"] = payload
    _HEALTH_CACHE["ts"] = now
    return payload


# --------------------------------------------------------------------------- #
# Bloque J · AI cost ledger                                                   #
# --------------------------------------------------------------------------- #

class AICostBreakdownItem(BaseModel):
    key: str
    tokens_input: int
    tokens_output: int
    cost_usd: float
    calls: int


class AICostsResponse(BaseModel):
    range_from: datetime
    range_to: datetime
    total_calls: int
    total_tokens_input: int
    total_tokens_output: int
    total_cost_usd: float
    by_provider: List[AICostBreakdownItem]
    by_model: List[AICostBreakdownItem]
    by_feature: List[AICostBreakdownItem]
    daily: List[Dict[str, float]]
    top_users: List[Dict[str, object]]


def _agg_breakdown(db: DBSession, group_col, frm: datetime, to: datetime) -> List[AICostBreakdownItem]:
    rows = (
        db.query(
            group_col.label("k"),
            func.coalesce(func.sum(AIUsageLog.tokens_input), 0).label("tin"),
            func.coalesce(func.sum(AIUsageLog.tokens_output), 0).label("tout"),
            func.coalesce(func.sum(AIUsageLog.cost_usd), 0).label("cost"),
            func.count(AIUsageLog.id).label("calls"),
        )
        .filter(AIUsageLog.created_at >= frm, AIUsageLog.created_at <= to)
        .group_by(group_col)
        .order_by(func.coalesce(func.sum(AIUsageLog.cost_usd), 0).desc())
        .all()
    )
    return [
        AICostBreakdownItem(
            key=r.k or "unknown",
            tokens_input=int(r.tin or 0),
            tokens_output=int(r.tout or 0),
            cost_usd=float(r.cost or 0),
            calls=int(r.calls or 0),
        )
        for r in rows
    ]


@router.get("/integrations/ai-costs", response_model=AICostsResponse)
def ai_costs(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = Query(30, ge=1, le=180),
):
    _ensure_super_admin(current_user)
    to = datetime.utcnow()
    frm = to - timedelta(days=days)

    by_provider = _agg_breakdown(db, AIUsageLog.provider, frm, to)
    by_model = _agg_breakdown(db, AIUsageLog.model, frm, to)
    by_feature = _agg_breakdown(db, AIUsageLog.feature, frm, to)

    total_calls = sum(b.calls for b in by_provider)
    total_in = sum(b.tokens_input for b in by_provider)
    total_out = sum(b.tokens_output for b in by_provider)
    total_cost = sum(b.cost_usd for b in by_provider)

    # daily timeseries
    daily_rows = (
        db.query(
            func.date(AIUsageLog.created_at).label("d"),
            func.coalesce(func.sum(AIUsageLog.cost_usd), 0).label("cost"),
            func.count(AIUsageLog.id).label("calls"),
        )
        .filter(AIUsageLog.created_at >= frm, AIUsageLog.created_at <= to)
        .group_by(func.date(AIUsageLog.created_at))
        .order_by(func.date(AIUsageLog.created_at))
        .all()
    )
    daily = [{"date": str(r.d), "cost_usd": float(r.cost or 0), "calls": int(r.calls or 0)} for r in daily_rows]

    # top users
    top_rows = (
        db.query(
            AIUsageLog.user_id,
            func.coalesce(func.sum(AIUsageLog.cost_usd), 0).label("cost"),
            func.count(AIUsageLog.id).label("calls"),
        )
        .filter(AIUsageLog.created_at >= frm, AIUsageLog.user_id.isnot(None))
        .group_by(AIUsageLog.user_id)
        .order_by(func.coalesce(func.sum(AIUsageLog.cost_usd), 0).desc())
        .limit(10)
        .all()
    )
    user_ids = {r.user_id for r in top_rows if r.user_id}
    email_map = {}
    if user_ids:
        for u in db.query(User.id, User.email).filter(User.id.in_(user_ids)).all():
            email_map[u.id] = u.email
    top_users = [
        {
            "user_id": str(r.user_id),
            "email": email_map.get(r.user_id),
            "cost_usd": float(r.cost or 0),
            "calls": int(r.calls or 0),
        }
        for r in top_rows
    ]

    return AICostsResponse(
        range_from=frm,
        range_to=to,
        total_calls=total_calls,
        total_tokens_input=total_in,
        total_tokens_output=total_out,
        total_cost_usd=total_cost,
        by_provider=by_provider,
        by_model=by_model,
        by_feature=by_feature,
        daily=daily,
        top_users=top_users,
    )


# --------------------------------------------------------------------------- #
# Bloque K · error log dashboard                                              #
# --------------------------------------------------------------------------- #

class ErrorGroupOut(BaseModel):
    exception_type: Optional[str]
    count: int
    last_seen_at: datetime
    last_message: Optional[str] = None
    last_path: Optional[str] = None


class ErrorLogResponse(BaseModel):
    range_from: datetime
    range_to: datetime
    total: int
    groups: List[ErrorGroupOut]


@router.get("/health/errors", response_model=ErrorLogResponse)
def health_errors(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = Query(7, ge=1, le=90),
    only_unresolved: bool = Query(True),
):
    _ensure_super_admin(current_user)
    to = datetime.utcnow()
    frm = to - timedelta(days=days)
    qry = db.query(ErrorLog).filter(ErrorLog.created_at >= frm)
    if only_unresolved:
        qry = qry.filter(ErrorLog.resolved_at.is_(None))

    total = qry.count()

    rows = (
        db.query(
            ErrorLog.exception_type,
            func.count(ErrorLog.id).label("c"),
            func.max(ErrorLog.created_at).label("last_seen"),
        )
        .filter(ErrorLog.created_at >= frm)
        .filter(ErrorLog.resolved_at.is_(None) if only_unresolved else True)
        .group_by(ErrorLog.exception_type)
        .order_by(func.count(ErrorLog.id).desc())
        .limit(50)
        .all()
    )
    groups: List[ErrorGroupOut] = []
    for r in rows:
        latest = (
            db.query(ErrorLog)
            .filter(ErrorLog.exception_type == r.exception_type, ErrorLog.created_at >= frm)
            .order_by(ErrorLog.created_at.desc())
            .first()
        )
        groups.append(
            ErrorGroupOut(
                exception_type=r.exception_type,
                count=int(r.c),
                last_seen_at=r.last_seen,
                last_message=latest.message if latest else None,
                last_path=latest.path if latest else None,
            )
        )

    return ErrorLogResponse(range_from=frm, range_to=to, total=total, groups=groups)


@router.post("/health/errors/{error_id}/resolve")
def resolve_error(
    error_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    e = db.query(ErrorLog).filter(ErrorLog.id == error_id).first()
    if not e:
        raise HTTPException(404, "Error log not found")
    e.resolved_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "resolved_at": e.resolved_at}


# --------------------------------------------------------------------------- #
# Bloque L · usage stats by role                                              #
# --------------------------------------------------------------------------- #

class UsageStatsResponse(BaseModel):
    dau_by_role: Dict[str, int]
    wau_by_role: Dict[str, int]
    mau_by_role: Dict[str, int]
    funnel: Dict[str, int]
    retention_cohort: Dict[str, float]


@router.get("/stats/usage", response_model=UsageStatsResponse)
def stats_usage(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    now = datetime.utcnow()
    day = now - timedelta(days=1)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)

    def _by_role(since: datetime) -> Dict[str, int]:
        rows = (
            db.query(User.role, func.count(User.id))
            .filter(User.last_login_at >= since)
            .group_by(User.role)
            .all()
        )
        out = {role.value: 0 for role in UserRole}
        for r, c in rows:
            out[r.value if hasattr(r, "value") else str(r)] = int(c or 0)
        return out

    dau = _by_role(day)
    wau = _by_role(week)
    mau = _by_role(month)

    # Funnel · counts of students that crossed each milestone
    students = db.query(User).filter(User.role == UserRole.STUDENT)
    total_students = students.count()
    onboarded = students.filter(User.onboarding_status.in_(["in_progress", "completed"])).count()
    completed_onboarding = students.filter(User.onboarding_status == "completed").count()
    test_done = (
        db.query(func.count(func.distinct(VocationalTestResult.user_id))).scalar() or 0
    )
    routes_done = (
        db.query(func.count(func.distinct(User.id)))
        .filter(User.id.in_(db.query(VocationalTestResult.user_id)))
        .scalar()
        or 0
    )
    funnel = {
        "registered": total_students,
        "onboarding_started": onboarded,
        "onboarding_completed": completed_onboarding,
        "any_test_completed": int(test_done),
        "routes_generated": int(routes_done),
    }

    # Retention proxy: % of users registered in last 4 weeks who logged in last 7 days
    cohort_28 = students.filter(User.created_at >= now - timedelta(days=28)).count()
    cohort_28_active_7 = students.filter(
        and_(User.created_at >= now - timedelta(days=28), User.last_login_at >= week)
    ).count()
    cohort_84 = students.filter(User.created_at >= now - timedelta(days=84)).count()
    cohort_84_active_30 = students.filter(
        and_(User.created_at >= now - timedelta(days=84), User.last_login_at >= month)
    ).count()
    retention_cohort = {
        "w4_active_w1_pct": round((cohort_28_active_7 / cohort_28 * 100) if cohort_28 else 0.0, 1),
        "w12_active_m1_pct": round((cohort_84_active_30 / cohort_84 * 100) if cohort_84 else 0.0, 1),
    }

    return UsageStatsResponse(
        dau_by_role=dau, wau_by_role=wau, mau_by_role=mau, funnel=funnel, retention_cohort=retention_cohort
    )
