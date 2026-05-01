"""Pydantic schemas for AuditLog (GH-S8-BE-10/11)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    user_email: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminStatsOverview(BaseModel):
    total_schools: int
    active_schools: int
    archived_schools: int
    active_licenses: int
    expired_licenses: int
    total_students: int
    students_active_30d: int
    reports_generated_30d: int
    tests_completed_30d: int
    top_programs: List[Dict[str, Any]] = []
    top_schools: List[Dict[str, Any]] = []
    cached_at: datetime
