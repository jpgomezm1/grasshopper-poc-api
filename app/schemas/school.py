"""Pydantic schemas for the School entity.

GH-S2-BE-07 · base CRUD shapes used by the placeholder endpoints in this sprint
and consumed in full by the Super Admin panel (Sprint 8).

Bloque A · Sprint super_admin fixes 2026-05-03 · extended with fiscal +
contacts + center metadata (migration 014).
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, EmailStr


# ---------------- nested fragments (used by wizard) ----------------

class SchoolFiscalIdentity(BaseModel):
    rut: Optional[str] = Field(default=None, max_length=40)
    razon_social: Optional[str] = Field(default=None, max_length=255)
    direccion_fiscal: Optional[str] = None
    tipo_persona: Optional[str] = Field(default=None, pattern=r"^(juridica|natural)$")


class SchoolCommercialContact(BaseModel):
    commercial_contact_name: Optional[str] = Field(default=None, max_length=255)
    commercial_contact_role: Optional[str] = Field(default=None, max_length=120)
    commercial_contact_email: Optional[EmailStr] = None
    commercial_contact_phone: Optional[str] = Field(default=None, max_length=50)


class SchoolAcademicContact(BaseModel):
    academic_contact_name: Optional[str] = Field(default=None, max_length=255)
    academic_contact_email: Optional[EmailStr] = None
    academic_contact_phone: Optional[str] = Field(default=None, max_length=50)


class SchoolCenterMeta(BaseModel):
    estimated_students: Optional[int] = Field(default=None, ge=0, le=100000)
    city: Optional[str] = Field(default=None, max_length=120)
    country: Optional[str] = Field(default=None, max_length=120)
    timezone: Optional[str] = Field(default=None, max_length=80)
    academic_year: Optional[str] = Field(default=None, max_length=20)


# ---------------- top-level shapes ----------------

class SchoolBase(
    SchoolFiscalIdentity,
    SchoolCommercialContact,
    SchoolAcademicContact,
    SchoolCenterMeta,
):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9-]*$")
    logo_url: Optional[str] = Field(default=None, max_length=500)
    license_active: bool = True
    license_expires_at: Optional[datetime] = None


class SchoolCreate(SchoolBase):
    """Payload to create a school. Only super_admin can do this.

    Wizard de 4 pasos en el FE:
      1. Identidad (name + slug + fiscal)
      2. Plan (license_active + license_expires_at, plus license tier on
         the licenses endpoint after create)
      3. Contactos (commercial + academic)
      4. Revisión + center
    """
    pass


class SchoolUpdate(BaseModel):
    """Partial update. All fields optional. Only super_admin can do this."""
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9-]*$")
    logo_url: Optional[str] = Field(default=None, max_length=500)
    license_active: Optional[bool] = None
    license_expires_at: Optional[datetime] = None
    # Fiscal
    rut: Optional[str] = Field(default=None, max_length=40)
    razon_social: Optional[str] = Field(default=None, max_length=255)
    direccion_fiscal: Optional[str] = None
    tipo_persona: Optional[str] = Field(default=None, pattern=r"^(juridica|natural)$")
    # Contactos
    commercial_contact_name: Optional[str] = Field(default=None, max_length=255)
    commercial_contact_role: Optional[str] = Field(default=None, max_length=120)
    commercial_contact_email: Optional[EmailStr] = None
    commercial_contact_phone: Optional[str] = Field(default=None, max_length=50)
    academic_contact_name: Optional[str] = Field(default=None, max_length=255)
    academic_contact_email: Optional[EmailStr] = None
    academic_contact_phone: Optional[str] = Field(default=None, max_length=50)
    # Centro
    estimated_students: Optional[int] = Field(default=None, ge=0, le=100000)
    city: Optional[str] = Field(default=None, max_length=120)
    country: Optional[str] = Field(default=None, max_length=120)
    timezone: Optional[str] = Field(default=None, max_length=80)
    academic_year: Optional[str] = Field(default=None, max_length=20)


class SchoolResponse(SchoolBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SchoolSummary(BaseModel):
    """Lightweight shape used inside other responses (e.g. UserResponse.school).

    Branding fields surfaced to B2B students for chip + banner rendering
    (GH-STUDENT-EXPERIENCE · Bloque A · 2026-05-05).
    """
    id: UUID
    name: str
    slug: str
    logo_url: Optional[str] = None
    branding_primary_color: Optional[str] = None
    secondary_color: Optional[str] = None

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


# ---------------- Bloque A · detail shapes ----------------

class StudentLeadScore(BaseModel):
    """One student row scored as B2C lead potential.

    GH-SUPERADMIN-A · derived in real-time by `scoring_service.score_students_for_school`.
    """
    user_id: UUID
    email: str
    name: Optional[str] = None
    onboarding_status: str
    journey_progress: float = 0.0  # 0..1
    tests_completed: int = 0
    has_consolidated_profile: bool = False
    english_cefr_level: Optional[str] = None
    budget_band: Optional[str] = None
    preferred_countries: List[str] = Field(default_factory=list)
    score: int  # 0..100
    score_band: str  # 'cold' | 'warm' | 'hot'
    rationale: str  # 1-2 lines


class SchoolStudentsBreakdown(BaseModel):
    items: List[StudentLeadScore]
    total: int
    hot: int = 0
    warm: int = 0
    cold: int = 0


class SchoolTeamMember(BaseModel):
    id: UUID
    email: str
    name: Optional[str] = None
    role: str
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime


class SchoolTeam(BaseModel):
    school_admins: List[SchoolTeamMember] = Field(default_factory=list)
    psychologists: List[SchoolTeamMember] = Field(default_factory=list)


class SchoolUsageMetrics(BaseModel):
    students_total: int = 0
    students_active_30d: int = 0
    students_completed_journey: int = 0
    students_with_profile: int = 0
    tests_completed_30d: int = 0
    reports_generated_30d: int = 0
    activity_rate_pct: float = 0.0  # weekly active / total
    health_score: int = 0  # 0..100 · composite
    last_activity_at: Optional[datetime] = None


class SchoolDetailResponse(SchoolWithStats):
    """Rich detail used by SchoolDetailPage tabs."""
    metrics: SchoolUsageMetrics
    team: SchoolTeam
