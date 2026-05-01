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

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ProgramBase(BaseModel):
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


class ProgramUpdate(BaseModel):
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
