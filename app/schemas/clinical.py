"""Schemas for the gh_advisor clinical toolkit · GH-ADVISOR-CLINICAL · 2026-05-04.

Surfaces:
- Bloque A · Dossier (estructura clínica + notes CRUD)
- Bloque B · Psychometrics (vista psicométrica cruzada · patrones · inconsistencias)
- Bloque C+D · Clinical analysis (narrativa + fortalezas + riesgos + patterns)
- Bloque E · Sessions + session notes
- Bloque F · Recomendaciones con narrativa clínica
- Bloque G · Comparador finalistas
- Bloque H · PDF clínico (reusa render path existente)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Bloque A · Dossier
# ---------------------------------------------------------------------------

DossierSection = Literal[
    "demographics",
    "family",
    "academic",
    "hobbies",
    "constraints",
    "aspirations",
    "general",
]


class DossierNoteOut(BaseModel):
    id: UUID
    section: DossierSection
    content: str
    advisor_user_id: Optional[UUID] = None
    advisor_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DossierNoteCreateIn(BaseModel):
    section: DossierSection
    content: str = Field(min_length=1, max_length=20000)


class DossierNoteUpdateIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class DossierDemographics(BaseModel):
    """Computed (non-editable) demographics block from the student profile."""
    name: Optional[str] = None
    email: str
    age: Optional[int] = None
    grade: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    school_name: Optional[str] = None
    english_cefr_level: Optional[str] = None
    english_test_completed: bool = False
    onboarding_status: str = "not_started"
    budget_band: Optional[str] = None
    budget_max_usd: Optional[int] = None
    preferred_countries: List[str] = []
    is_minor: Optional[bool] = None


class DossierAspirations(BaseModel):
    declared: List[str] = []  # de onboarding answers
    inferred: List[str] = []  # del consolidated profile (suggested_career_paths)


class DossierResponse(BaseModel):
    """Full dossier payload · keys map to UI sections."""
    student_user_id: UUID
    demographics: DossierDemographics
    notes_by_section: Dict[str, List[DossierNoteOut]] = {}
    aspirations: DossierAspirations = DossierAspirations()
    journey_answers: Dict[str, Any] = {}  # raw onboarding answers (for hobbies/family/academic captured ahí)
    has_consolidated_profile: bool = False
    tests_completed_count: int = 0


# ---------------------------------------------------------------------------
# Bloque B · Psychometrics
# ---------------------------------------------------------------------------


class PsychTestSummary(BaseModel):
    test_id: str
    completed_at: Optional[datetime] = None
    source: str = "internal"
    scores: Dict[str, Any] = {}


class CrossPattern(BaseModel):
    label: str
    description: str
    severity: Literal["info", "low", "medium", "high"] = "info"
    evidence: List[str] = []


class Inconsistency(BaseModel):
    label: str
    description: str
    severity: Literal["low", "medium", "high"] = "medium"
    tests_involved: List[str] = []


class PsychometricsResponse(BaseModel):
    student_user_id: UUID
    tests: List[PsychTestSummary]
    tests_count: int
    cross_patterns: List[CrossPattern] = []
    inconsistencies: List[Inconsistency] = []
    has_consolidated_profile: bool = False
    consolidated_profile_summary: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Bloque C+D · Clinical analysis
# ---------------------------------------------------------------------------


class ClinicalStrength(BaseModel):
    title: str
    description: str


class ClinicalGrowthArea(BaseModel):
    title: str
    description: str


class ClinicalRisk(BaseModel):
    title: str
    severity: Literal["low", "medium", "high"]
    description: str


class SessionSuggestion(BaseModel):
    topic: str
    why: str
    suggested_exercise: Optional[str] = None


class BehavioralPattern(BaseModel):
    pattern: Literal[
        "ansiedad_decision",
        "complacencia_familiar",
        "bloqueo_exploracion",
        "desalineacion_valor_carrera",
        "señales_clinicas",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str
    severity: Literal["low", "medium", "high"]
    suggested_intervention: str


class ClinicalAnalysis(BaseModel):
    """Persisted clinical analysis · advisor-only."""
    # Pydantic v2: silence the "model_" protected namespace warning so we can
    # keep `model_used` in line with the rest of the codebase (consolidated_profile).
    model_config = {"protected_namespaces": ()}

    narrative: str
    strengths: List[ClinicalStrength] = []
    growth_areas: List[ClinicalGrowthArea] = []
    potential_risks: List[ClinicalRisk] = []
    session_suggestions: List[SessionSuggestion] = []
    behavioral_patterns: List[BehavioralPattern] = []
    requires_clinical_referral: bool = False
    referral_reason: Optional[str] = None

    # Metadata stamped by service
    model_used: Optional[str] = None
    prompt_version: Optional[str] = None
    generated_at: Optional[datetime] = None


class ClinicalAnalysisResponse(BaseModel):
    student_user_id: UUID
    analysis: Optional[ClinicalAnalysis] = None
    cached: bool = False
    cached_at: Optional[datetime] = None
    stale: bool = False
    has_inputs: bool = True
    insufficient_inputs_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Bloque E · Sessions
# ---------------------------------------------------------------------------

OrientationSessionType = Literal[
    "first_contact",
    "exploration",
    "deepening",
    "decision",
    "followup",
]

OrientationSessionStatus = Literal[
    "scheduled",
    "completed",
    "cancelled",
    "no_show",
]

SessionNotePrivacy = Literal[
    "private",
    "shared_supervisor",
    "shared_team",
]


class SessionCreateIn(BaseModel):
    student_user_id: UUID
    scheduled_at: datetime
    duration_min: Optional[int] = Field(default=60, ge=10, le=480)
    type: OrientationSessionType = "first_contact"
    status: OrientationSessionStatus = "scheduled"
    summary: Optional[str] = Field(default=None, max_length=4000)


class SessionPatchIn(BaseModel):
    scheduled_at: Optional[datetime] = None
    duration_min: Optional[int] = Field(default=None, ge=10, le=480)
    type: Optional[OrientationSessionType] = None
    status: Optional[OrientationSessionStatus] = None
    summary: Optional[str] = Field(default=None, max_length=4000)


class SessionOut(BaseModel):
    id: UUID
    advisor_user_id: UUID
    advisor_name: Optional[str] = None
    student_user_id: UUID
    student_name: Optional[str] = None
    student_email: Optional[str] = None
    scheduled_at: datetime
    duration_min: Optional[int] = None
    type: OrientationSessionType
    status: OrientationSessionStatus
    summary: Optional[str] = None
    notes_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    items: List[SessionOut]
    total: int


class SessionNoteCreateIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    privacy: SessionNotePrivacy = "private"


class SessionNotePatchIn(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    privacy: Optional[SessionNotePrivacy] = None


class SessionNoteOut(BaseModel):
    id: UUID
    session_id: UUID
    advisor_user_id: Optional[UUID] = None
    advisor_name: Optional[str] = None
    content: str
    privacy: SessionNotePrivacy
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Bloque F · Recomendaciones con narrativa clínica
# ---------------------------------------------------------------------------


class ClinicalRecommendationItem(BaseModel):
    program_id: Optional[str] = None
    program_slug: Optional[str] = None
    program_name: str
    institution: Optional[str] = None
    country: Optional[str] = None
    match_score: Optional[int] = None
    why_match: Optional[str] = None  # narrativa pública existente
    # Clinical layer (added)
    psychographic_fit: Optional[str] = None
    risks_or_considerations: Optional[str] = None
    development_areas: Optional[str] = None
    success_probability: Optional[Literal["low", "medium", "high"]] = None
    success_probability_reason: Optional[str] = None


class ExplorationStep(BaseModel):
    title: str
    description: str


class ClinicalRecommendationsResponse(BaseModel):
    student_user_id: UUID
    items: List[ClinicalRecommendationItem]
    exploration_plan: List[ExplorationStep] = []
    cached: bool = False
    cached_at: Optional[datetime] = None
    has_recommendations: bool = True
    insufficient_inputs_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Bloque G · Comparador de finalistas
# ---------------------------------------------------------------------------


class FinalistComparisonItem(BaseModel):
    program_id: str
    program_slug: Optional[str] = None
    program_name: str
    institution: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    duration_months: Optional[int] = None
    cost_total: Optional[int] = None
    currency: Optional[str] = None
    budget_tier: Optional[str] = None
    language_requirement: Optional[str] = None
    psychographic_fit_short: Optional[str] = None
    employability: Optional[Dict[str, Any]] = None
    ranking: Optional[Dict[str, Any]] = None
    advisor_pros: Optional[str] = None
    advisor_cons: Optional[str] = None


class FinalistsRequestIn(BaseModel):
    program_ids: List[str] = Field(min_length=2, max_length=3)
    advisor_pros_cons: Dict[str, Dict[str, str]] = {}  # program_id -> {pros, cons}


class ClinicalPdfRequestIn(BaseModel):
    """Optional body for the clinical PDF · finalists are optional.

    If `program_ids` is empty/missing the PDF is generated WITHOUT the
    finalists section. If 2-3 program_ids provided · table is included.
    """
    program_ids: List[str] = Field(default_factory=list, max_length=3)
    advisor_pros_cons: Dict[str, Dict[str, str]] = Field(default_factory=dict)


class FinalistsResponse(BaseModel):
    student_user_id: UUID
    items: List[FinalistComparisonItem]
