"""Pydantic schemas for the enriched CRM module.

GH-CRM-001 · Sprint CRM enriquecido 2026-05-03 · último issue de
BITACORA_TESTING.md.

Surfaces:

    GET   /api/v1/admin/crm/leads
    GET   /api/v1/admin/crm/leads/{user_id}
    POST  /api/v1/admin/crm/leads/{user_id}/regenerate-analysis
    PATCH /api/v1/admin/crm/leads/{user_id}/status
    GET   /api/v1/admin/crm/kpis
    GET   /api/v1/admin/crm/leads/export

Reglas de origen (consumidas también por la query del listado):

    Lead Grasshopper (lead propio):
        school_id IS NULL
        OR (school_id NOT NULL AND gh_contact_status = 'converted')
    Lead potencial de colegio (radar · NO propio):
        school_id NOT NULL AND gh_contact_status IN (NULL, 'pending', 'in_progress')
        Solo se muestra si score >= 60 (umbral fijo · ver service).

Privacidad (D-025 + Habeas Data):
    - Journal del student → solo metadata (count + tipos · nunca contenido).
    - Chat con Hop → solo count + last_at (nunca contenido).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


LeadOrigin = Literal["grasshopper", "school_radar"]
LeadPipelineStatus = Literal[
    "pending", "contacted", "qualified", "converted", "declined"
]
ScoreBand = Literal["hot", "warm", "cold"]
NextActionPriority = Literal["high", "medium", "low"]


# ---------------------------------------------------------------------------
# Lead list row (resumen para tabla)
# ---------------------------------------------------------------------------


class CrmLeadListItem(BaseModel):
    """One row in the CRM leads list."""

    user_id: UUID
    email: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None  # placeholder · derivable from name initials in FE

    origin: LeadOrigin
    school_id: Optional[UUID] = None
    school_name: Optional[str] = None

    # Score (computed from `student_lead_scoring`)
    score: int  # 0..100
    score_band: ScoreBand

    # Pipeline status (separate from gh_contact_status)
    pipeline_status: Optional[LeadPipelineStatus] = None
    pipeline_status_at: Optional[datetime] = None

    # Original contact request status (visible to commercial for triage)
    gh_contact_status: Optional[str] = None  # 'pending'|'in_progress'|'converted'|'declined'
    gh_contact_requested_at: Optional[datetime] = None

    # Activity summary (last touch · tests · profile)
    last_activity_at: Optional[datetime] = None
    tests_completed: int = 0
    has_consolidated_profile: bool = False

    created_at: datetime

    model_config = ConfigDict(from_attributes=False)


class CrmLeadListResponse(BaseModel):
    items: List[CrmLeadListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------


class CrmKpisResponse(BaseModel):
    total_leads: int = 0
    hot_leads: int = 0  # score >= 70
    pending_action: int = 0  # pipeline_status IN (pending) OR gh_contact_status='pending'
    converted_last_30d: int = 0  # pipeline_status='converted' AND status_at >= -30d
    by_origin: Dict[str, int] = Field(default_factory=dict)  # {grasshopper, school_radar}
    by_band: Dict[str, int] = Field(default_factory=dict)  # {hot, warm, cold}
    by_pipeline_status: Dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detail · score breakdown
# ---------------------------------------------------------------------------


class ScoreBreakdownSignal(BaseModel):
    """One of the 7 signals consumed by `student_lead_scoring`."""

    key: str  # 'journey_progress' | 'tests_completed' | 'consolidated_profile' | ...
    label: str  # human-friendly · es-CO
    weight: int  # max points this signal can contribute
    contributed: float  # actual contribution · 0..weight
    evidence: str  # 1-line evidencia textual


class CrmScoreBreakdown(BaseModel):
    score: int  # 0..100
    band: ScoreBand
    signals: List[ScoreBreakdownSignal] = Field(default_factory=list)
    rationale: str  # narrative line (deterministic · from scoring service)


# ---------------------------------------------------------------------------
# Detail · demographics (Overview tab)
# ---------------------------------------------------------------------------


class CrmDemographics(BaseModel):
    name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    birthdate: Optional[date] = None
    age: Optional[int] = None  # derived from birthdate · None if unknown

    # Geo / contact city pulled from onboarding answers if available
    city: Optional[str] = None
    country: Optional[str] = None

    # Preferences
    budget_band: Optional[str] = None
    budget_max_usd: Optional[int] = None
    preferred_countries: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)

    # English level
    english_cefr_level: Optional[str] = None
    english_test_completed: bool = False

    # Onboarding answers (raw · already opted-in by the user filling them)
    onboarding_answers: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detail · journey snapshot
# ---------------------------------------------------------------------------


class CrmTestSnapshot(BaseModel):
    test_id: str
    completed_at: datetime
    scores: Dict[str, Any] = Field(default_factory=dict)
    source: str = "internal"  # 'internal' | 'external_upload'


class CrmConsolidatedProfileLite(BaseModel):
    generated_at: datetime
    has_profile: bool = True
    summary: Optional[str] = None  # short (<=300 chars) · safe for staff
    interests: List[str] = Field(default_factory=list)
    values: List[str] = Field(default_factory=list)


class CrmJournalMeta(BaseModel):
    """Privacy-respecting metadata only · NO content (D-025)."""

    total_entries: int = 0
    entries_by_type: Dict[str, int] = Field(default_factory=dict)
    last_entry_at: Optional[datetime] = None


class CrmHopSessionMeta(BaseModel):
    """Privacy-respecting metadata only · NO content (D-025)."""

    total_sessions: int = 0
    last_session_at: Optional[datetime] = None


class CrmJourneySnapshot(BaseModel):
    onboarding_status: str
    journey_progress: float = 0.0  # 0..1
    onboarding_answers: Dict[str, Any] = Field(default_factory=dict)
    tests: List[CrmTestSnapshot] = Field(default_factory=list)
    consolidated_profile: Optional[CrmConsolidatedProfileLite] = None
    journal: CrmJournalMeta = Field(default_factory=CrmJournalMeta)
    hop_sessions: CrmHopSessionMeta = Field(default_factory=CrmHopSessionMeta)


# ---------------------------------------------------------------------------
# Detail · AI analysis
# ---------------------------------------------------------------------------


class CrmProgramMatch(BaseModel):
    program_id: str
    name: str
    institution: Optional[str] = None
    country: Optional[str] = None
    match_reason: str  # 1-line · why this program fits this lead


class CrmNextAction(BaseModel):
    priority: NextActionPriority
    action: str  # imperative · es-CO
    why: str  # rationale 1-2 lines


class CrmAiAnalysis(BaseModel):
    # Disable Pydantic's "model_" protected namespace · we use `model_used`
    # to mirror the rest of the codebase's audit trail naming convention.
    model_config = ConfigDict(protected_namespaces=())

    rationale: str  # 1-2 paragraphs · es-CO
    program_matches: List[CrmProgramMatch] = Field(default_factory=list, max_length=3)
    next_actions: List[CrmNextAction] = Field(default_factory=list, max_length=3)
    generated_at: datetime
    model_used: Optional[str] = None
    cache_age_seconds: Optional[int] = None  # 0 if just generated · >0 if from cache
    is_fallback: bool = False  # True when the AI call failed and we used a deterministic template


# ---------------------------------------------------------------------------
# Detail · activity log
# ---------------------------------------------------------------------------


class CrmActivityEntry(BaseModel):
    at: datetime
    kind: str  # 'contact_request' | 'pipeline_change' | 'bitrix_sync' | 'audit'
    label: str  # human-friendly description (es-CO)
    actor_email: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class CrmActivityLog(BaseModel):
    items: List[CrmActivityEntry] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Detail · top-level response
# ---------------------------------------------------------------------------


class CrmLeadDetailResponse(BaseModel):
    user_id: UUID
    origin: LeadOrigin
    school_id: Optional[UUID] = None
    school_name: Optional[str] = None

    pipeline_status: Optional[LeadPipelineStatus] = None
    pipeline_status_at: Optional[datetime] = None
    gh_contact_status: Optional[str] = None
    gh_contact_message: Optional[str] = None
    gh_contact_requested_at: Optional[datetime] = None

    score_breakdown: CrmScoreBreakdown
    demographics: CrmDemographics
    journey: CrmJourneySnapshot
    ai_analysis: Optional[CrmAiAnalysis] = None  # may be null on first load · POST regenerates
    activity_log: CrmActivityLog


# ---------------------------------------------------------------------------
# PATCH status
# ---------------------------------------------------------------------------


class CrmPipelineStatusUpdate(BaseModel):
    status: LeadPipelineStatus
    note: Optional[str] = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# POST regenerate-analysis (response is just CrmAiAnalysis)
# ---------------------------------------------------------------------------


class CrmRegenerateAnalysisRequest(BaseModel):
    """Optional flags to influence the regen · all default."""

    force: bool = False  # bypass cache and regenerate even if fresh
