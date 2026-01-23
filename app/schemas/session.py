from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


class JourneyStage(str, Enum):
    """Journey stages."""
    LANDING = "LANDING"
    CONTEXT = "CONTEXT"
    INTERESTS = "INTERESTS"
    CONSTRAINTS = "CONSTRAINTS"
    SYNTHESIS = "SYNTHESIS"
    ROUTES = "ROUTES"
    DONE = "DONE"


class ViewType(str, Enum):
    """View types for journey steps."""
    WELCOME = "WELCOME"
    OPEN_TEXT = "OPEN_TEXT"
    SINGLE_CHOICE = "SINGLE_CHOICE"
    MULTI_CHOICE = "MULTI_CHOICE"
    REFLECTION = "REFLECTION"
    PARTIAL_SUMMARY = "PARTIAL_SUMMARY"
    ROUTES_PICKER = "ROUTES_PICKER"
    NEXT_STEP = "NEXT_STEP"


class JourneyAnswers(BaseModel):
    """User journey answers."""
    whyHere: Optional[str] = None
    lifeStage: Optional[str] = None
    timeHorizon: Optional[str] = None
    clarityLevel: Optional[str] = None
    interestType: Optional[List[str]] = None
    weeklyActivities: Optional[str] = None
    dontWant: Optional[str] = None
    budgetBand: Optional[str] = None
    languageLevel: Optional[str] = None
    geoPreference: Optional[str] = None


class SessionCreate(BaseModel):
    """Schema for creating a new session."""
    pass  # No required fields for creation


class SessionEventCreate(BaseModel):
    """Schema for submitting a journey event."""
    event_type: str  # "answer", "navigation", "selection"
    step_id: str
    payload: Optional[Dict[str, Any]] = None


class ProgressInfo(BaseModel):
    """Progress information."""
    stage: str
    percentage: int


class ProfilePreview(BaseModel):
    """Profile preview for side panel."""
    life_stage: Optional[str] = None
    time_horizon: Optional[str] = None
    interests: Optional[List[str]] = None
    motivations: Optional[List[str]] = None
    constraints: Optional[List[str]] = None


class JournalPreviewEntry(BaseModel):
    """Journal entry preview for side panel."""
    id: str
    content: str
    type: str
    timestamp: datetime


class SidePanel(BaseModel):
    """Side panel data."""
    profile_preview: ProfilePreview
    journal_preview: List[JournalPreviewEntry]


class JourneyResponse(BaseModel):
    """Standard journey response contract."""
    session_id: UUID
    stage: JourneyStage
    step_id: str
    view_type: ViewType
    title: Optional[str] = None
    question: Optional[str] = None
    text: Optional[str] = None
    placeholder: Optional[str] = None
    options: Optional[List[str]] = None
    max_select: Optional[int] = None
    helper: Optional[str] = None
    progress: ProgressInfo
    side_panel: SidePanel
    actions: List[str]

    # AI-generated content for reflections
    reflection_content: Optional[str] = None
    synthesis_text: Optional[str] = None
    synthesis_chips: Optional[List[Dict[str, str]]] = None
    partial_summary_bullets: Optional[List[str]] = None
    partial_summary_motivation: Optional[str] = None
    suggested_routes: Optional[List[Dict[str, Any]]] = None


class SessionResponse(BaseModel):
    """Session state response."""
    id: UUID
    created_at: datetime
    updated_at: datetime
    current_step: str
    current_stage: str
    is_paused: bool
    is_completed: bool
    answers: JourneyAnswers
    completed_steps: List[str]
    selected_routes: List[str]

    class Config:
        from_attributes = True
