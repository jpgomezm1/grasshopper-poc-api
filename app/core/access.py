"""Session ownership enforcement · Habeas Data / Ley 1581 / IDOR protection.

GH-F1-SECURITY · S11.5-BE-05

Every endpoint that receives a `session_id` in path or query MUST call
`assert_session_access` before touching any session-scoped data.

Access matrix
─────────────
  anonymous caller (no JWT)      → 401
  student / B2C user             → only own sessions
  parent                         → only own sessions (parent's OWN sessions,
                                   not their children's journey sessions)
  psychologist                   → sessions that belong to a student enrolled
                                   in the same school (school_id match)
  gh_advisor / gh_commercial     → any authenticated session (B2C + B2B)
  school_admin                   → sessions of students in their school
  super_admin                    → unrestricted

TODO (JP): implement CohortPsychologistAssignment row-level check once
           psychologists are assigned to specific cohorts.  Today we use the
           coarser school_id match, which is still a substantial improvement
           over unauthenticated access.  Track in GH-F1-SEC-TODO-01.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.db.models import Session as JourneySession, User, UserRole

logger = logging.getLogger(__name__)

# Roles that have broad (non-ownership-bound) access to student journey data
_BROAD_ACCESS_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.GH_ADVISOR,
    UserRole.GH_COMMERCIAL,
}

# Roles that access sessions via their school association
_SCHOOL_STAFF_ROLES = {
    UserRole.SCHOOL_ADMIN,
    UserRole.PSYCHOLOGIST,
}


def assert_session_access(
    session_id: UUID,
    user: User,
    db: DBSession,
) -> JourneySession:
    """Load a journey session and assert the caller has read/write access.

    Parameters
    ----------
    session_id:
        UUID of the session being accessed.
    user:
        Authenticated caller (already resolved via `get_current_user`).
    db:
        Active database session.

    Returns
    -------
    JourneySession
        The loaded session object, ready to use — no second query needed.

    Raises
    ------
    HTTPException 404
        Session does not exist.
    HTTPException 403
        Session exists but the caller is not allowed to access it.
    """
    session: JourneySession | None = (
        db.query(JourneySession).filter(JourneySession.id == session_id).first()
    )

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Super-admin / gh_advisor / gh_commercial → unrestricted
    if user.role in _BROAD_ACCESS_ROLES:
        return session

    # Anonymous session (user_id=NULL) — only broad-access roles can read
    # these; regular users cannot claim ownership of an anonymous session.
    if session.user_id is None:
        # Defensive: broad-access already handled above.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Owner check — student, parent
    if user.role not in _SCHOOL_STAFF_ROLES:
        if session.user_id != user.id:
            logger.warning(
                "idor.blocked user=%s role=%s session=%s owner=%s",
                user.id,
                user.role,
                session_id,
                session.user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        return session

    # school_admin / psychologist → session owner must belong to same school
    # Fetch the session owner
    owner: User | None = (
        db.query(User).filter(User.id == session.user_id).first()
    )

    if owner is None:
        # Dangling session (owner deleted) — conservatively deny
        logger.warning(
            "idor.dangling_session session=%s no_owner", session_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if owner.school_id is None or owner.school_id != user.school_id:
        logger.warning(
            "idor.school_mismatch user=%s school=%s owner=%s owner_school=%s",
            user.id,
            user.school_id,
            owner.id,
            owner.school_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return session
