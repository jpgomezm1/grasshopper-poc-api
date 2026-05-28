"""Pydantic schemas for HumanInterventionNote · F-006 (2026-05-28)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import HUMAN_INTERVENTION_LEVELS


class HumanInterventionNoteOut(BaseModel):
    user_id: UUID
    notes: Optional[str] = None
    closeness_level: Optional[str] = None
    updated_by_user_id: Optional[UUID] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HumanInterventionNoteUpdate(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=4000)
    closeness_level: Optional[str] = Field(default=None, max_length=20)

    @field_validator("closeness_level")
    @classmethod
    def _check_level(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if v not in HUMAN_INTERVENTION_LEVELS:
            raise ValueError(
                f"closeness_level must be one of {list(HUMAN_INTERVENTION_LEVELS)}"
            )
        return v
