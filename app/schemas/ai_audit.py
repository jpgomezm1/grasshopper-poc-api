"""Schemas for the AI feedback audit panel · M-001 (2026-05-21).

GH-LOCAL-CLIENT-MODULES · cliente pidió que su equipo pueda calificar las
recomendaciones de Hop para retroalimentar el prompt engineering. Este
módulo expone los DTOs del panel `/admin/ai-audit`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


Rating = Literal["thumbs_up", "thumbs_down"]


class AiFeedbackCreate(BaseModel):
    """Body of POST /admin/ai-audit/feedback."""

    recommendation_type: str = Field(..., max_length=60)
    recommendation_ref: Optional[str] = Field(None, max_length=120)
    context: Optional[Dict[str, Any]] = None
    rating: Rating
    comment: Optional[str] = Field(None, max_length=2000)


class AiFeedbackOut(BaseModel):
    """Row in GET /admin/ai-audit listing."""

    id: UUID
    recommendation_type: str
    recommendation_ref: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    rating: Rating
    comment: Optional[str] = None
    rated_by_user_id: Optional[UUID] = None
    rated_by_name: Optional[str] = None
    rated_by_role: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AiFeedbackList(BaseModel):
    items: List[AiFeedbackOut]
    total: int
    page: int
    page_size: int


class AiFeedbackTypeAggregate(BaseModel):
    """Per recommendation_type breakdown."""

    recommendation_type: str
    thumbs_up: int
    thumbs_down: int
    total: int
    positive_rate_pct: float  # 0.0–100.0; 0 si total==0


class AiFeedbackAggregates(BaseModel):
    """Returned by GET /admin/ai-audit/aggregates."""

    range_from: datetime
    range_to: datetime
    total_feedback: int
    overall_thumbs_up: int
    overall_thumbs_down: int
    overall_positive_rate_pct: float
    by_type: List[AiFeedbackTypeAggregate]
