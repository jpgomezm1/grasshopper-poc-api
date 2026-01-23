from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class ProfileVersionResponse(BaseModel):
    """Profile version response."""
    id: UUID
    session_id: UUID
    created_at: datetime
    version: int
    answers: dict
    derived_tags: List[str]

    class Config:
        from_attributes = True


class ProfileSummary(BaseModel):
    """Profile summary with derived data."""
    answers: dict
    motivations: List[str]
    constraints: List[str]
    stage_label: str
    clarity_level: str
