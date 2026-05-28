"""Pydantic schemas for InstitutionCatalog · GH-LOCAL-CLIENT-CATALOG (2026-05-28)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InstitutionCatalogBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: Optional[str] = Field(default=None, max_length=60)
    country: Optional[str] = Field(default=None, max_length=120)
    country_raw: Optional[str] = Field(default=None, max_length=120)
    city: Optional[str] = Field(default=None, max_length=255)
    partner_group: Optional[str] = Field(default=None, max_length=120)
    programs_offered: Optional[List[str]] = None
    agreement_status: Optional[str] = Field(default=None, max_length=40)
    starting_date: Optional[date] = None
    end_date: Optional[date] = None
    contact_name: Optional[str] = Field(default=None, max_length=255)
    contact_email: Optional[str] = Field(default=None, max_length=255)
    website: Optional[str] = Field(default=None, max_length=500)
    territories: Optional[str] = Field(default=None, max_length=255)
    commissions: Optional[List[Dict[str, Any]]] = None
    source_sheet: Optional[str] = Field(default=None, max_length=60)
    active: bool = True


class InstitutionCatalogResponse(InstitutionCatalogBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InstitutionCatalogListResponse(BaseModel):
    items: List[InstitutionCatalogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class InstitutionCatalogFacets(BaseModel):
    """Aggregated counts for filter UI."""
    countries: List[Dict[str, Any]] = Field(default_factory=list)
    categories: List[Dict[str, Any]] = Field(default_factory=list)
    partner_groups: List[Dict[str, Any]] = Field(default_factory=list)
    agreement_statuses: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0
