"""Invitation service · GH-S9.

Encapsulates token generation, lifetime, validation and accept flow.

Permission matrix (enforced by callers, summarized here):
    - school_admin: may invite role=student or psychologist (own school).
    - psychologist: may invite role=student only (own school).
    - super_admin: may invite for any school (mostly used for QA).
    - student / anon: forbidden.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.db.models import Invitation, InvitationStatus, School, User, UserRole


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def role_can_invite(actor_role: UserRole, target_role: str) -> bool:
    """Permission rule for who can invite whom."""
    if actor_role == UserRole.SUPER_ADMIN:
        return target_role in ("student", "psychologist", "school_admin")
    if actor_role == UserRole.SCHOOL_ADMIN:
        return target_role in ("student", "psychologist")
    if actor_role == UserRole.PSYCHOLOGIST:
        return target_role == "student"
    return False


def find_active_invitation(
    db: DBSession, school_id: UUID, email: str
) -> Optional[Invitation]:
    """Return the latest pending invite for (school, email) if any."""
    return (
        db.query(Invitation)
        .filter(
            Invitation.school_id == school_id,
            Invitation.email == email.lower(),
            Invitation.status == InvitationStatus.PENDING.value,
        )
        .order_by(Invitation.created_at.desc())
        .first()
    )


def create_invitation(
    db: DBSession,
    *,
    school: School,
    email: str,
    role: str,
    invited_by: User,
    expires_in_days: int = 14,
) -> Invitation:
    """Create a new invitation. Caller MUST have validated permission."""
    email_norm = email.lower().strip()

    # avoid duplicate pendings
    existing = find_active_invitation(db, school.id, email_norm)
    if existing:
        # roll back to a fresh token so the email is still actionable
        existing.token = _generate_token()
        existing.expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        existing.role = role  # in case the role was upgraded
        existing.invited_by_user_id = invited_by.id
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    inv = Invitation(
        school_id=school.id,
        email=email_norm,
        role=role,
        token=_generate_token(),
        status=InvitationStatus.PENDING.value,
        expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
        invited_by_user_id=invited_by.id,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def revoke_invitation(db: DBSession, inv: Invitation) -> Invitation:
    if inv.status != InvitationStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending invitations can be revoked.",
        )
    inv.status = InvitationStatus.REVOKED.value
    inv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(inv)
    return inv


def expire_if_due(db: DBSession, inv: Invitation) -> Invitation:
    """Mark as expired if the lifetime is over · returns the (possibly mutated) row."""
    if (
        inv.status == InvitationStatus.PENDING.value
        and inv.expires_at <= datetime.utcnow()
    ):
        inv.status = InvitationStatus.EXPIRED.value
        inv.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(inv)
    return inv


def lookup_token(db: DBSession, token: str) -> Tuple[Invitation, str]:
    """Public-facing lookup. Returns (invitation, reason).

    reason ∈ {"ok", "not_found", "expired", "revoked", "accepted"}.
    """
    inv = db.query(Invitation).filter(Invitation.token == token).first()
    if not inv:
        return None, "not_found"  # type: ignore[return-value]
    if inv.status == InvitationStatus.REVOKED.value:
        return inv, "revoked"
    if inv.status == InvitationStatus.ACCEPTED.value:
        return inv, "accepted"
    if inv.expires_at <= datetime.utcnow():
        # late expire: persist
        inv.status = InvitationStatus.EXPIRED.value
        inv.updated_at = datetime.utcnow()
        db.commit()
        return inv, "expired"
    return inv, "ok"


def mark_accepted(db: DBSession, inv: Invitation, user: User) -> None:
    inv.status = InvitationStatus.ACCEPTED.value
    inv.accepted_at = datetime.utcnow()
    inv.accepted_user_id = user.id
    inv.updated_at = datetime.utcnow()
    db.commit()
