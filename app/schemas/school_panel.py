"""Pydantic schemas for the B2B school panel · GH-S9.

These shapes are consumed by `/school/me/*` endpoints and the FE pages
under `pages/school/*`.

Conventions:
    - "Cohort" means "students of the school".
    - JourneyStatus is a coarse classification computed by
      `app.services.school_panel_service.classify_journey`.
    - All dates serialize as ISO-8601 (datetime).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


JourneyStatus = Literal["no_iniciado", "en_progreso", "completado", "perdido"]


# ============================================================================
# Dashboard KPIs · GET /school/me/dashboard
# ============================================================================


class LicenseSnapshot(BaseModel):
    tier: Optional[str] = None
    seats_total: int = 0
    seats_used: int = 0
    expires_at: Optional[datetime] = None
    is_expired: bool = False


class CohortBucket(BaseModel):
    code: str
    label: str
    count: int


class TopProgramHit(BaseModel):
    program_id: str
    name: Optional[str] = None
    hits: int


class SchoolDashboardKpis(BaseModel):
    """KPIs surfaced in the dashboard. Cached server-side 5 min per school."""
    school_id: UUID
    school_name: str

    total_students: int
    students_no_iniciado: int
    students_en_progreso: int
    students_completado: int
    students_perdido: int
    students_with_completed_journey: int

    avg_tests_per_student: float
    tests_completed_total: int
    reports_generated_30d: int

    active_license: LicenseSnapshot

    top_holland_codes_in_cohort: List[CohortBucket] = Field(default_factory=list)
    top_recommended_paths: List[CohortBucket] = Field(default_factory=list)

    cached_at: datetime


# ============================================================================
# Students list · GET /school/me/students
# ============================================================================


class StudentRow(BaseModel):
    """Compact row for the cohort table."""
    id: UUID
    email: str
    name: Optional[str] = None

    journey_status: JourneyStatus
    completion_pct: int = Field(ge=0, le=100)
    tests_completed_count: int = 0
    has_consolidated_profile: bool = False
    last_active_at: Optional[datetime] = None
    invited_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudentListResponse(BaseModel):
    items: List[StudentRow]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================================
# Student detail · GET /school/me/students/{id}
# ============================================================================


class TestSummary(BaseModel):
    test_id: str
    completed_at: datetime
    source: str = "internal"
    scores: Dict[str, Any] = Field(default_factory=dict)


class RecommendationSummary(BaseModel):
    program_id: str
    name: Optional[str] = None
    fit_score: Optional[int] = None
    rationale: Optional[str] = None


class JournalEntrySummary(BaseModel):
    id: UUID
    entry_type: str
    content: str
    created_at: datetime
    auto_generated: bool = False


class StudentDetailResponse(BaseModel):
    id: UUID
    email: str
    name: Optional[str] = None
    school_id: UUID

    journey_status: JourneyStatus
    completion_pct: int = Field(ge=0, le=100)
    onboarding_status: str
    english_cefr_level: Optional[str] = None

    tests: List[TestSummary] = Field(default_factory=list)
    consolidated_profile: Optional[Dict[str, Any]] = None
    recommendations: List[RecommendationSummary] = Field(default_factory=list)
    journal_entries: List[JournalEntrySummary] = Field(default_factory=list)
    # GH-S11.5-BE-06 · D-025 · Habeas Data filter (Ley 1581/2012)
    # Staff (psychologist · school_admin · super_admin) only sees journal
    # entries with entry_type IN ('interest','constraint','decision').
    # `private_entries_count` exposes the number of `reflection`+`manual`
    # entries the student has WITHOUT leaking content · transparency without
    # disclosure · enables UI to inform staff that the student has private
    # entries that require explicit student consent to access.
    private_entries_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of student's `reflection`+`manual` entries hidden from staff. "
            "Use to render a discreet notice without disclosing content."
        ),
    )
    saved_offers: List[str] = Field(default_factory=list)

    last_active_at: Optional[datetime] = None
    created_at: datetime

    # Read-only marker for the FE (psychologist gets a read-only banner).
    read_only_for_caller: bool = False


# ============================================================================
# Reports cohort-level · GET /school/me/reports
# ============================================================================


class CohortReportsResponse(BaseModel):
    school_id: UUID
    school_name: str

    distribution_journey_status: List[CohortBucket]
    distribution_holland: List[CohortBucket]
    distribution_mbti: List[CohortBucket] = Field(default_factory=list)
    completion_rate_pct: float
    avg_tests_per_student: float
    most_popular_tests: List[CohortBucket]

    students_to_review: List[StudentRow] = Field(
        default_factory=list,
        description="Students classified as `perdido` to nudge from the panel.",
    )

    cached_at: datetime
