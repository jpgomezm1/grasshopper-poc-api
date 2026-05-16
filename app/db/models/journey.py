"""Bounded context: journey del estudiante y catálogo de programas.

Contiene: JourneyStage, RouteStatus, JournalEntryType, Session, SessionEvent,
ProfileVersion, JournalEntry, Route, Snapshot, AdvisorLead, SavedOferta,
Program.

`Program` vive aquí porque es el catálogo de ofertas académicas que el
matching engine consume durante el journey, no una entidad administrativa
del colegio.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.models.base import Base


class JourneyStage(str, enum.Enum):
    """Journey stages matching frontend STAGES."""
    LANDING = "LANDING"
    CONTEXT = "CONTEXT"
    INTERESTS = "INTERESTS"
    CONSTRAINTS = "CONSTRAINTS"
    SYNTHESIS = "SYNTHESIS"
    ROUTES = "ROUTES"
    DONE = "DONE"


class RouteStatus(str, enum.Enum):
    """Route status options."""
    ACTIVE = "active"
    PAUSED = "paused"


class JournalEntryType(str, enum.Enum):
    """Journal entry types."""
    INTEREST = "interest"
    CONSTRAINT = "constraint"
    DECISION = "decision"
    REFLECTION = "reflection"
    MANUAL = "manual"


class Session(Base):
    """Journey session tracking."""
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # User relationship (optional - sessions can exist without user for anonymous access)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    # Current state
    current_step = Column(String(50), default="welcome", nullable=False)
    current_stage = Column(Enum(JourneyStage), default=JourneyStage.LANDING, nullable=False)
    is_paused = Column(Boolean, default=False, nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False)

    # Answers stored as JSON
    answers = Column(JSON, default=dict, nullable=False)
    completed_steps = Column(JSON, default=list, nullable=False)
    selected_routes = Column(JSON, default=list, nullable=False)

    # Relationships
    user = relationship("User", back_populates="sessions")
    events = relationship("SessionEvent", back_populates="session", cascade="all, delete-orphan")
    profile_versions = relationship("ProfileVersion", back_populates="session", cascade="all, delete-orphan")
    journal_entries = relationship("JournalEntry", back_populates="session", cascade="all, delete-orphan")
    routes = relationship("Route", back_populates="session", cascade="all, delete-orphan")
    snapshots = relationship("Snapshot", back_populates="session", cascade="all, delete-orphan")
    advisor_lead = relationship("AdvisorLead", back_populates="session", uselist=False, cascade="all, delete-orphan")


class SessionEvent(Base):
    """Session events/actions tracking."""
    __tablename__ = "session_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Event details
    event_type = Column(String(50), nullable=False)  # answer, navigation, selection
    step_id = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=True)  # The actual answer/action data

    # Relationship
    session = relationship("Session", back_populates="events")


class ProfileVersion(Base):
    """Versioned profile snapshots."""
    __tablename__ = "profile_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    version = Column(Integer, nullable=False)

    # Profile data
    answers = Column(JSON, nullable=False)
    derived_tags = Column(JSON, default=list, nullable=False)

    # Relationship
    session = relationship("Session", back_populates="profile_versions")


class JournalEntry(Base):
    """Journal/bitacora entries."""
    __tablename__ = "journal_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Entry data
    content = Column(Text, nullable=False)
    entry_type = Column(Enum(JournalEntryType), nullable=False)
    tags = Column(JSON, default=list, nullable=False)
    auto_generated = Column(Boolean, default=False, nullable=False)

    # Relationship
    session = relationship("Session", back_populates="journal_entries")


class Route(Base):
    """Academic routes (max 3 active per session)."""
    __tablename__ = "routes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Route data
    key = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    why = Column(Text, nullable=False)
    what_it_looks_like = Column(Text, nullable=False)
    next_step = Column(Text, nullable=False)

    # Status
    status = Column(Enum(RouteStatus), default=RouteStatus.ACTIVE, nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)

    # Relationship
    session = relationship("Session", back_populates="routes")


class Snapshot(Base):
    """Generated plan snapshots."""
    __tablename__ = "snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Snapshot data
    profile = Column(JSON, nullable=False)
    routes = Column(JSON, nullable=False)
    derived_tags = Column(JSON, default=list, nullable=False)

    # Relationship
    session = relationship("Session", back_populates="snapshots")


class AdvisorLead(Base):
    """Advisor contact submissions."""
    __tablename__ = "advisor_leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Contact info
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)

    # Generated brief
    advisor_brief = Column(Text, nullable=True)

    # Relationship
    session = relationship("Session", back_populates="advisor_lead")


class SavedOferta(Base):
    """User's saved/bookmarked ofertas."""
    __tablename__ = "saved_ofertas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    oferta_id = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String(50), default="interested", nullable=False)

    user = relationship("User", back_populates="saved_ofertas")

    __table_args__ = (UniqueConstraint("user_id", "oferta_id", name="uq_user_oferta"),)


class Program(Base):
    """Catalogue program · GH-S8-BE-06.

    Replaces the in-memory `app.data.ofertas` for the canonical catalogue.
    Imported from Excel via scripts/import_catalog.py and edited via the
    super admin panel.
    """

    __tablename__ = "programs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(String(120), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)

    country = Column(String(120), nullable=False, index=True)
    city = Column(String(120), nullable=True)
    institution = Column(String(255), nullable=False, index=True)

    type = Column(String(60), nullable=False, index=True)
    area = Column(String(120), nullable=True)
    subject = Column(String(255), nullable=True)

    duration_months = Column(Integer, nullable=False)
    cost_total = Column(Integer, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    budget_tier = Column(String(20), nullable=False, index=True)
    alliance_type = Column(String(30), default="estandar", nullable=False)
    language_requirement = Column(String(50), nullable=True)

    active = Column(Boolean, default=True, nullable=False, index=True)
    raw = Column(JSON, nullable=True)

    # ---- Editorial fields (Bloque B · migration 015) ----
    description_long = Column(Text, nullable=True)
    institution_logo_url = Column(String(500), nullable=True)
    language_requirement_detail = Column(Text, nullable=True)
    images = Column(JSON, nullable=True)
    highlights = Column(JSON, nullable=True)
    syllabus = Column(JSON, nullable=True)
    academic_requirements = Column(JSON, nullable=True)
    admission_dates = Column(JSON, nullable=True)
    scholarships = Column(JSON, nullable=True)
    employability = Column(JSON, nullable=True)
    ranking = Column(JSON, nullable=True)
    testimonials = Column(JSON, nullable=True)
    location = Column(JSON, nullable=True)
    accreditations = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
