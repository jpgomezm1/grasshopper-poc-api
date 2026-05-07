"""Schemas for the GH internal team endpoints · GH-ROLES-001.

Surfaces:
- Contact request lifecycle (request → list → status update).
- Student visibility for gh_advisor (B2C + opted-in B2B).
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# Pseudo-enum kept as Literal so we don't ship a DB enum (cheap to extend later)
ContactStatus = Literal["pending", "in_progress", "converted", "declined"]


# ---------------------------------------------------------------------------
# Student-facing
# ---------------------------------------------------------------------------


class GhContactRequestIn(BaseModel):
    """Body for `POST /students/me/request-gh-contact`."""

    message: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Optional context the student wants the GH team to know.",
    )


class GhContactRequestOut(BaseModel):
    """Response after the student submits a contact request."""

    requested_at: datetime
    status: ContactStatus
    message: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# GH-team facing
# ---------------------------------------------------------------------------


class GhStudentSummary(BaseModel):
    """Compact student row used by `GET /gh/students` and contact-requests list."""

    id: UUID
    email: str
    name: Optional[str] = None
    school_id: Optional[UUID] = None
    school_name: Optional[str] = None
    onboarding_status: str
    english_cefr_level: Optional[str] = None
    english_test_completed: bool
    is_b2c: bool
    has_contact_request: bool
    gh_contact_status: Optional[ContactStatus] = None
    gh_contact_requested_at: Optional[datetime] = None
    gh_contact_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GhStudentListResponse(BaseModel):
    items: List[GhStudentSummary]
    total: int
    page: int
    page_size: int


class GhContactRequestListItem(BaseModel):
    """One row in the gh_advisor / gh_commercial contact-requests panel."""

    user_id: UUID
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None  # JP 2026-05-04 · contacto del lead
    school_id: Optional[UUID] = None
    school_name: Optional[str] = None
    is_b2c: bool
    gh_contact_status: ContactStatus
    gh_contact_requested_at: datetime
    gh_contact_message: Optional[str] = None

    class Config:
        from_attributes = True


class GhContactRequestList(BaseModel):
    items: List[GhContactRequestListItem]
    total: int


class GhContactStatusUpdate(BaseModel):
    """Body for `PATCH /gh/contact-requests/{user_id}/status`."""

    status: ContactStatus
