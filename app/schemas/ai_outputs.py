from pydantic import BaseModel
from typing import Optional, List


class EmpathyReflectionOutput(BaseModel):
    """Output schema for empathy reflection."""
    text: str
    detected_emotion: Optional[str] = None


class SynthesisChip(BaseModel):
    """Chip data for synthesis."""
    label: str
    value: str


class SynthesisOutput(BaseModel):
    """Output schema for synthesis reflection."""
    text: str
    chips: List[SynthesisChip]
    key_motivations: List[str]
    constraints: List[str]


class PartialSummaryOutput(BaseModel):
    """Output schema for partial summary."""
    bullets: List[str]
    motivation: str


class GeneratedRoute(BaseModel):
    """AI-generated route."""
    key: str
    name: str
    why: str
    what_it_looks_like: str
    next_step: str


class RouteSuggestionOutput(BaseModel):
    """Output schema for route suggestions."""
    routes: List[GeneratedRoute]  # max 3


class AdvisorBriefOutput(BaseModel):
    """Output schema for advisor brief."""
    profile_summary: str
    primary_route: Optional[str] = None
    key_considerations: List[str]
    emotional_state: Optional[str] = None
