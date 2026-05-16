"""Pydantic schemas for invitations · GH-S9.

The school panel uses these to invite students and (school_admin only)
psychologists. The accept flow is public-facing and requires only the
opaque token.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


InvitationRole = Literal["student", "psychologist"]
InvitationStatusLit = Literal["pending", "accepted", "expired", "revoked"]


class InvitationCreate(BaseModel):
    """Payload to create an invitation."""
    email: EmailStr
    role: InvitationRole = Field(..., description="student | psychologist")
    expires_in_days: Optional[int] = Field(
        default=14, ge=1, le=90, description="Lifetime · default 14 days"
    )


class InvitationResponse(BaseModel):
    id: UUID
    school_id: UUID
    email: str
    role: InvitationRole
    status: InvitationStatusLit
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    invited_by_user_id: Optional[UUID] = None
    invited_by_email: Optional[str] = None
    accept_url: Optional[str] = Field(
        default=None,
        description="Full URL the invitee should follow · only returned to the issuer.",
    )
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvitationListResponse(BaseModel):
    items: List[InvitationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class InvitationAccept(BaseModel):
    """Public accept payload · invitee chooses password + (optional) name."""
    password: str = Field(..., min_length=8, max_length=128)
    name: Optional[str] = Field(default=None, max_length=255)


class InvitationLookupResponse(BaseModel):
    """Response de GET /invitations/{token} · público · sin auth.

    `requires_auth` indica al FE si debe mostrar el formulario de login
    (True) o el formulario de registro con nueva contraseña (False).

    Siempre populado por el backend; es `Optional` solo para backward-compat
    con clientes que no lo esperan (lo ignoran silenciosamente).

    Campos de estado de error (reason != 'ok'):
        status      · 'ok' | 'expired' | 'revoked' | 'accepted'
        school_id   · siempre presente
        role        · siempre presente
        email       · siempre presente

    Campos adicionales cuando status == 'ok':
        school_name · nombre del colegio (puede ser None si school fue eliminado)
        expires_at  · ISO timestamp de expiración
        requires_auth · True si el email ya tiene cuenta activa con contraseña
    """

    status: str
    school_id: str
    role: str
    email: str
    school_name: Optional[str] = None
    expires_at: Optional[str] = None
    requires_auth: Optional[bool] = None


class InvitationAcceptResponse(BaseModel):
    """Mirror TokenResponse-shape so the FE can hop directly into the app."""
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    role: InvitationRole
    school_id: UUID
    email: str
