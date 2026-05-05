"""Proactive alerts engine for super_admin · Bloque D.

Runs synchronous checks; idempotent on (type, target_type, target_id) while
the prior alert is unresolved. Designed to be invoked from a cron, a manual
"refresh" button in the admin UI, or whatever scheduler is wired in INFRA.

The engine writes to the `admin_alerts` table and returns a summary of what
was created during the run.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    AdminAlert,
    AdminAlertSeverity,
    ErrorLog,
    License,
    LicenseStatus,
    School,
    User,
    UserRole,
)


CHECK_TYPES = {
    "school.no_activity",
    "license.expiring",
    "errors.spike",
    "dau.drop",
    "ai.quota",
}


def _has_active_alert(db: DBSession, type_: str, target_type: Optional[str], target_id: Optional[str]) -> bool:
    return (
        db.query(AdminAlert.id)
        .filter(
            AdminAlert.type == type_,
            AdminAlert.target_type == target_type,
            AdminAlert.target_id == target_id,
            AdminAlert.resolved_at.is_(None),
        )
        .first()
        is not None
    )


def _create_alert(
    db: DBSession,
    *,
    type_: str,
    severity: str,
    title: str,
    body: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    data: Optional[dict] = None,
) -> AdminAlert:
    row = AdminAlert(
        id=uuid4(),
        type=type_,
        severity=severity,
        title=title,
        body=body,
        target_type=target_type,
        target_id=target_id,
        data=data,
    )
    db.add(row)
    db.flush()
    return row


def check_schools_no_activity(db: DBSession, *, days: int = 30) -> List[AdminAlert]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    out: List[AdminAlert] = []
    rows = (
        db.query(School)
        .filter(School.archived_at.is_(None))
        .all()
    )
    for school in rows:
        last_login = (
            db.query(func.max(User.last_login_at))
            .filter(User.school_id == school.id)
            .scalar()
        )
        if last_login is None or last_login < cutoff:
            if not _has_active_alert(db, "school.no_activity", "school", str(school.id)):
                out.append(
                    _create_alert(
                        db,
                        type_="school.no_activity",
                        severity=AdminAlertSeverity.WARNING.value,
                        title=f"Sin actividad · {school.name}",
                        body=f"Sin logins de usuarios del colegio en los últimos {days} días.",
                        target_type="school",
                        target_id=str(school.id),
                        data={"last_login_at": last_login.isoformat() if last_login else None},
                    )
                )
    return out


def check_licenses_expiring(db: DBSession) -> List[AdminAlert]:
    now = datetime.utcnow()
    horizons = [(7, AdminAlertSeverity.CRITICAL), (15, AdminAlertSeverity.WARNING), (30, AdminAlertSeverity.INFO)]
    out: List[AdminAlert] = []
    for days, severity in horizons:
        cutoff = now + timedelta(days=days)
        rows = (
            db.query(License)
            .filter(
                License.status == LicenseStatus.ACTIVE.value,
                License.expires_at.isnot(None),
                License.expires_at > now,
                License.expires_at <= cutoff,
            )
            .all()
        )
        for lic in rows:
            target_id = str(lic.id)
            type_key = f"license.expiring_{days}d"
            if not _has_active_alert(db, type_key, "license", target_id):
                out.append(
                    _create_alert(
                        db,
                        type_=type_key,
                        severity=severity.value,
                        title=f"Licencia por expirar en {days} días",
                        body=f"License {lic.id} expira el {lic.expires_at.isoformat()}.",
                        target_type="license",
                        target_id=target_id,
                        data={"expires_at": lic.expires_at.isoformat()},
                    )
                )
    return out


def check_errors_spike(db: DBSession, *, threshold: int = 10, window_minutes: int = 60) -> List[AdminAlert]:
    since = datetime.utcnow() - timedelta(minutes=window_minutes)
    count = (
        db.query(func.count(ErrorLog.id))
        .filter(ErrorLog.created_at >= since, ErrorLog.level == "error")
        .scalar()
        or 0
    )
    if count < threshold:
        return []
    if _has_active_alert(db, "errors.spike", "system", "error_log"):
        return []
    return [
        _create_alert(
            db,
            type_="errors.spike",
            severity=AdminAlertSeverity.CRITICAL.value,
            title=f"{count} errores 5xx en la última hora",
            body=f"Más de {threshold} errores en {window_minutes} min · revisa /admin/integrations/errors.",
            target_type="system",
            target_id="error_log",
            data={"count": int(count), "window_minutes": window_minutes},
        )
    ]


def check_dau_drop(db: DBSession) -> List[AdminAlert]:
    now = datetime.utcnow()
    last_7 = now - timedelta(days=7)
    prev_7 = now - timedelta(days=14)

    last_count = (
        db.query(func.count(func.distinct(User.id)))
        .filter(User.last_login_at >= last_7)
        .scalar()
        or 0
    )
    prev_count = (
        db.query(func.count(func.distinct(User.id)))
        .filter(User.last_login_at >= prev_7, User.last_login_at < last_7)
        .scalar()
        or 0
    )
    if prev_count == 0 or last_count >= prev_count * 0.8:
        return []
    if _has_active_alert(db, "dau.drop", "system", "weekly_active"):
        return []
    drop_pct = round((1 - (last_count / max(1, prev_count))) * 100, 1)
    return [
        _create_alert(
            db,
            type_="dau.drop",
            severity=AdminAlertSeverity.WARNING.value,
            title=f"Caída de actividad: -{drop_pct}% WoW",
            body=f"Usuarios activos esta semana: {last_count} · semana previa: {prev_count}.",
            target_type="system",
            target_id="weekly_active",
            data={"this_week": int(last_count), "prev_week": int(prev_count), "drop_pct": drop_pct},
        )
    ]


def check_ai_quota(db: DBSession, *, threshold_usd: float = 50.0) -> List[AdminAlert]:
    """Today's AI cost spike alert (heuristic · we don't poll provider quota)."""
    from app.db.models import AIUsageLog

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    cost_today = (
        db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0))
        .filter(AIUsageLog.created_at >= today_start)
        .scalar()
        or 0.0
    )
    cost_today_f = float(cost_today)
    if cost_today_f < threshold_usd:
        return []
    if _has_active_alert(db, "ai.quota", "system", "ai_costs_today"):
        return []
    return [
        _create_alert(
            db,
            type_="ai.quota",
            severity=AdminAlertSeverity.WARNING.value,
            title=f"Costo AI hoy: ${cost_today_f:.2f} USD",
            body=f"Cruzaste el umbral configurable (${threshold_usd:.2f} USD).",
            target_type="system",
            target_id="ai_costs_today",
            data={"cost_usd_today": cost_today_f, "threshold_usd": threshold_usd},
        )
    ]


def run_checks(db: DBSession) -> Dict[str, int]:
    """Run all checks · returns count per type created in this run."""
    summary: Dict[str, int] = {}
    for fn, key in (
        (check_schools_no_activity, "school.no_activity"),
        (check_licenses_expiring, "license.expiring"),
        (check_errors_spike, "errors.spike"),
        (check_dau_drop, "dau.drop"),
        (check_ai_quota, "ai.quota"),
    ):
        try:
            created = fn(db)
            summary[key] = len(created)
        except Exception as e:
            summary[key] = -1  # signal failure without raising
            summary[f"{key}_error"] = str(e)[:200]  # type: ignore[assignment]
    db.commit()
    return summary
