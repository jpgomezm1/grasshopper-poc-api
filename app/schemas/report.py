"""Pydantic schemas for the PDF report flow (Sprint 7).

GH-S7-BE · added 2026-04-30.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class ReportRead(BaseModel):
    """Public representation of a Report row."""

    id: UUID
    user_id: UUID
    file_path: str
    size_bytes: Optional[int] = None
    profile_hash: Optional[str] = None
    school_id_at_render: Optional[UUID] = None
    locale: str = "es-CO"
    generator_version: Optional[str] = None
    page_count: Optional[int] = None
    created_at: datetime
    email_sent: bool = False
    email_sent_at: Optional[datetime] = None
    email_to: Optional[str] = None
    email_provider: Optional[str] = None
    email_message_id: Optional[str] = None
    email_reason: Optional[str] = None

    class Config:
        from_attributes = True


class ReportGenerateResponse(BaseModel):
    """Response of POST /reports/generate."""

    report: ReportRead
    download_url: str = Field(
        ..., description="Signed URL · TTL 1h · directo al PDF en storage"
    )
    is_stale: bool = Field(
        default=False,
        description=(
            "True si la consolidated_profile cache del usuario tiene un hash "
            "más fresco que el snapshot del reporte (FE puede invitar a regenerar)."
        ),
    )


class ReportSendRequest(BaseModel):
    """Body of POST /reports/{id}/send."""

    to: Optional[EmailStr] = Field(
        default=None,
        description=(
            "Email destino · si vacío, usa `current_user.email`. Solo psicólogo/admin "
            "pueden enviar a un email distinto del estudiante."
        ),
    )


class ReportSendResponse(BaseModel):
    """Response of POST /reports/{id}/send."""

    report: ReportRead
    delivered: bool
    provider: str = Field(..., description="resend | stub | otro")
    reason: Optional[str] = None
    message_id: Optional[str] = None
