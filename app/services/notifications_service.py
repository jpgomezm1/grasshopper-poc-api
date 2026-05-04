"""Notification service · GH-COMMPROD-A1/A2/A3.

Centralizes the in-app notification creation pipeline. Other services
(crm_service, tasks_service, comments_service, sla_service) call
`create_notification(...)` whenever a relevant event happens.

Web Push fan-out is best-effort and lives in `_dispatch_push`. If
`pywebpush` isn't installed (legacy environments / CI) the fan-out
is a no-op · the in-app row still persists.

Daily / weekly summary helpers live here too · they're pure data
producers consumed by:
    POST /api/v1/notifications/me/daily-summary/preview
    POST /api/v1/notifications/me/weekly-report/preview
and a future Heroku Scheduler stub.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, func
from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    Notification,
    PushSubscription,
    Task,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Whitelisted notification types (mirrors schemas.notifications.NotificationType)
# ---------------------------------------------------------------------------

NOTIFICATION_TYPES = frozenset({
    "lead.assigned",
    "lead.journey_progress",
    "lead.contact_request",
    "lead.pipeline_changed",
    "lead.sla_breach",
    "lead.mention",
    "task.due_soon",
    "task.created",
    "comment.mention",
    "system.daily_summary",
    "system.weekly_report",
})


# ---------------------------------------------------------------------------
# Core creation
# ---------------------------------------------------------------------------


def create_notification(
    db: DBSession,
    *,
    user_id: UUID,
    type: str,
    title: str,
    body: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    commit: bool = True,
    dispatch_push: bool = True,
) -> Notification:
    """Persist a notification row + best-effort push fan-out.

    `commit=False` to fold into an outer transaction (caller commits).
    """
    if type not in NOTIFICATION_TYPES:
        logger.warning("notifications · unknown type `%s` (still stored)", type)

    row = Notification(
        user_id=user_id,
        type=type,
        title=title[:255],
        body=body,
        data=data or None,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()

    if dispatch_push:
        try:
            _dispatch_push(db, user_id=user_id, title=title, body=body, data=data)
        except Exception as exc:  # pragma: no cover · best-effort
            logger.warning("notifications · push dispatch failed · %s", exc)

    return row


def fan_out(
    db: DBSession,
    *,
    user_ids: Sequence[UUID],
    type: str,
    title: str,
    body: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> int:
    """Create the same notification for many users · returns count created."""
    count = 0
    for uid in user_ids:
        if uid is None:
            continue
        create_notification(
            db,
            user_id=uid,
            type=type,
            title=title,
            body=body,
            data=data,
            commit=False,
        )
        count += 1
    if count > 0:
        db.commit()
    return count


# ---------------------------------------------------------------------------
# Inbox queries
# ---------------------------------------------------------------------------


def list_for_user(
    db: DBSession,
    *,
    user: User,
    status: str = "all",
    page: int = 1,
    page_size: int = 25,
) -> Dict[str, Any]:
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if status == "unread":
        q = q.filter(Notification.read_at.is_(None))
    total = q.count()
    unread = (
        db.query(func.count(Notification.id))
        .filter(
            Notification.user_id == user.id,
            Notification.read_at.is_(None),
        )
        .scalar()
        or 0
    )
    rows = (
        q.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": rows,
        "total": total,
        "unread": int(unread),
        "page": page,
        "page_size": page_size,
    }


def mark_read(db: DBSession, *, user: User, notification_id: UUID) -> int:
    row = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
        .first()
    )
    if row is None:
        return _unread_count(db, user)
    if row.read_at is None:
        row.read_at = datetime.utcnow()
        db.commit()
    return _unread_count(db, user)


def mark_all_read(db: DBSession, *, user: User) -> int:
    db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.read_at.is_(None),
    ).update({Notification.read_at: datetime.utcnow()}, synchronize_session=False)
    db.commit()
    return 0


def _unread_count(db: DBSession, user: User) -> int:
    return int(
        db.query(func.count(Notification.id))
        .filter(
            Notification.user_id == user.id,
            Notification.read_at.is_(None),
        )
        .scalar()
        or 0
    )


# ---------------------------------------------------------------------------
# Push subscriptions
# ---------------------------------------------------------------------------


def upsert_push_subscription(
    db: DBSession,
    *,
    user: User,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: Optional[str] = None,
) -> PushSubscription:
    existing = (
        db.query(PushSubscription)
        .filter(PushSubscription.endpoint == endpoint)
        .first()
    )
    if existing is not None:
        existing.user_id = user.id
        existing.p256dh = p256dh
        existing.auth = auth
        existing.user_agent = user_agent or existing.user_agent
        existing.last_used_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    row = PushSubscription(
        user_id=user.id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        user_agent=user_agent,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_push_subscriptions(db: DBSession, *, user: User) -> List[PushSubscription]:
    return (
        db.query(PushSubscription)
        .filter(PushSubscription.user_id == user.id)
        .order_by(PushSubscription.created_at.desc())
        .all()
    )


def delete_push_subscription(
    db: DBSession, *, user: User, subscription_id: UUID
) -> bool:
    row = (
        db.query(PushSubscription)
        .filter(
            PushSubscription.id == subscription_id,
            PushSubscription.user_id == user.id,
        )
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def _dispatch_push(
    db: DBSession,
    *,
    user_id: UUID,
    title: str,
    body: Optional[str],
    data: Optional[Dict[str, Any]],
) -> None:
    """Best-effort web push fan-out · no-op when pywebpush unavailable."""
    try:
        from pywebpush import webpush, WebPushException  # type: ignore
    except Exception:
        # pywebpush is optional · gracefully skip in dev/CI without VAPID keys
        return

    from app.config import get_settings

    settings = get_settings()
    vapid_private = getattr(settings, "vapid_private_key", "") or ""
    vapid_subject = getattr(settings, "vapid_subject", "mailto:ops@grasshopper.app")
    if not vapid_private:
        return

    subs = (
        db.query(PushSubscription)
        .filter(PushSubscription.user_id == user_id)
        .all()
    )
    if not subs:
        return

    payload = json.dumps({
        "title": title,
        "body": body or "",
        "data": data or {},
    })

    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=vapid_private,
                vapid_claims={"sub": vapid_subject},
                ttl=3600,
            )
            sub.last_used_at = datetime.utcnow()
            db.add(sub)
        except WebPushException as exc:  # pragma: no cover
            # 410 / 404 → endpoint expired · drop the row
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in (404, 410):
                db.delete(sub)
            else:
                logger.warning("push · dispatch failed · %s", exc)
        except Exception as exc:  # pragma: no cover
            logger.warning("push · unexpected error · %s", exc)
    db.commit()


# ---------------------------------------------------------------------------
# Daily summary / weekly report
# ---------------------------------------------------------------------------


def build_daily_summary(db: DBSession, *, user: User) -> Dict[str, Any]:
    """Compose the data for an end-of-day summary email.

    Pure read · no side effects.
    """
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    # Tasks due today
    tasks_today = (
        db.query(func.count(Task.id))
        .filter(
            Task.assigned_to_user_id == user.id,
            Task.status == "open",
            Task.due_at >= today,
            Task.due_at < tomorrow,
        )
        .scalar()
        or 0
    )

    tasks_overdue = (
        db.query(func.count(Task.id))
        .filter(
            Task.assigned_to_user_id == user.id,
            Task.status == "open",
            Task.due_at < today,
        )
        .scalar()
        or 0
    )

    leads_assigned_pending = (
        db.query(func.count(User.id))
        .filter(
            User.assigned_to_user_id == user.id,
            User.lead_pipeline_status.in_(["pending", "contacted"]),
        )
        .scalar()
        or 0
    )

    rows = [
        {"label": "Leads pendientes de acción", "value": int(leads_assigned_pending), "href": "/admin/crm/leads?assigned=me&pipeline_status=pending"},
        {"label": "Tareas para hoy", "value": int(tasks_today), "href": "/tasks?due=today"},
        {"label": "Tareas atrasadas", "value": int(tasks_overdue), "href": "/tasks?due=overdue"},
    ]

    return {
        "user_id": user.id,
        "user_name": user.name,
        "user_email": user.email,
        "generated_at": datetime.utcnow(),
        "rows": rows,
        "salutation": f"Tu día {user.name.split(' ')[0] if user.name else 'asesora'}",
        "closing": "Que tengas una excelente jornada.",
    }


def build_weekly_report(db: DBSession, *, user: User) -> Dict[str, Any]:
    """Weekly aggregation · used by /weekly-report/preview and the Monday job."""
    end = datetime.utcnow()
    start = end - timedelta(days=7)
    prev_start = start - timedelta(days=7)

    leads_handled = (
        db.query(func.count(User.id))
        .filter(
            User.assigned_to_user_id == user.id,
            User.assigned_at >= start,
        )
        .scalar()
        or 0
    )
    conversions = (
        db.query(func.count(User.id))
        .filter(
            User.assigned_to_user_id == user.id,
            User.lead_pipeline_status == "converted",
            User.lead_pipeline_status_at >= start,
        )
        .scalar()
        or 0
    )
    pending = (
        db.query(func.count(User.id))
        .filter(
            User.assigned_to_user_id == user.id,
            User.lead_pipeline_status.in_(["pending", "contacted"]),
        )
        .scalar()
        or 0
    )

    # Team ranking (anonymous-by-default)
    ranking = (
        db.query(
            User.assigned_to_user_id,
            func.count(User.id).label("converted_count"),
        )
        .filter(
            User.lead_pipeline_status == "converted",
            User.lead_pipeline_status_at >= start,
            User.assigned_to_user_id.isnot(None),
        )
        .group_by(User.assigned_to_user_id)
        .order_by(func.count(User.id).desc())
        .all()
    )
    rank = None
    rank_total = len(ranking)
    for idx, row in enumerate(ranking, start=1):
        if row.assigned_to_user_id == user.id:
            rank = idx
            break

    return {
        "user_id": str(user.id),
        "user_name": user.name,
        "user_email": user.email,
        "generated_at": datetime.utcnow().isoformat(),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "leads_handled": int(leads_handled),
        "conversions": int(conversions),
        "pending": int(pending),
        "rank": rank,
        "rank_total": rank_total,
    }


# ---------------------------------------------------------------------------
# Heroku Scheduler stub helpers
# ---------------------------------------------------------------------------


def run_daily_summary_job(db: DBSession) -> int:
    """Stub: would be called by Heroku Scheduler · 7am COL.

    Iterates gh_commercial / gh_advisor users + creates an in-app
    notification with the day-ahead summary. Returns count of users
    notified.
    """
    targets = (
        db.query(User)
        .filter(User.role.in_([UserRole.GH_COMMERCIAL, UserRole.GH_ADVISOR]))
        .filter(User.is_active.is_(True))
        .all()
    )
    notified = 0
    for u in targets:
        summary = build_daily_summary(db, user=u)
        title = "Resumen del día"
        body_lines = [
            f"{r['label']}: {r['value']}" for r in summary["rows"] if r["value"] > 0
        ]
        body = " · ".join(body_lines) if body_lines else "Día tranquilo · sin pendientes."
        create_notification(
            db,
            user_id=u.id,
            type="system.daily_summary",
            title=title,
            body=body,
            data={"rows": summary["rows"]},
            commit=False,
            dispatch_push=False,
        )
        notified += 1
    db.commit()
    return notified


def run_weekly_report_job(db: DBSession) -> int:
    """Stub: would be called by Heroku Scheduler · Monday 8am COL."""
    targets = (
        db.query(User)
        .filter(User.role.in_([UserRole.GH_COMMERCIAL, UserRole.GH_ADVISOR]))
        .filter(User.is_active.is_(True))
        .all()
    )
    notified = 0
    for u in targets:
        report = build_weekly_report(db, user=u)
        title = "Reporte semanal"
        body = (
            f"Semana: {report['leads_handled']} leads · "
            f"{report['conversions']} conversiones · "
            f"{report['pending']} pendientes"
        )
        if report.get("rank"):
            body += f" · ranking #{report['rank']} de {report['rank_total']}"
        create_notification(
            db,
            user_id=u.id,
            type="system.weekly_report",
            title=title,
            body=body,
            data=report,
            commit=False,
            dispatch_push=False,
        )
        notified += 1
    db.commit()
    return notified
