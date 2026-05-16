"""Bounded context: toolkit clínico del gh_advisor.

Contiene: constantes de enumeración (DOSSIER_SECTIONS, ORIENTATION_SESSION_TYPES,
ORIENTATION_SESSION_STATUSES, SESSION_NOTE_PRIVACIES), StudentDossierNote,
OrientationSession, SessionNote.

Modelos intencionalmente independientes de las relaciones User existentes
para mantener los eager-loading paths del dashboard rápidos.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.models.base import Base


# Allowed enum-string values · enforced at service layer (NOT a DB enum so we
# can extend without migrations).
DOSSIER_SECTIONS = (
    "demographics",
    "family",
    "academic",
    "hobbies",
    "constraints",
    "aspirations",
    "general",
)

ORIENTATION_SESSION_TYPES = (
    "first_contact",
    "exploration",
    "deepening",
    "decision",
    "followup",
)

ORIENTATION_SESSION_STATUSES = (
    "scheduled",
    "completed",
    "cancelled",
    "no_show",
)

SESSION_NOTE_PRIVACIES = (
    "private",                # solo el advisor autor + super_admin
    "shared_supervisor",      # autor + super_admin
    "shared_team",            # autor + super_admin + otros gh_advisor
    # GH-STUDENT-EXPERIENCE · 2026-05-05 · Bloque C
    # Nota explícitamente legible por el student dueño de la sesión.
    # No-op para permission gates clínicos · sólo `me_router` la expone.
    "shared_with_student",
)


class StudentDossierNote(Base):
    """Clinical dossier note authored by the gh_advisor · GH-ADVISOR-CLINICAL.

    One row per advisor-edit per section per student. The page treats the
    most-recent note per (student, section) as the canonical body but
    history is preserved (no soft-delete · use DELETE only).

    Privacy:
    - Visible only to gh_advisor + super_admin.
    - The student never sees their dossier.
    - PII guard: never log `content` in stdout / metrics.
    """
    __tablename__ = "student_dossier_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    advisor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    section = Column(String(40), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class OrientationSession(Base):
    """Orientation session · GH-ADVISOR-CLINICAL · Bloque E.

    Created and managed by gh_advisor. A session has 0..N session_notes.
    """
    __tablename__ = "orientation_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advisor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheduled_at = Column(DateTime, nullable=False, index=True)
    duration_min = Column(Integer, nullable=True)
    type = Column(String(20), nullable=False)
    status = Column(String(20), default="scheduled", nullable=False, index=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class SessionNote(Base):
    """Clinical note attached to a session · GH-ADVISOR-CLINICAL · Bloque E.

    Privacy gates (enforced in service layer):
    - 'private'            · only author advisor + super_admin
    - 'shared_supervisor'  · author + super_admin (same as private for now)
    - 'shared_team'        · author + super_admin + other gh_advisor

    Never visible to the student / school_admin / psychologist.
    """
    __tablename__ = "session_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("orientation_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    advisor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content = Column(Text, nullable=False)
    privacy = Column(String(20), default="private", nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
