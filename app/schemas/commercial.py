"""Pydantic schemas for the commercial productivity sprint.

Includes:
    - Assignment / handoff
    - Tags (catalog + assignments)
    - Saved searches
    - Comments
    - Pipeline stages
    - Auto-assign + pipeline rules
    - Today dashboard
    - SLA badges
    - Performance analytics

GH-COMMPROD-B2/B5/B6 + D1/D3/D4 + E1/E2 + F1/F2 + I.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Assignment / handoff
# ---------------------------------------------------------------------------


class AssignBody(BaseModel):
    to_user_id: Optional[UUID] = None  # null → unassign
    note: Optional[str] = Field(default=None, max_length=1000)


class HandoffBody(BaseModel):
    to_user_id: UUID
    note: str = Field(min_length=2, max_length=1000)


class AssignmentResult(BaseModel):
    lead_user_id: UUID
    assigned_to_user_id: Optional[UUID] = None
    assigned_to_name: Optional[str] = None
    assigned_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class TagItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    label: str
    color: Optional[str] = None


class TagCreate(BaseModel):
    key: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9-]+$")
    label: str = Field(min_length=2, max_length=120)
    color: Optional[str] = Field(default=None, max_length=20)


class TagAssignBody(BaseModel):
    tag_ids: List[UUID] = Field(min_length=0)


class LeadTagsResponse(BaseModel):
    lead_user_id: UUID
    tags: List[TagItem]


# ---------------------------------------------------------------------------
# Saved searches
# ---------------------------------------------------------------------------


class SavedSearchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    filters: Dict[str, Any]
    pinned: bool = False


class SavedSearchPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    filters: Optional[Dict[str, Any]] = None
    pinned: Optional[bool] = None


class SavedSearchItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    filters: Dict[str, Any]
    pinned: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    parent_id: Optional[UUID] = None
    mentions: Optional[List[UUID]] = None  # author resolves @email -> ids in FE


class CommentPatch(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CommentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_user_id: UUID
    author_user_id: Optional[UUID] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    body: str
    mentions: Optional[List[UUID]] = None
    parent_id: Optional[UUID] = None
    created_at: datetime
    edited_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------


class PipelineStageItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    label: str
    color: Optional[str] = None
    order_index: int
    is_default: bool


class PipelineStageCreate(BaseModel):
    key: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=2, max_length=120)
    color: Optional[str] = Field(default=None, max_length=20)
    order_index: int = Field(ge=0, le=999)


class PipelineStagePatch(BaseModel):
    label: Optional[str] = Field(default=None, min_length=2, max_length=120)
    color: Optional[str] = Field(default=None, max_length=20)
    order_index: Optional[int] = Field(default=None, ge=0, le=999)


class PipelineStageReorder(BaseModel):
    order: List[UUID] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Auto-assign rules
# ---------------------------------------------------------------------------


AutoAssignStrategy = Literal[
    "round_robin", "least_loaded", "by_country", "by_language"
]


class AutoAssignRuleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    strategy: str
    config: Optional[Dict[str, Any]] = None
    is_active: bool
    priority: int
    created_at: datetime


class AutoAssignRuleCreate(BaseModel):
    strategy: AutoAssignStrategy
    config: Optional[Dict[str, Any]] = None
    is_active: bool = True
    priority: int = 100


class AutoAssignRulePatch(BaseModel):
    strategy: Optional[AutoAssignStrategy] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None


# ---------------------------------------------------------------------------
# Pipeline rules (IFTTT)
# ---------------------------------------------------------------------------


class PipelineRuleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    condition: Dict[str, Any]
    action: Dict[str, Any]
    is_active: bool
    created_at: datetime


class PipelineRuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    condition: Dict[str, Any]
    action: Dict[str, Any]
    is_active: bool = True


class PipelineRulePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    condition: Optional[Dict[str, Any]] = None
    action: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Today dashboard
# ---------------------------------------------------------------------------


class TodayLeadCard(BaseModel):
    user_id: UUID
    name: Optional[str] = None
    email: str
    score: int
    score_band: str
    pipeline_status: Optional[str] = None
    last_activity_at: Optional[datetime] = None
    sla_state: Literal["ok", "warning", "breach"] = "ok"
    days_in_status: Optional[int] = None


class TodayTaskCard(BaseModel):
    id: UUID
    description: str
    due_at: Optional[datetime] = None
    priority: str
    lead_user_id: Optional[UUID] = None
    lead_name: Optional[str] = None
    is_overdue: bool = False


class TodayKpis(BaseModel):
    leads_assigned_total: int
    leads_pending_action: int
    tasks_today: int
    tasks_overdue: int
    sla_breach_count: int
    week_conversions: int


class TodayResponse(BaseModel):
    generated_at: datetime
    kpis: TodayKpis
    priority_leads: List[TodayLeadCard]
    overdue_tasks: List[TodayTaskCard]
    upcoming_tasks: List[TodayTaskCard]
    sla_breaches: List[TodayLeadCard]


# ---------------------------------------------------------------------------
# Performance analytics
# ---------------------------------------------------------------------------


class PerformancePoint(BaseModel):
    label: str
    leads_handled: int
    conversions: int
    conversion_rate: float


class PerformanceResponse(BaseModel):
    period: Literal["30d", "90d", "year"]
    user_id: UUID
    leads_handled: int
    leads_handled_prev: int
    conversions: int
    conversions_prev: int
    conversion_rate: float
    conversion_rate_prev: float
    avg_response_hours: Optional[float] = None
    avg_response_hours_prev: Optional[float] = None
    rank: Optional[int] = None
    rank_total: Optional[int] = None
    timeseries: List[PerformancePoint]


# ---------------------------------------------------------------------------
# Funnel personal
# ---------------------------------------------------------------------------


class FunnelStage(BaseModel):
    key: str
    label: str
    count: int
    drop_off_pct: Optional[float] = None
    team_avg_count: Optional[int] = None


class FunnelResponse(BaseModel):
    user_id: UUID
    period: Literal["30d", "90d", "year"]
    stages: List[FunnelStage]
    team_avg_total: int
    my_total: int


# ---------------------------------------------------------------------------
# Benchmarks (D2)
# ---------------------------------------------------------------------------


class BenchmarkResponse(BaseModel):
    lead_user_id: UUID
    cohort_size: int
    rank: int
    percentile: float
    cohort_definition: Dict[str, Any]
    cohort_avg_score: float
    cohort_top_score: int
    my_score: int


# ---------------------------------------------------------------------------
# Activity timeline (B5)
# ---------------------------------------------------------------------------


ActivityKind = Literal[
    "audit",
    "pipeline_change",
    "task",
    "notification",
    "assignment",
    "journey",
    "comment",
    "tag",
]


class ActivityEvent(BaseModel):
    kind: ActivityKind
    at: datetime
    actor_user_id: Optional[UUID] = None
    actor_name: Optional[str] = None
    title: str
    detail: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class ActivityTimelineResponse(BaseModel):
    lead_user_id: UUID
    items: List[ActivityEvent]
    total: int


# ---------------------------------------------------------------------------
# GH user picker
# ---------------------------------------------------------------------------


class GhUserPickerItem(BaseModel):
    user_id: UUID
    name: Optional[str] = None
    email: str
    role: str
    open_leads: int = 0
