"""Pydantic schemas for Program (catalogue · GH-S8-BE-06)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, List, Any, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


VALID_BUDGET_TIERS = {"low", "medium", "high", "premium"}
VALID_ALLIANCES = {"preferencial", "estandar", "convenio"}
VALID_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD", "CHF", "COP"}

# Bloque B · expanded program types (migration 015)
VALID_PROGRAM_TYPES = {
    "pregrado",
    "posgrado",
    "maestria",
    "doctorado",
    "diplomado",
    "especializacion",
    "curso_corto",
    "vacacional",
    "intercambio",
    "bootcamp",
    "mba",
    "bachelor",  # legacy
}

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# ---------------------------------------------------------------------------
# Editorial nested shapes (loose · accept extra keys for forward-compat)
# ---------------------------------------------------------------------------


class ProgramImage(BaseModel):
    url: str
    alt: Optional[str] = None
    caption: Optional[str] = None
    order: int = 0

    model_config = ConfigDict(extra="allow")


class ProgramTestimonial(BaseModel):
    quote: str
    name: Optional[str] = None
    year: Optional[int] = None
    link: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ProgramSyllabusUnit(BaseModel):
    semester: Optional[str] = None
    courses: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ProgramAcademicReq(BaseModel):
    gpa: Optional[float] = None
    courses: Optional[List[str]] = None
    exam: Optional[str] = None
    interview: Optional[bool] = None

    model_config = ConfigDict(extra="allow")


class ProgramAdmissionDate(BaseModel):
    cohort: Optional[str] = None
    application_deadline: Optional[str] = None
    start_date: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ProgramScholarship(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    coverage_pct: Optional[int] = None
    requirements: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ProgramEmployability(BaseModel):
    placement_rate_pct: Optional[float] = None
    avg_salary: Optional[int] = None
    top_employers: Optional[List[str]] = None
    notes: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ProgramRanking(BaseModel):
    global_rank: Optional[int] = None
    regional_rank: Optional[int] = None
    by_area: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(extra="allow")


class ProgramLocation(BaseModel):
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    neighborhood: Optional[str] = None
    monthly_cost_usd: Optional[int] = None

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Editorial mixin · stays loose because the FE may grow these shapes.
# ---------------------------------------------------------------------------


class ProgramEditorialFields(BaseModel):
    description_long: Optional[str] = None
    institution_logo_url: Optional[str] = Field(default=None, max_length=500)
    language_requirement_detail: Optional[str] = None
    images: Optional[List[Dict[str, Any]]] = None
    highlights: Optional[List[str]] = None
    syllabus: Optional[List[Dict[str, Any]]] = None
    academic_requirements: Optional[Dict[str, Any]] = None
    admission_dates: Optional[List[Dict[str, Any]]] = None
    scholarships: Optional[List[Dict[str, Any]]] = None
    employability: Optional[Dict[str, Any]] = None
    ranking: Optional[Dict[str, Any]] = None
    testimonials: Optional[List[Dict[str, Any]]] = None
    location: Optional[Dict[str, Any]] = None
    accreditations: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    # F-002 etapa 1 (2026-05-21) · Ruta migratoria laboral + ROI
    visa_type: Optional[str] = Field(default=None, max_length=40)
    visa_max_years_work: Optional[int] = Field(default=None, ge=0, le=20)
    visa_requires_degree_alignment: Optional[bool] = None
    visa_notes: Optional[str] = None
    entry_salary_local_usd: Optional[int] = Field(default=None, ge=0)
    living_cost_city_usd_year: Optional[int] = Field(default=None, ge=0)
    # F-003 etapa 1 (2026-05-28) · Financial Fit / Becas LatAm
    scholarships_for_latam: Optional[bool] = None


class ProgramBase(ProgramEditorialFields):
    program_id: str = Field(..., min_length=2, max_length=120)
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=255)
    country: str = Field(..., min_length=2, max_length=120)
    city: Optional[str] = Field(default=None, max_length=120)
    institution: str = Field(..., min_length=2, max_length=255)
    type: str = Field(..., min_length=2, max_length=60)
    area: Optional[str] = Field(default=None, max_length=120)
    subject: Optional[str] = Field(default=None, max_length=255)
    duration_months: int = Field(..., ge=1, le=120)
    cost_total: int = Field(..., ge=0)
    currency: str = Field(default="USD")
    budget_tier: str = Field(...)
    alliance_type: str = Field(default="estandar")
    language_requirement: Optional[str] = Field(default=None, max_length=50)
    active: bool = True

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in VALID_PROGRAM_TYPES:
            raise ValueError(
                f"type must be one of {sorted(VALID_PROGRAM_TYPES)}"
            )
        return v

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError("slug must be lowercase alphanumeric with optional hyphens")
        return v

    @field_validator("budget_tier")
    @classmethod
    def _validate_tier(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in VALID_BUDGET_TIERS:
            raise ValueError(f"budget_tier must be one of {sorted(VALID_BUDGET_TIERS)}")
        return v

    @field_validator("alliance_type")
    @classmethod
    def _validate_alliance(cls, v: str) -> str:
        v = (v or "estandar").strip().lower()
        if v not in VALID_ALLIANCES:
            raise ValueError(f"alliance_type must be one of {sorted(VALID_ALLIANCES)}")
        return v

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: str) -> str:
        v = (v or "USD").strip().upper()
        if v not in VALID_CURRENCIES:
            raise ValueError(f"currency must be one of {sorted(VALID_CURRENCIES)}")
        return v


class ProgramCreate(ProgramBase):
    raw: Optional[Dict[str, Any]] = None


class ProgramUpdate(ProgramEditorialFields):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=255)
    country: Optional[str] = Field(default=None, min_length=2, max_length=120)
    city: Optional[str] = Field(default=None, max_length=120)
    institution: Optional[str] = Field(default=None, min_length=2, max_length=255)
    type: Optional[str] = Field(default=None, min_length=2, max_length=60)
    area: Optional[str] = Field(default=None, max_length=120)
    subject: Optional[str] = Field(default=None, max_length=255)
    duration_months: Optional[int] = Field(default=None, ge=1, le=120)
    cost_total: Optional[int] = Field(default=None, ge=0)
    currency: Optional[str] = None
    budget_tier: Optional[str] = None
    alliance_type: Optional[str] = None
    language_requirement: Optional[str] = Field(default=None, max_length=50)
    active: Optional[bool] = None

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in VALID_PROGRAM_TYPES:
            raise ValueError(
                f"type must be one of {sorted(VALID_PROGRAM_TYPES)}"
            )
        return v

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError("slug must be lowercase alphanumeric with optional hyphens")
        return v

    @field_validator("budget_tier")
    @classmethod
    def _validate_tier(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in VALID_BUDGET_TIERS:
            raise ValueError(f"budget_tier must be one of {sorted(VALID_BUDGET_TIERS)}")
        return v

    @field_validator("alliance_type")
    @classmethod
    def _validate_alliance(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in VALID_ALLIANCES:
            raise ValueError(f"alliance_type must be one of {sorted(VALID_ALLIANCES)}")
        return v

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().upper()
        if v not in VALID_CURRENCIES:
            raise ValueError(f"currency must be one of {sorted(VALID_CURRENCIES)}")
        return v


class ProgramResponse(ProgramBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProgramListResponse(BaseModel):
    items: List[ProgramResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProgramImportReport(BaseModel):
    total_rows: int
    valid_rows: int
    inserted: int
    updated: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    committed: bool
