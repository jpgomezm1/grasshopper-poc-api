"""Pydantic schemas for License (GH-S8-BE-03/04)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


VALID_TIERS = {"starter", "pro", "enterprise"}
VALID_STATUS = {"active", "expired", "cancelled"}


class LicenseBase(BaseModel):
    tier: str = Field(default="starter")
    seats: int = Field(default=50, ge=1, le=100_000)
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    status: str = Field(default="active")
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("tier")
    @classmethod
    def _validate_tier(cls, v: str) -> str:
        v = (v or "").lower().strip()
        if v not in VALID_TIERS:
            raise ValueError(f"tier must be one of {sorted(VALID_TIERS)}")
        return v

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        v = (v or "").lower().strip()
        if v not in VALID_STATUS:
            raise ValueError(f"status must be one of {sorted(VALID_STATUS)}")
        return v


class LicenseCreate(LicenseBase):
    pass


class LicenseUpdate(BaseModel):
    tier: Optional[str] = None
    seats: Optional[int] = Field(default=None, ge=1, le=100_000)
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    status: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("tier")
    @classmethod
    def _validate_tier(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.lower().strip()
        if v not in VALID_TIERS:
            raise ValueError(f"tier must be one of {sorted(VALID_TIERS)}")
        return v

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.lower().strip()
        if v not in VALID_STATUS:
            raise ValueError(f"status must be one of {sorted(VALID_STATUS)}")
        return v


class LicenseResponse(LicenseBase):
    id: UUID
    school_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LicenseUsage(BaseModel):
    """Combined view of a school's current license + usage stats."""
    license: Optional[LicenseResponse] = None
    seats: int = 0
    seats_used: int = 0
    seats_remaining: int = 0
    is_expired: bool = False
    is_within_seats: bool = True
