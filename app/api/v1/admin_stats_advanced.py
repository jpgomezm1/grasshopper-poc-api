"""Admin advanced stats · Bloque C · Sprint super_admin fixes 2026-05-03.

Issue 4 BITACORA_TESTING.md · "Estadísticas insuficiente · falta funnel +
cohort + exports". Ofrece KPIs derivados con date range global + exports
multi-formato (xlsx · csv · json · pdf-stub).

Endpoints (super_admin only):
    GET /admin/stats/funnel?from=&to=
    GET /admin/stats/timeseries?metric=&from=&to=&interval=
    GET /admin/stats/cohorts?metric=retention&months=6
    GET /admin/stats/lead-scores?limit=
    GET /admin/stats/export?format=xlsx&dataset=funnel|timeseries|leads&from=&to=

Time series intervals: day · week · month. Defaults: last 30 days · day.
PDF format · ReportLab not in requirements yet; we return a minimal HTML
fallback wrapped in `text/html` and let the browser print → user can print
to PDF. This keeps the surface useful without bloating dependencies.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import (
    ConsolidatedProfileCache,
    Report,
    School,
    Session as JourneySession,
    User,
    UserRole,
    VocationalTestResult,
)
from app.services.student_lead_scoring import score_students_for_school


router = APIRouter(prefix="/admin/stats", tags=["AdminStatsAdvanced"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ensure_super_admin(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only super_admin can access stats.",
        )


def _resolve_range(
    since: Optional[datetime], until: Optional[datetime], default_days: int = 30
) -> tuple[datetime, datetime]:
    now = datetime.utcnow()
    end = until or now
    start = since or (end - timedelta(days=default_days))
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`from` must be <= `to`",
        )
    if (end - start).days > 730:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Range too large · max 2 years",
        )
    return start, end


def _trunc_unit(interval: str) -> str:
    if interval == "day":
        return "day"
    if interval == "week":
        return "week"
    if interval == "month":
        return "month"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="interval must be one of day · week · month",
    )


# ---------------------------------------------------------------------------
# funnel
# ---------------------------------------------------------------------------


@router.get(
    "/funnel",
    summary="Bloque C · journey funnel from onboarding to PDF download",
)
def stats_funnel(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    since: Optional[datetime] = Query(None, alias="from"),
    until: Optional[datetime] = Query(None, alias="to"),
):
    _ensure_super_admin(current_user)
    start, end = _resolve_range(since, until)
    return _funnel_payload(db, start, end)


# ---------------------------------------------------------------------------
# time series
# ---------------------------------------------------------------------------


def _build_timeseries(
    db: DBSession,
    metric: str,
    start: datetime,
    end: datetime,
    interval: str,
) -> List[Dict[str, Any]]:
    unit = _trunc_unit(interval)
    if metric == "users_created":
        col = User.created_at
        q = (
            db.query(
                func.date_trunc(unit, col).label("bucket"),
                func.count(User.id).label("v"),
            )
            .filter(
                User.role == UserRole.STUDENT,
                col >= start,
                col <= end,
            )
            .group_by("bucket")
            .order_by("bucket")
        )
    elif metric == "tests_completed":
        col = VocationalTestResult.created_at
        q = (
            db.query(
                func.date_trunc(unit, col).label("bucket"),
                func.count(VocationalTestResult.id).label("v"),
            )
            .filter(col >= start, col <= end)
            .group_by("bucket")
            .order_by("bucket")
        )
    elif metric == "reports_generated":
        col = Report.created_at
        q = (
            db.query(
                func.date_trunc(unit, col).label("bucket"),
                func.count(Report.id).label("v"),
            )
            .filter(col >= start, col <= end)
            .group_by("bucket")
            .order_by("bucket")
        )
    elif metric == "active_sessions":
        col = JourneySession.updated_at
        q = (
            db.query(
                func.date_trunc(unit, col).label("bucket"),
                func.count(JourneySession.user_id.distinct()).label("v"),
            )
            .filter(col >= start, col <= end)
            .group_by("bucket")
            .order_by("bucket")
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "metric must be one of: users_created, tests_completed, "
                "reports_generated, active_sessions"
            ),
        )

    return [
        {"bucket": b.isoformat() if b else None, "value": int(v or 0)}
        for b, v in q.all()
    ]


@router.get(
    "/timeseries",
    summary="Bloque C · time series for a single metric",
)
def stats_timeseries(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    metric: str = Query(...),
    since: Optional[datetime] = Query(None, alias="from"),
    until: Optional[datetime] = Query(None, alias="to"),
    interval: str = Query("day"),
):
    _ensure_super_admin(current_user)
    start, end = _resolve_range(since, until)
    points = _build_timeseries(db, metric, start, end, interval)
    return {
        "metric": metric,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "interval": interval,
        "points": points,
    }


# ---------------------------------------------------------------------------
# cohorts (signup month vs activity month)
# ---------------------------------------------------------------------------


@router.get(
    "/cohorts",
    summary="Bloque C · monthly retention cohort heatmap",
)
def stats_cohorts(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    months: int = Query(6, ge=1, le=24),
):
    _ensure_super_admin(current_user)
    end = datetime.utcnow()
    start = end - timedelta(days=months * 31)

    # Signup cohort = month of users.created_at; activity month = month of
    # session.updated_at. We rely on date_trunc for portability.
    rows = (
        db.query(
            func.date_trunc("month", User.created_at).label("cohort"),
            func.date_trunc("month", JourneySession.updated_at).label(
                "activity"
            ),
            func.count(User.id.distinct()).label("v"),
        )
        .join(JourneySession, JourneySession.user_id == User.id)
        .filter(
            User.role == UserRole.STUDENT,
            User.created_at >= start,
            User.created_at <= end,
            JourneySession.updated_at <= end,
        )
        .group_by("cohort", "activity")
        .order_by("cohort", "activity")
        .all()
    )
    by_cohort: Dict[str, Dict[str, int]] = {}
    for cohort, activity, v in rows:
        if not cohort or not activity:
            continue
        c = cohort.strftime("%Y-%m")
        a = activity.strftime("%Y-%m")
        by_cohort.setdefault(c, {})[a] = int(v or 0)

    return {
        "months": months,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "cohorts": by_cohort,
    }


# ---------------------------------------------------------------------------
# lead scores aggregate (across all schools · top N)
# ---------------------------------------------------------------------------


@router.get(
    "/lead-scores",
    summary="Bloque C · top scored students across the portfolio (super_admin)",
)
def stats_lead_scores(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=500),
):
    _ensure_super_admin(current_user)
    return _leads_payload(db, limit=limit)


# ---------------------------------------------------------------------------
# exports (csv · xlsx · json · html-printable)
# ---------------------------------------------------------------------------


def _funnel_to_rows(payload: Dict[str, Any]) -> List[List[Any]]:
    out = [["stage_id", "label", "count", "pct_of_top"]]
    for st in payload["stages"]:
        out.append([st["id"], st["label"], st["count"], st["pct_of_top"]])
    return out


def _timeseries_to_rows(payload: Dict[str, Any]) -> List[List[Any]]:
    out = [["bucket", "value", "metric"]]
    for p in payload["points"]:
        out.append([p["bucket"], p["value"], payload["metric"]])
    return out


def _leads_to_rows(payload: Dict[str, Any]) -> List[List[Any]]:
    out = [
        [
            "school_id",
            "school_name",
            "email",
            "name",
            "score",
            "score_band",
            "journey_progress",
            "tests_completed",
            "rationale",
        ]
    ]
    for it in payload["items"]:
        out.append(
            [
                it.get("school_id", ""),
                it.get("school_name", ""),
                it.get("email", ""),
                it.get("name", ""),
                it.get("score", 0),
                it.get("score_band", ""),
                it.get("journey_progress", 0),
                it.get("tests_completed", 0),
                it.get("rationale", ""),
            ]
        )
    return out


def _to_csv(rows: List[List[Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")


def _to_xlsx(rows: List[List[Any]], sheet_name: str = "Stats") -> bytes:
    try:
        from openpyxl import Workbook
    except ImportError:
        # B-021 (QA round 2): optional dep missing → 503, not 500. Same pattern
        # we use for other optional runtime deps (e.g. WeasyPrint / GTK).
        raise HTTPException(
            status_code=503,
            detail="openpyxl not installed on this deploy",
        )
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31] or "Stats"
    for r in rows:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _to_html_printable(title: str, rows: List[List[Any]]) -> bytes:
    """Minimal printable HTML · user prints-to-PDF from browser.

    Avoids adding ReportLab/WeasyPrint dependencies for the first iteration.
    """
    head = (
        "<html><head><meta charset='utf-8'><title>"
        + title
        + "</title>"
        + "<style>body{font-family:system-ui;margin:32px;color:#1a1a1a}"
        + "table{border-collapse:collapse;width:100%}"
        + "th,td{border:1px solid #e5e7eb;padding:6px 10px;font-size:12px}"
        + "th{background:#f3f4f6;text-align:left}"
        + "h1{font-size:18px;margin:0 0 16px 0}"
        + "</style></head><body><h1>"
        + title
        + "</h1><table>"
    )
    body = ""
    for i, r in enumerate(rows):
        tag = "th" if i == 0 else "td"
        body += "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in r) + "</tr>"
    return (head + body + "</table></body></html>").encode("utf-8")


def _funnel_payload(
    db: DBSession, start: datetime, end: datetime
) -> Dict[str, Any]:
    """Pure function variant of /admin/stats/funnel · used by export."""
    student_window = (
        db.query(User)
        .filter(
            User.role == UserRole.STUDENT,
            User.created_at >= start,
            User.created_at <= end,
        )
    )
    total_entered = student_window.count()
    if total_entered == 0:
        total_entered = (
            db.query(func.count(User.id.distinct()))
            .join(JourneySession, JourneySession.user_id == User.id)
            .filter(
                User.role == UserRole.STUDENT,
                JourneySession.updated_at >= start,
                JourneySession.updated_at <= end,
            )
            .scalar()
            or 0
        )
    started_journey = (
        db.query(func.count(User.id.distinct()))
        .join(JourneySession, JourneySession.user_id == User.id)
        .filter(
            User.role == UserRole.STUDENT,
            JourneySession.created_at >= start,
            JourneySession.created_at <= end,
        )
        .scalar()
        or 0
    )
    sessions_in_window = (
        db.query(JourneySession)
        .filter(
            JourneySession.updated_at >= start,
            JourneySession.updated_at <= end,
        )
        .all()
    )
    user_stage: Dict[str, int] = {}
    for s in sessions_in_window:
        if not s.user_id:
            continue
        steps = s.completed_steps or []
        n = len(steps) if isinstance(steps, list) else 0
        prev = user_stage.get(str(s.user_id), 0)
        cur = 4 if s.is_completed else min(3, max(0, n // 4))
        user_stage[str(s.user_id)] = max(prev, cur)
    phase_a = sum(1 for v in user_stage.values() if v >= 1)
    phase_b = sum(1 for v in user_stage.values() if v >= 2)
    phase_c = sum(1 for v in user_stage.values() if v >= 3)
    completed = sum(1 for v in user_stage.values() if v >= 4)
    profiles_in_window = (
        db.query(func.count(ConsolidatedProfileCache.id))
        .filter(
            ConsolidatedProfileCache.generated_at >= start,
            ConsolidatedProfileCache.generated_at <= end,
            ConsolidatedProfileCache.invalidated_at.is_(None),
        )
        .scalar()
        or 0
    )
    pdfs_in_window = (
        db.query(func.count(Report.id))
        .filter(
            Report.created_at >= start,
            Report.created_at <= end,
        )
        .scalar()
        or 0
    )
    stages = [
        {"id": "entered", "label": "Inscritos", "count": int(total_entered)},
        {"id": "started", "label": "Inició onboarding", "count": int(started_journey)},
        {"id": "phase_a", "label": "Completó Fase A", "count": int(phase_a)},
        {"id": "phase_b", "label": "Completó Fase B", "count": int(phase_b)},
        {"id": "phase_c", "label": "Completó Fase C", "count": int(phase_c)},
        {"id": "journey_done", "label": "Journey completo", "count": int(completed)},
        {"id": "profile", "label": "Perfil consolidado", "count": int(profiles_in_window)},
        {"id": "pdf", "label": "Reporte PDF generado", "count": int(pdfs_in_window)},
    ]
    top = max(1, stages[0]["count"])
    for st in stages:
        st["pct_of_top"] = round(100.0 * st["count"] / top, 1)
    drop_offs = []
    for i in range(1, len(stages)):
        prev = stages[i - 1]["count"] or 1
        cur = stages[i]["count"]
        drop_offs.append(
            {
                "from_id": stages[i - 1]["id"],
                "to_id": stages[i]["id"],
                "drop_pct": round(100.0 * (1.0 - cur / prev), 1) if prev else 0.0,
                "absolute": int(prev - cur),
            }
        )
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "stages": stages,
        "drop_offs": drop_offs,
    }


def _leads_payload(db: DBSession, limit: int = 200) -> Dict[str, Any]:
    schools = (
        db.query(School)
        .filter(School.archived_at.is_(None))
        .all()
    )
    rows: List[Dict[str, Any]] = []
    for s in schools:
        for r in score_students_for_school(db, s.id, limit=limit):
            rows.append(
                {
                    "school_id": str(s.id),
                    "school_name": s.name,
                    **r.model_dump(mode="json"),
                }
            )
    rows.sort(key=lambda x: x["score"], reverse=True)
    rows = rows[:limit]
    return {"items": rows, "total": len(rows)}


def _gather_dataset(
    db: DBSession, dataset: str, since: datetime, until: datetime
) -> tuple[Dict[str, Any], List[List[Any]], str]:
    if dataset == "funnel":
        payload = _funnel_payload(db, since, until)
        return payload, _funnel_to_rows(payload), "funnel"
    if dataset == "timeseries_users":
        points = _build_timeseries(db, "users_created", since, until, "day")
        payload = {
            "metric": "users_created",
            "from": since.isoformat(),
            "to": until.isoformat(),
            "points": points,
        }
        return payload, _timeseries_to_rows(payload), "timeseries_users"
    if dataset == "timeseries_tests":
        points = _build_timeseries(db, "tests_completed", since, until, "day")
        payload = {
            "metric": "tests_completed",
            "from": since.isoformat(),
            "to": until.isoformat(),
            "points": points,
        }
        return payload, _timeseries_to_rows(payload), "timeseries_tests"
    if dataset == "leads":
        payload = _leads_payload(db, limit=200)
        return payload, _leads_to_rows(payload), "leads"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="dataset must be funnel · timeseries_users · timeseries_tests · leads",
    )


@router.get(
    "/export",
    summary="Bloque C · export stats datasets in xlsx · csv · json · html",
)
def stats_export(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    fmt: str = Query("xlsx", alias="format"),
    dataset: str = Query("funnel"),
    since: Optional[datetime] = Query(None, alias="from"),
    until: Optional[datetime] = Query(None, alias="to"),
):
    _ensure_super_admin(current_user)
    start, end = _resolve_range(since, until, default_days=30)
    payload, rows, name = _gather_dataset(db, dataset, start, end)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base = f"grasshopper_{name}_{ts}"

    if fmt == "json":
        return Response(
            content=json.dumps(payload, default=str, ensure_ascii=False).encode(
                "utf-8"
            ),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{base}.json"'},
        )
    if fmt == "csv":
        return Response(
            content=_to_csv(rows),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{base}.csv"'},
        )
    if fmt == "xlsx":
        return Response(
            content=_to_xlsx(rows, sheet_name=name),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{base}.xlsx"'},
        )
    if fmt == "html":
        title = f"Grasshopper · {name} · {start.date()} → {end.date()}"
        return Response(
            content=_to_html_printable(title, rows),
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": f'inline; filename="{base}.html"'
            },
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="format must be one of: xlsx · csv · json · html",
    )
