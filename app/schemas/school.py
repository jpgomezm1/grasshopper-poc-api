"""Pydantic schemas for the School entity.

GH-S2-BE-07 · base CRUD shapes used by the placeholder endpoints in this sprint
and consumed in full by the Super Admin panel (Sprint 8).
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class SchoolBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9-]*$")
    logo_url: Optional[str] = Field(default=None, max_length=500)
    license_active: bool = True
    license_expires_at: Optional[datetime] = None


class SchoolCreate(SchoolBase):
    """Payload to create a school. Only super_admin can do this."""
    pass


class SchoolUpdate(BaseModel):
    """Partial update. All fields optional. Only super_admin can do this."""
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9-]*$")
    logo_url: Optional[str] = Field(default=None, max_length=500)
    license_active: Optional[bool] = None
    license_expires_at: Optional[datetime] = None


class SchoolResponse(SchoolBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SchoolSummary(BaseModel):
    """Lightweight shape used inside other responses (e.g. UserResponse.school)."""
    id: UUID
    name: str
    slug: str
    logo_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SchoolWithStats(SchoolResponse):
    """School row enriched with usage stats for the admin list view."""
    students_count: int = 0
    psychologists_count: int = 0
    license_tier: Optional[str] = None
    license_seats: Optional[int] = None
    license_expires_at: Optional[datetime] = None


class SchoolListResponse(BaseModel):
    """Paginated school list · GH-S8-BE-01."""
    items: List[SchoolWithStats]
    total: int
    page: int
    page_size: int
    total_pages: int
