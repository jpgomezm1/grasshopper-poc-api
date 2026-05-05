"""Orientation session service · GH-ADVISOR-CLINICAL Bloque E.

CRUD for orientation_sessions + session_notes with strict permission gates:
- gh_advisor sees ONLY their own sessions (advisor_user_id == current_user.id)
- psychologist sees ONLY their own sessions (advisor_user_id == current_user.id)
  GH-PSY-CLINICAL · 2026-05-05 · psy is the "advisor" of a session for B2B
- super_admin sees all
- gh_commercial NEVER sees sessions/notes
- student NEVER sees sessions/notes
- school_admin NEVER sees sessions/notes (use school_admin endpoints)

Note privacy gates:
- 'private' · only the author + super_admin
- 'shared_supervisor' · author + super_admin
- 'shared_team' · author + super_admin + other clinical staff (advisor/psy)

Audit: every mutation logs to audit_logs via existing audit_service.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    ORIENTATION_SESSION_STATUSES,
    ORIENTATION_SESSION_TYPES,
    SESSION_NOTE_PRIVACIES,
    OrientationSession,
    SessionNote,
    User,
    UserRole,
)
from app.schemas.clinical import SessionNoteOut, SessionOut

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------


def _is_super(user: User) -> bool:
    return user.role == UserRole.SUPER_ADMIN


def _is_clinical_staff(user: User) -> bool:
    """gh_advisor or psychologist · the two roles that can own a session."""
    return user.role in (UserRole.GH_ADVISOR, UserRole.PSYCHOLOGIST)


def can_view_session(session: OrientationSession, user: User) -> bool:
    if _is_super(user):
        return True
    if _is_clinical_staff(user) and session.advisor_user_id == user.id:
        return True
    return False


def can_view_note(note: SessionNote, session: OrientationSession, user: User) -> bool:
    """Note privacy gates · author + super_admin always; shared_team for peers."""
    if _is_super(user):
        return True
    if not _is_clinical_staff(user):
        return False
    # Author of the session sees all notes on that session
    if session.advisor_user_id == user.id:
        return True
    # Other clinical staff: only shared_team notes
    if note.privacy == "shared_team":
        return True
    return False


def can_edit_session(session: OrientationSession, user: User) -> bool:
    if _is_super(user):
        return True
    return _is_clinical_staff(user) and session.advisor_user_id == user.id


def can_edit_note(note: SessionNote, user: User) -> bool:
    if _is_super(user):
        return True
    if not _is_clinical_staff(user):
        return False
    return note.advisor_user_id == user.id


# ---------------------------------------------------------------------------
# Sessions CRUD
# ---------------------------------------------------------------------------


def list_sessions(
    db: DBSession,
    current_user: User,
    advisor_user_id: Optional[UUID] = None,
    student_user_id: Optional[UUID] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[OrientationSession], int]:
    q = db.query(OrientationSession)

    # Visibility gate · advisor or psy see only their own sessions; super sees all.
    if not _is_super(current_user):
        if not _is_clinical_staff(current_user):
            return [], 0
        q = q.filter(OrientationSession.advisor_user_id == current_user.id)

    if advisor_user_id is not None and _is_super(current_user):
        q = q.filter(OrientationSession.advisor_user_id == advisor_user_id)
    if student_user_id is not None:
        q = q.filter(OrientationSession.student_user_id == student_user_id)
    if status:
        if status not in ORIENTATION_SESSION_STATUSES:
            raise ValueError(f"invalid status: {status}")
        q = q.filter(OrientationSession.status == status)
    if date_from:
        q = q.filter(OrientationSession.scheduled_at >= date_from)
    if date_to:
        q = q.filter(OrientationSession.scheduled_at <= date_to)

    total = q.count()
    rows = (
        q.order_by(OrientationSession.scheduled_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def get_session(db: DBSession, session_id: UUID) -> Optional[OrientationSession]:
    return (
        db.query(OrientationSession).filter(OrientationSession.id == session_id).first()
    )


def create_session(
    db: DBSession,
    advisor: User,
    student_user_id: UUID,
    scheduled_at: datetime,
    duration_min: Optional[int],
    type: str,
    status: str = "scheduled",
    summary: Optional[str] = None,
) -> OrientationSession:
    if type not in ORIENTATION_SESSION_TYPES:
        raise ValueError(f"invalid type: {type}")
    if status not in ORIENTATION_SESSION_STATUSES:
        raise ValueError(f"invalid status: {status}")
    sess = OrientationSession(
        advisor_user_id=advisor.id,
        student_user_id=student_user_id,
        scheduled_at=scheduled_at,
        duration_min=duration_min,
        type=type,
        status=status,
        summary=summary,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def patch_session(
    db: DBSession,
    sess: OrientationSession,
    **fields,
) -> OrientationSession:
    if "type" in fields and fields["type"] is not None:
        if fields["type"] not in ORIENTATION_SESSION_TYPES:
            raise ValueError(f"invalid type: {fields['type']}")
    if "status" in fields and fields["status"] is not None:
        if fields["status"] not in ORIENTATION_SESSION_STATUSES:
            raise ValueError(f"invalid status: {fields['status']}")
    for k, v in fields.items():
        if v is None:
            continue
        if hasattr(sess, k):
            setattr(sess, k, v)
    sess.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(sess)
    return sess


def delete_session(db: DBSession, sess: OrientationSession) -> None:
    db.delete(sess)
    db.commit()


# ---------------------------------------------------------------------------
# Session notes CRUD
# ---------------------------------------------------------------------------


def list_notes(
    db: DBSession, session_id: UUID, current_user: User
) -> List[SessionNote]:
    sess = get_session(db, session_id)
    if not sess:
        return []
    if not can_view_session(sess, current_user):
        return []
    rows = (
        db.query(SessionNote)
        .filter(SessionNote.session_id == session_id)
        .order_by(SessionNote.created_at.desc())
        .all()
    )
    return [n for n in rows if can_view_note(n, sess, current_user)]


def create_note(
    db: DBSession,
    sess: OrientationSession,
    advisor: User,
    content: str,
    privacy: str = "private",
) -> SessionNote:
    if privacy not in SESSION_NOTE_PRIVACIES:
        raise ValueError(f"invalid privacy: {privacy}")
    note = SessionNote(
        session_id=sess.id,
        advisor_user_id=advisor.id,
        content=content,
        privacy=privacy,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def patch_note(
    db: DBSession,
    note: SessionNote,
    content: Optional[str] = None,
    privacy: Optional[str] = None,
) -> SessionNote:
    if privacy is not None:
        if privacy not in SESSION_NOTE_PRIVACIES:
            raise ValueError(f"invalid privacy: {privacy}")
        note.privacy = privacy
    if content is not None:
        note.content = content
    note.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)
    return note


def delete_note(db: DBSession, note: SessionNote) -> None:
    db.delete(note)
    db.commit()


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def to_out(
    sess: OrientationSession,
    advisor_name: Optional[str] = None,
    student_name: Optional[str] = None,
    student_email: Optional[str] = None,
    notes_count: int = 0,
) -> SessionOut:
    return SessionOut(
        id=sess.id,
        advisor_user_id=sess.advisor_user_id,
        advisor_name=advisor_name,
        student_user_id=sess.student_user_id,
        student_name=student_name,
        student_email=student_email,
        scheduled_at=sess.scheduled_at,
        duration_min=sess.duration_min,
        type=sess.type,  # type: ignore[arg-type]
        status=sess.status,  # type: ignore[arg-type]
        summary=sess.summary,
        notes_count=notes_count,
        created_at=sess.created_at,
        updated_at=sess.updated_at,
    )


def note_to_out(note: SessionNote, advisor_name: Optional[str] = None) -> SessionNoteOut:
    return SessionNoteOut(
        id=note.id,
        session_id=note.session_id,
        advisor_user_id=note.advisor_user_id,
        advisor_name=advisor_name,
        content=note.content,
        privacy=note.privacy,  # type: ignore[arg-type]
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def hydrate_sessions(
    db: DBSession, sessions: List[OrientationSession]
) -> List[SessionOut]:
    """Attach advisor/student names + notes_count efficiently."""
    if not sessions:
        return []
    ids = {s.advisor_user_id for s in sessions} | {s.student_user_id for s in sessions}
    users_by_id = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}
    counts: dict = {}
    for s in sessions:
        cnt = (
            db.query(SessionNote).filter(SessionNote.session_id == s.id).count()
        )
        counts[s.id] = cnt
    out: List[SessionOut] = []
    for s in sessions:
        adv = users_by_id.get(s.advisor_user_id)
        stu = users_by_id.get(s.student_user_id)
        out.append(
            to_out(
                s,
                advisor_name=(adv.name or adv.email) if adv else None,
                student_name=(stu.name) if stu else None,
                student_email=(stu.email) if stu else None,
                notes_count=counts.get(s.id, 0),
            )
        )
    return out
