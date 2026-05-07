"""Pydantic schemas for the extended school_admin panel · GH-SCHOOL-ADMIN.

Sprint school_admin · 2026-05-04. Covers 23 features grouped in 11 categories
(see docs/BITACORA_TESTING.md "## 4 · SCHOOL_ADMIN").

All shapes are scoped to the caller's school via JWT. No school_id ever
appears in path or body of mutating endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, EmailStr


# ============================================================================
# Cohorts (Categoría B · feature 4)
# ============================================================================


class CohortBase(BaseModel):
    key: str = Field(..., min_length=1, max_length=40)
    label: str = Field(..., min_length=1, max_length=120)
    grade: Optional[str] = Field(None, max_length=20)
    academic_year: Optional[int] = None
    color: Optional[str] = Field(None, max_length=20)


class CohortCreate(CohortBase):
    pass


class CohortUpdate(BaseModel):
    label: Optional[str] = Field(None, max_length=120)
    grade: Optional[str] = Field(None, max_length=20)
    academic_year: Optional[int] = None
    color: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None


class CohortResponse(CohortBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    school_id: UUID
    is_active: bool
    created_at: datetime
    archived_at: Optional[datetime] = None
    students_count: int = 0
    psychologists_count: int = 0


class CohortListResponse(BaseModel):
    items: List[CohortResponse]
    total: int


class CohortKpis(BaseModel):
    cohort_id: UUID
    cohort_label: str
    students_total: int
    completed_pct: float
    in_progress_pct: float
    inactive_pct: float
    decided_pct: float
    health_score: float
    avg_journey_days: Optional[float] = None


class CohortAssignmentRequest(BaseModel):
    student_user_ids: List[UUID]


class CohortPsyAssignmentRequest(BaseModel):
    psychologist_user_ids: List[UUID]


# ============================================================================
# Advanced student search + saved searches (Categoría C · feature 5)
# ============================================================================


class StudentAdvancedFilter(BaseModel):
    cohort_id: Optional[UUID] = None
    status: Optional[str] = None
    pct_min: Optional[float] = None
    pct_max: Optional[float] = None
    tests_min: Optional[int] = None
    tests_max: Optional[int] = None
    has_alert: Optional[bool] = None
    has_parents: Optional[bool] = None
    inactive_days: Optional[int] = None
    search: Optional[str] = None


class SavedSearchCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    filters: StudentAdvancedFilter


class SavedSearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    filters: Dict[str, Any]
    created_at: datetime


# ============================================================================
# Bulk actions (Categoría C · feature 6)
# ============================================================================


class BulkInviteRow(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    cohort_key: Optional[str] = None


class BulkInviteRequest(BaseModel):
    rows: List[BulkInviteRow]


class BulkInviteResult(BaseModel):
    created: int
    skipped: int
    errors: List[Dict[str, str]]


class BulkReassignCohortRequest(BaseModel):
    student_user_ids: List[UUID]
    target_cohort_id: UUID


class BulkInactivateRequest(BaseModel):
    student_user_ids: List[UUID]


# ============================================================================
# Admin notes (Categoría C · feature 7)
# ============================================================================


class AdminNoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class AdminNoteUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class AdminNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    student_user_id: UUID
    school_id: UUID
    author_user_id: Optional[UUID] = None
    author_name: Optional[str] = None
    content: str
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Psychologist performance (Categoría D · feature 8)
# ============================================================================


class PsychologistPerformanceItem(BaseModel):
    psychologist_user_id: UUID
    name: Optional[str] = None
    email: Optional[str] = None
    sessions_count: int
    students_attended: int
    avg_response_hours: Optional[float] = None
    no_show_rate: Optional[float] = None
    workload_alert: bool = False


class PsychologistPerformanceResponse(BaseModel):
    items: List[PsychologistPerformanceItem]
    school_avg_students: float


# ============================================================================
# Parent role (Categoría E · feature 10)
# ============================================================================


class ParentInviteItem(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    relationship: Literal["mother", "father", "guardian", "other"] = "guardian"


class ParentInviteRequest(BaseModel):
    emails: List[ParentInviteItem]


class ParentInviteResult(BaseModel):
    invited: int
    skipped: int
    errors: List[Dict[str, str]] = Field(default_factory=list)


class ParentChildSummary(BaseModel):
    student_user_id: UUID
    student_name: Optional[str] = None
    onboarding_status: Optional[str] = None
    progress_pct: float = 0.0
    tests_completed: int = 0
    has_consolidated_profile: bool = False
    last_activity_at: Optional[datetime] = None


class ParentSchoolBranding(BaseModel):
    """Primary school exposed to the parent (logo + brand color).

    GH-PARENT-EXPERIENCE · 2026-05-05 · Bloque D.
    """
    id: UUID
    name: str
    logo_url: Optional[str] = None
    branding_primary_color: Optional[str] = None


class ParentMeResponse(BaseModel):
    parent_user_id: UUID
    parent_name: Optional[str] = None
    children: List[ParentChildSummary]
    # GH-PARENT-EXPERIENCE · 2026-05-05 · Bloque D
    primary_school: Optional[ParentSchoolBranding] = None
    schools: List[ParentSchoolBranding] = Field(default_factory=list)


# ============================================================================
# Parent inbox · mass messages read-only (Bloque B · 2026-05-05)
# ============================================================================


class ParentMessageItem(BaseModel):
    id: UUID
    school_id: UUID
    school_name: Optional[str] = None
    sender_name: Optional[str] = None
    subject: str
    body: str
    sent_at: datetime
    is_read: bool


class ParentMessagesResponse(BaseModel):
    items: List[ParentMessageItem]
    unread: int


# ============================================================================
# Parent timeline of a child (Bloque C · 2026-05-05)
# ============================================================================


class ParentTimelineMilestone(BaseModel):
    """One milestone on the child timeline. PUBLIC INFO ONLY.

    Never carries clinical analysis · session notes · admin notes.
    """
    kind: Literal[
        "onboarding_completed",
        "test_completed",
        "english_completed",
        "route_active",
        "journey_completed",
    ]
    title: str
    detail: Optional[str] = None
    occurred_at: Optional[datetime] = None
    icon: Optional[str] = None


class ParentTimelineResponse(BaseModel):
    student_user_id: UUID
    student_name: Optional[str] = None
    onboarding_status: str
    onboarding_pct: float
    tests_completed: List[str]
    routes_active: int
    onboarding_completed_at: Optional[datetime] = None
    journey_completed_at: Optional[datetime] = None
    milestones: List[ParentTimelineMilestone]


# ============================================================================
# Parent legal documents · history (Bloque J · 2026-05-05)
# ============================================================================


class ParentLegalDocItem(BaseModel):
    id: UUID
    school_id: UUID
    type: str
    version: str
    content: str
    effective_at: Optional[datetime] = None
    created_at: datetime
    is_signed: bool
    signed_at: Optional[datetime] = None
    signed_version: Optional[str] = None
    requires_resign: bool = False


class ParentLegalHistoryResponse(BaseModel):
    pending: List[ParentLegalDocItem]
    signed: List[ParentLegalDocItem]


# ============================================================================
# Mass messages (Categoría E · feature 11)
# ============================================================================


class MassMessageCreate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=20000)
    audience: Literal["students", "parents", "both"] = "both"
    cohort_id: Optional[UUID] = None


class MassMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    subject: str
    audience: str
    cohort_id: Optional[UUID] = None
    sent_at: datetime
    sent_count: int
    opened_count: int


# ============================================================================
# Events (Categoría E·12 + G·15)
# ============================================================================


class EventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=20000)
    starts_at: datetime
    ends_at: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=200)
    audience: Literal["students", "parents", "both"] = "both"


class EventUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=20000)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=200)
    audience: Optional[Literal["students", "parents", "both"]] = None


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    school_id: UUID
    title: str
    description: Optional[str] = None
    starts_at: datetime
    ends_at: Optional[datetime] = None
    location: Optional[str] = None
    audience: str
    created_at: datetime
    archived_at: Optional[datetime] = None
    rsvp_count: int = 0


class EventRSVPRequest(BaseModel):
    status: Literal["going", "maybe", "declined"]


# ============================================================================
# Reports (Categoría F · 13/14)
# ============================================================================


class ExecutiveReportRequest(BaseModel):
    quarter: int = Field(..., ge=1, le=4)
    year: int = Field(..., ge=2024, le=2099)


class ROIReportRequest(BaseModel):
    period_start: datetime
    period_end: datetime


# ============================================================================
# School branding (Categoría H · 16)
# ============================================================================


class SchoolBrandingUpdate(BaseModel):
    secondary_color: Optional[str] = Field(None, max_length=20)
    locale: Optional[str] = Field(None, max_length=10)
    timezone: Optional[str] = Field(None, max_length=80)


# ============================================================================
# Custom fields (Categoría H · 17)
# ============================================================================


class CustomFieldCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=60, pattern=r"^[a-z0-9_]+$")
    label: str = Field(..., min_length=1, max_length=120)
    type: Literal["text", "number", "boolean", "enum"]
    options: Optional[List[str]] = None


class CustomFieldUpdate(BaseModel):
    label: Optional[str] = None
    options: Optional[List[str]] = None
    is_active: Optional[bool] = None


class CustomFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    school_id: UUID
    key: str
    label: str
    type: str
    options: Optional[List[str]] = None
    is_active: bool
    created_at: datetime


class StudentCustomFieldValueUpdate(BaseModel):
    field_id: UUID
    value: Any


class StudentCustomFieldValueResponse(BaseModel):
    field_id: UUID
    field_key: str
    field_label: str
    field_type: str
    value: Any


# ============================================================================
# Legal documents (Categoría H · 18)
# ============================================================================


class LegalDocumentCreate(BaseModel):
    type: Literal["privacy", "terms", "parental_consent", "other"]
    version: str = Field(..., min_length=1, max_length=20)
    content: str = Field(..., min_length=1, max_length=200000)
    effective_at: Optional[datetime] = None


class LegalDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    school_id: UUID
    type: str
    version: str
    content: str
    effective_at: Optional[datetime] = None
    created_at: datetime
    signatures_count: int = 0


class LegalSignatureRequest(BaseModel):
    document_id: UUID


class LegalSignatureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_id: UUID
    signer_user_id: Optional[UUID] = None
    signer_name: Optional[str] = None
    signer_email: Optional[str] = None
    signed_at: datetime


# ============================================================================
# License upgrade request (Categoría I · 19)
# ============================================================================


class LicenseUpgradeRequest(BaseModel):
    target_tier: Optional[str] = None
    target_seats: Optional[int] = None
    notes: Optional[str] = Field(None, max_length=2000)


# ============================================================================
# GH coordination (Categoría J · 20/21)
# ============================================================================


class GHCoordinationStudent(BaseModel):
    student_user_id: UUID
    name: Optional[str] = None
    email: Optional[str] = None
    gh_contact_status: Optional[str] = None
    gh_contact_requested_at: Optional[datetime] = None
    lead_pipeline_status: Optional[str] = None
    assigned_to_name: Optional[str] = None


class HandoffRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=4000)
    consent_given: bool = True


# ============================================================================
# Cases followup + clinical alerts (Categoría K · 22/23)
# ============================================================================


class ClinicalAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    student_user_id: UUID
    student_name: Optional[str] = None
    severity: str
    pattern_type: str
    summary: Optional[str] = None
    source: str
    acknowledged_at: Optional[datetime] = None
    case_id: Optional[UUID] = None
    created_at: datetime


class ClinicalAlertAck(BaseModel):
    create_case: bool = False
    case_title: Optional[str] = None
    case_type: Optional[str] = None


class CaseCreate(BaseModel):
    student_user_id: UUID
    case_type: Literal["academic", "emocional", "familiar", "otro"]
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=10000)


class CaseUpdate(BaseModel):
    status: Optional[Literal["open", "in_progress", "resolved", "escalated"]] = None
    title: Optional[str] = None
    description: Optional[str] = None
    resolution_notes: Optional[str] = None


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    student_user_id: UUID
    student_name: Optional[str] = None
    school_id: UUID
    opened_by_user_id: Optional[UUID] = None
    opened_by_name: Optional[str] = None
    case_type: str
    status: str
    title: str
    description: Optional[str] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    interventions_count: int = 0


class InterventionCreate(BaseModel):
    action: Literal["note", "meeting", "referral", "parent_contact", "closure"]
    content: str = Field(..., min_length=1, max_length=10000)


class InterventionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    case_id: UUID
    author_user_id: Optional[UUID] = None
    author_name: Optional[str] = None
    action: str
    content: str
    created_at: datetime


# ============================================================================
# Dashboard rico (Categoría A · 1/2/3)
# ============================================================================


class HealthScoreBreakdown(BaseModel):
    activity: float
    completeness: float
    satisfaction: float
    timeliness: float
    overall: float


class TimelinePoint(BaseModel):
    period_label: str  # e.g. "2026-W18" or "2026-04"
    period_start: datetime
    students_active: int
    tests_completed: int
    profiles_consolidated: int
    decisions_taken: int


class FunnelStage(BaseModel):
    stage_key: str
    stage_label: str
    count: int
    drop_off_pct: float


class RiskAlert(BaseModel):
    student_user_id: UUID
    student_name: Optional[str] = None
    reason: Literal[
        "inactive_30d",
        "stuck_14d",
        "tests_abandoned",
        "sla_breach",
    ]
    detail: Optional[str] = None
    triggered_at: datetime


class DashboardRichResponse(BaseModel):
    health_score: HealthScoreBreakdown
    timeline_weekly: List[TimelinePoint]
    timeline_monthly: List[TimelinePoint]
    funnel: List[FunnelStage]
    activity_heatmap: List[List[int]]  # 7 rows x 24 cols
    risk_alerts: List[RiskAlert]
    cohorts_kpis: List[CohortKpis]
    cohorts_compare: List[CohortKpis]
