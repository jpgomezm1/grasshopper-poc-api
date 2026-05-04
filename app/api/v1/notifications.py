"""Notifications + push subscriptions + daily/weekly preview routers.

GH-COMMPROD-A1/A2/A3 · gh_commercial productivity sprint.

Surfaces:

    GET    /api/v1/notifications/me?status=unread|all&page&page_size
    PATCH  /api/v1/notifications/{id}/read
    PATCH  /api/v1/notifications/read-all
    POST   /api/v1/notifications/me/push-subscriptions
    GET    /api/v1/notifications/me/push-subscriptions
    DELETE /api/v1/notifications/me/push-subscriptions/{id}
    POST   /api/v1/notifications/me/daily-summary/preview
    POST   /api/v1/notifications/me/weekly-report/preview
    POST   /api/v1/notifications/_jobs/daily-summary    · stub trigger (super_admin)
    POST   /api/v1/notifications/_jobs/weekly-report    · stub trigger (super_admin)
    POST   /api/v1/notifications/_jobs/sla-sweep        · stub trigger (super_admin)
    POST   /api/v1/notifications/_jobs/task-due-sweep   · stub trigger (super_admin)
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, UserRole
from app.schemas.notifications import (
    DailySummaryPreview,
    MarkReadResponse,
    NotificationItem,
    NotificationListResponse,
    PushSubscriptionCreate,
    PushSubscriptionItem,
)
from app.services import commercial_service, notifications_service, sla_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


@router.get("/me", response_model=NotificationListResponse)
def list_my_notifications(
    status_filter: str = Query("all", regex="^(all|unread)$", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return notifications_service.list_for_user(
        db, user=current_user, status=status_filter, page=page, page_size=page_size
    )


@router.patch("/{notification_id}/read", response_model=MarkReadResponse)
def mark_one_read(
    notification_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    unread = notifications_service.mark_read(
        db, user=current_user, notification_id=notification_id
    )
    return {"ok": True, "unread": unread}


@router.patch("/read-all", response_model=MarkReadResponse)
def mark_all_read(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notifications_service.mark_all_read(db, user=current_user)
    return {"ok": True, "unread": 0}


# ---------------------------------------------------------------------------
# Push subscriptions
# ---------------------------------------------------------------------------


@router.post(
    "/me/push-subscriptions",
    response_model=PushSubscriptionItem,
    status_code=status.HTTP_201_CREATED,
)
def create_push_subscription(
    body: PushSubscriptionCreate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = notifications_service.upsert_push_subscription(
        db,
        user=current_user,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=body.user_agent,
    )
    return sub


@router.get("/me/push-subscriptions", response_model=list[PushSubscriptionItem])
def list_my_push_subscriptions(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return notifications_service.list_push_subscriptions(db, user=current_user)


@router.delete(
    "/me/push-subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_push_subscription(
    subscription_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ok = notifications_service.delete_push_subscription(
        db, user=current_user, subscription_id=subscription_id
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="subscription not found"
        )


# ---------------------------------------------------------------------------
# Daily / weekly preview
# ---------------------------------------------------------------------------


@router.post("/me/daily-summary/preview", response_model=DailySummaryPreview)
def preview_my_daily_summary(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return notifications_service.build_daily_summary(db, user=current_user)


@router.post("/me/weekly-report/preview")
def preview_my_weekly_report(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return notifications_service.build_weekly_report(db, user=current_user)


# ---------------------------------------------------------------------------
# Job stubs (super_admin only · would be triggered by Heroku Scheduler)
# ---------------------------------------------------------------------------


def _require_super_admin(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="super_admin only"
        )


@router.post("/_jobs/daily-summary")
def job_daily_summary(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    notified = notifications_service.run_daily_summary_job(db)
    return {"ok": True, "notified_users": notified}


@router.post("/_jobs/weekly-report")
def job_weekly_report(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    notified = notifications_service.run_weekly_report_job(db)
    return {"ok": True, "notified_users": notified}


@router.post("/_jobs/sla-sweep")
def job_sla_sweep(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    created = sla_service.evaluate_and_notify_breaches(db)
    return {"ok": True, "notifications_created": created}


@router.post("/_jobs/task-due-sweep")
def job_task_due_sweep(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    created = commercial_service.emit_task_due_soon_notifications(db)
    return {"ok": True, "notifications_created": created}
