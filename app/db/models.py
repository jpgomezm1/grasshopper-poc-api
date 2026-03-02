import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer, ForeignKey, JSON, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.database import Base


class OnboardingStatus(str, enum.Enum):
    """User onboarding status."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class User(Base):
    """User accounts for authentication."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Auth credentials
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)

    # Profile info
    name = Column(String(255), nullable=True)

    # Onboarding status
    onboarding_status = Column(Enum(OnboardingStatus), default=OnboardingStatus.NOT_STARTED, nullable=False)
    onboarding_answers = Column(JSON, default=dict, nullable=False)

    # Contact info
    phone = Column(String(50), nullable=True)

    # English test
    english_test_completed = Column(Boolean, default=False, nullable=False)
    english_cefr_level = Column(String(10), nullable=True)

    # Password recovery
    password_reset_token = Column(String(255), nullable=True, unique=True)
    password_reset_expires = Column(DateTime, nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    english_test_result = relationship("EnglishTestResult", back_populates="user", uselist=False, cascade="all, delete-orphan")
    vocational_test_results = relationship("VocationalTestResult", back_populates="user", cascade="all, delete-orphan")
    saved_ofertas = relationship("SavedOferta", back_populates="user", cascade="all, delete-orphan")


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


class EnglishTestResult(Base):
    __tablename__ = "english_test_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    answers = Column(JSON, nullable=False)
    score = Column(Integer, nullable=False)
    total_questions = Column(Integer, nullable=False)
    cefr_level = Column(String(10), nullable=False)
    section_scores = Column(JSON, nullable=False)

    user = relationship("User", back_populates="english_test_result")


class VocationalTestResult(Base):
    __tablename__ = "vocational_test_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    test_id = Column(String(50), nullable=False)
    answers = Column(JSON, nullable=False)
    scores = Column(JSON, nullable=False)

    user = relationship("User", back_populates="vocational_test_results")

    __table_args__ = (UniqueConstraint("user_id", "test_id", name="uq_user_test"),)


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


class LeadProfile(Base):
    """Lead profiles from quick vocational quiz (no account required)."""
    __tablename__ = "lead_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Contact info (captured at end of quiz)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)

    # Quiz data
    answers = Column(JSON, nullable=False)
    profile_result = Column(JSON, nullable=False)

    # Tracking
    converted = Column(Boolean, default=False, nullable=False)
    source = Column(String(50), default="landing_quiz", nullable=False)
