"""SLA tracker · GH-COMMPROD-B4.

Pure functions to compute the SLA state of a lead. Never persists. The
notifications hook (`evaluate_and_notify_breaches`) creates an in-app
row on first transition from `ok|warning` to `breach`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.db.models import Notification, User

logger = logging.getLogger(__name__)


SlaState = str  # "ok" | "warning" | "breach"


@dataclass
class SlaInfo:
    state: SlaState
    days_in_status: int
    threshold_hours: int
    elapsed_hours: int


def evaluate(user: User, *, now: Optional[datetime] = None) -> SlaInfo:
    """Compute SLA state for a single lead.

    Returns "ok" when no pipeline status set, the lead is converted/declined,
    or there's no status_at timestamp yet.
    """
    settings = get_settings()
    now = now or datetime.utcnow()
    status = (user.lead_pipeline_status or "").lower()
    status_at = user.lead_pipeline_status_at or user.created_at or now

    if status not in ("pending", "contacted", "qualified"):
        delta = now - (status_at or now)
        return SlaInfo(state="ok", days_in_status=delta.days, threshold_hours=0, elapsed_hours=int(delta.total_seconds() // 3600))

    if status == "pending":
        threshold_h = settings.sla_pending_breach_hours
    elif status == "contacted":
        threshold_h = settings.sla_contacted_breach_days * 24
    else:  # qualified
        threshold_h = settings.sla_qualified_breach_days * 24

    elapsed_h = int((now - status_at).total_seconds() // 3600)
    days_in = max(0, (now - status_at).days)

    if elapsed_h >= threshold_h:
        state = "breach"
    elif elapsed_h >= int(threshold_h * 0.7):
        state = "warning"
    else:
        state = "ok"

    return SlaInfo(
        state=state,
        days_in_status=days_in,
        threshold_hours=threshold_h,
        elapsed_hours=elapsed_h,
    )


def evaluate_and_notify_breaches(db: DBSession) -> int:
    """Sweep open leads · create lead.sla_breach notifications for new breaches.

    De-duplicates by checking that no lead.sla_breach notification exists
    for that user in the last 24h. Returns count of notifications created.
    """
    from app.services.notifications_service import create_notification

    now = datetime.utcnow()
    leads = (
        db.query(User)
        .filter(
            User.lead_pipeline_status.in_(["pending", "contacted", "qualified"]),
            User.assigned_to_user_id.isnot(None),
        )
        .all()
    )

    created = 0
    cutoff = now - timedelta(hours=24)
    for lead in leads:
        info = evaluate(lead, now=now)
        if info.state != "breach":
            continue
        # Skip if we already notified the assignee in last 24h about this lead
        recent = (
            db.query(Notification.id)
            .filter(
                Notification.user_id == lead.assigned_to_user_id,
                Notification.type == "lead.sla_breach",
                Notification.created_at > cutoff,
                # filter same lead via JSON data is best-effort · we filter by title containing the user_id
                Notification.title.contains(str(lead.id)[:8]),
            )
            .first()
        )
        if recent is not None:
            continue
        title = f"SLA en riesgo · {lead.name or lead.email} ({str(lead.id)[:8]})"
        body = (
            f"El lead lleva {info.days_in_status} días en estado "
            f"`{lead.lead_pipeline_status}` · supera el umbral configurado."
        )
        create_notification(
            db,
            user_id=lead.assigned_to_user_id,
            type="lead.sla_breach",
            title=title,
            body=body,
            data={
                "lead_user_id": str(lead.id),
                "pipeline_status": lead.lead_pipeline_status,
                "elapsed_hours": info.elapsed_hours,
                "threshold_hours": info.threshold_hours,
                "navigate_to": f"/admin/crm/leads/{lead.id}",
            },
            commit=False,
        )
        created += 1

    if created > 0:
        db.commit()
    return created
