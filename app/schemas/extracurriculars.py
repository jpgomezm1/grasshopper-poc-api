"""Schemas for extracurricular activities · F-001 (2026-05-21)."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExtracurricularCreate(BaseModel):
    """Body of POST /me/activities."""

    category: str = Field(..., max_length=20)
    name: str = Field(..., min_length=1, max_length=120)
    role: Optional[str] = Field(None, max_length=120)
    hours_per_week: Optional[int] = Field(None, ge=0, le=168)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = Field(None, max_length=4000)
    achievements: Optional[List[str]] = None
    evidence_urls: Optional[List[str]] = None


class ExtracurricularUpdate(BaseModel):
    """Body of PATCH /me/activities/{id}. Todos los campos opcionales."""

    category: Optional[str] = Field(None, max_length=20)
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    role: Optional[str] = Field(None, max_length=120)
    hours_per_week: Optional[int] = Field(None, ge=0, le=168)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = Field(None, max_length=4000)
    achievements: Optional[List[str]] = None
    evidence_urls: Optional[List[str]] = None


class ExtracurricularOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    category: str
    name: str
    role: Optional[str] = None
    hours_per_week: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = None
    achievements: Optional[List[str]] = None
    evidence_urls: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime


class ExtracurricularList(BaseModel):
    items: List[ExtracurricularOut]
    total: int
