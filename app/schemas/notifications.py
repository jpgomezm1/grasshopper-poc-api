"""Pydantic schemas for notifications + push subscriptions + daily summary.

GH-COMMPROD-A1/A2/A3 · Sprint gh_commercial productivity 2026-05-03.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Whitelisted notification types · keep in sync with notifications_service
NotificationType = Literal[
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
]


class NotificationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    title: str
    body: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    read_at: Optional[datetime] = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: List[NotificationItem]
    total: int
    unread: int
    page: int
    page_size: int


class MarkReadResponse(BaseModel):
    ok: bool = True
    unread: int


# ---------------------------------------------------------------------------
# Push subscriptions
# ---------------------------------------------------------------------------


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=10)
    auth: str = Field(min_length=10)


class PushSubscriptionCreate(BaseModel):
    """Mirrors the browser PushSubscription.toJSON() shape."""
    endpoint: str = Field(min_length=10, max_length=2048)
    keys: PushSubscriptionKeys
    user_agent: Optional[str] = Field(default=None, max_length=255)


class PushSubscriptionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    endpoint: str
    user_agent: Optional[str] = None
    created_at: datetime
    last_used_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Daily summary preview
# ---------------------------------------------------------------------------


class DailySummaryRow(BaseModel):
    label: str
    value: int
    href: Optional[str] = None


class DailySummaryPreview(BaseModel):
    user_id: UUID
    user_name: Optional[str] = None
    user_email: str
    generated_at: datetime
    rows: List[DailySummaryRow]
    salutation: str
    closing: Optional[str] = None
