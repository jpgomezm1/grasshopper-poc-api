import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Date, Text, Boolean, Integer, Float, ForeignKey, JSON, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.database import Base


class OnboardingStatus(str, enum.Enum):
    """User onboarding status."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class UserRole(str, enum.Enum):
    """User roles for multi-tenant access control.

    - student        · estudiante (B2C o B2B según school_id)
    - psychologist   · psicólogo del colegio · ve estudiantes de su escuela en read-only
    - school_admin   · admin del colegio · gestiona estudiantes + reportes + branding del colegio
    - gh_advisor     · orientador interno Grasshopper · ve B2C + B2B con contact_request
    - gh_commercial  · asesora comercial Grasshopper · pipeline Bitrix + contact requests
    - super_admin    · staff de Grasshopper · CRUD global de colegios, licencias, catálogo

    GH-S2-DB-01 · added 2026-04-30.
    GH-ROLES-001 · GH_ADVISOR + GH_COMMERCIAL added 2026-05-03 (migration 013).
    """
    STUDENT = "student"
    PSYCHOLOGIST = "psychologist"
    SCHOOL_ADMIN = "school_admin"
    GH_ADVISOR = "gh_advisor"
    GH_COMMERCIAL = "gh_commercial"
    SUPER_ADMIN = "super_admin"


# Convenience tuples used as role guards across endpoints
GH_TEAM_ROLES = (UserRole.GH_ADVISOR, UserRole.GH_COMMERCIAL, UserRole.SUPER_ADMIN)
GH_CONTACT_REQUEST_STATUSES = ("pending", "in_progress", "converted", "declined")


class School(Base):
    """B2B client (colegio) of Grasshopper.

    Owns the license + students + branding + reporting context. Created and
    managed by super_admin from the panel. School users (psychologist /
    school_admin) reference this via users.school_id.

    GH-S2-DB-02 · added 2026-04-30.
    """
    __tablename__ = "schools"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    logo_url = Column(String(500), nullable=True)

    license_active = Column(Boolean, default=True, nullable=False)
    license_expires_at = Column(DateTime, nullable=True)

    # Soft-delete · GH-S8-D-017 · super_admin marca archived_at; impide login
    # de usuarios del colegio archivado (revisado en auth_service).
    archived_at = Column(DateTime, nullable=True, index=True)

    # ---- Fiscal identity (migration 014) ----
    rut = Column(String(40), nullable=True)
    razon_social = Column(String(255), nullable=True)
    direccion_fiscal = Column(Text, nullable=True)
    tipo_persona = Column(String(20), nullable=True)  # 'juridica' | 'natural'

    # ---- Commercial contact (decisor) (migration 014) ----
    commercial_contact_name = Column(String(255), nullable=True)
    commercial_contact_role = Column(String(120), nullable=True)
    commercial_contact_email = Column(String(255), nullable=True)
    commercial_contact_phone = Column(String(50), nullable=True)

    # ---- Academic / operative contact (migration 014) ----
    academic_contact_name = Column(String(255), nullable=True)
    academic_contact_email = Column(String(255), nullable=True)
    academic_contact_phone = Column(String(50), nullable=True)

    # ---- Center metadata (migration 014) ----
    estimated_students = Column(Integer, nullable=True)
    city = Column(String(120), nullable=True)
    country = Column(String(120), nullable=True)
    timezone = Column(String(80), nullable=True)
    academic_year = Column(String(20), nullable=True)

    # Reverse relation to users that belong to this school
    users = relationship("User", back_populates="school")
    licenses = relationship(
        "License",
        back_populates="school",
        cascade="all, delete-orphan",
        order_by="License.created_at.desc()",
    )


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

    # Role · drives multi-rol auth (GH-S2-DB-01)
    role = Column(Enum(UserRole, name="userrole"), default=UserRole.STUDENT, nullable=False)

    # School membership · nullable for B2C students and super_admin (GH-S2-DB-03)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="SET NULL"), nullable=True, index=True)

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

    # Student preferences (GH-S6-FE-03/04 · alimenta el filtro pre-IA)
    # budget_band: "bajo" | "medio" | "alto" (qualitative · UI tier slider)
    # budget_max_usd: techo numérico opcional (más preciso para filtros)
    # preferred_countries: lista de strings ej. ["Estados Unidos", "Canadá"]
    budget_band = Column(String(20), nullable=True)
    budget_max_usd = Column(Integer, nullable=True)
    preferred_countries = Column(JSON, default=list, nullable=False)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Bitrix CRM lead status (GH-S10-DB-01 · inbound webhook BE-06)
    # bitrix_lead_id    · external ID of the Bitrix lead/contact (UUID-as-str)
    # bitrix_lead_status · 'new' | 'qualified' | 'contacted' | 'lost' | ...
    # bitrix_lead_status_at · last update timestamp from Bitrix
    bitrix_lead_id = Column(String(120), nullable=True, index=True)
    bitrix_lead_status = Column(String(40), nullable=True, index=True)
    bitrix_lead_status_at = Column(DateTime, nullable=True)

    # GH team contact request · GH-ROLES-001 · 2026-05-03
    # Allows a B2B student to opt-in to be visible by gh_advisor / gh_commercial.
    # NULL on all three columns = student has not requested contact (default).
    # Status pseudo-enum: 'pending' | 'in_progress' | 'converted' | 'declined'.
    gh_contact_requested_at = Column(DateTime, nullable=True)
    gh_contact_message = Column(Text, nullable=True)
    gh_contact_status = Column(String(20), nullable=True)

    # Habeas Data consent gate · GH-S11.5-BE-07 · D-026 · Ley 1581/2012 (Colombia)
    # ALL nullable for backward compat · gate logic treats NULL as "not granted".
    # is_minor logic: if birthdate is None → assume minor (more restrictive default).
    birthdate = Column(Date, nullable=True)
    consent_data_processing_at = Column(DateTime, nullable=True)
    consent_data_processing_version = Column(String(20), nullable=True)
    consent_crm_sync_at = Column(DateTime, nullable=True)
    consent_parental_at = Column(DateTime, nullable=True)

    # Relationships
    school = relationship("School", back_populates="users")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    english_test_result = relationship("EnglishTestResult", back_populates="user", uselist=False, cascade="all, delete-orphan")
    vocational_test_results = relationship("VocationalTestResult", back_populates="user", cascade="all, delete-orphan")
    saved_ofertas = relationship("SavedOferta", back_populates="user", cascade="all, delete-orphan")
    consolidated_profile = relationship(
        "ConsolidatedProfileCache",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


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

    # GH-S5-DB-02 · trazabilidad de origen del resultado
    # source: "internal" (test tomado en plataforma) | "external_upload" (parseado de PDF)
    source = Column(String(30), default="internal", nullable=False)
    external_upload_id = Column(
        UUID(as_uuid=True),
        ForeignKey("external_test_uploads.id", ondelete="SET NULL"),
        nullable=True,
    )

    user = relationship("User", back_populates="vocational_test_results")
    external_upload = relationship("ExternalTestUpload", back_populates="vocational_result")

    __table_args__ = (UniqueConstraint("user_id", "test_id", name="uq_user_test"),)


class ExternalTestUpload(Base):
    """User-uploaded PDF/image of a vocational test taken outside the platform.

    GH-S5-DB-01 · added 2026-04-30 (Sprint 5).

    Lifecycle:
        pending     · file stored, parser not invoked yet
        processing  · parser is running (background task)
        done        · parser succeeded with confidence above threshold
        needs_review · parser ran but confidence below threshold · UI offers manual edit/retry
        failed      · parser raised or returned unusable output

    PII guard: `raw_text` may contain the student's name/age. Never log it
    in stdout or in AI call metadata · only in DB (RLS-protected by user_id).
    """

    __tablename__ = "external_test_uploads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    test_type = Column(String(50), nullable=False, index=True)  # mbti · istrong · big5 · riasec
    file_path = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=True)
    content_type = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=True)

    parsing_status = Column(String(30), default="pending", nullable=False, index=True)
    raw_text = Column(Text, nullable=True)
    parsed_data = Column(JSON, nullable=True)
    confidence_score = Column(Float, nullable=True)  # 0.0 - 1.0
    parser_version = Column(String(20), nullable=True)
    error_message = Column(Text, nullable=True)

    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    parsed_at = Column(DateTime, nullable=True)

    vocational_result = relationship("VocationalTestResult", back_populates="external_upload", uselist=False)


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


class ConsolidatedProfileCache(Base):
    """Cache row for the IA-generated consolidated profile + recommendations.

    GH-S6-DB-01 · added 2026-04-30 (Sprint 6).

    One row per user. Reused if `profile_hash` matches the canonical hash
    of the current input AND `invalidated_at` is NULL AND `generated_at`
    is within TTL (24h default).

    Schema name on purpose differs from the Pydantic `ConsolidatedProfile`
    to avoid import-time clashes — we use `ConsolidatedProfileCache` for
    the ORM model and the JSONB payload contains the schema-validated
    Pydantic data.
    """

    __tablename__ = "consolidated_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Hash of the canonical input · cache key
    profile_hash = Column(String(64), nullable=False, index=True)

    # JSONB payloads (validated against Pydantic schemas before persisting)
    profile_data = Column(JSON, nullable=False)
    recommendations_data = Column(JSON, default=list, nullable=False)

    # Metadata
    model_used = Column(String(100), nullable=True)
    prompt_version = Column(String(50), nullable=True)
    tokens_input = Column(Integer, nullable=True)
    tokens_output = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)

    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    invalidated_at = Column(DateTime, nullable=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user = relationship("User", back_populates="consolidated_profile")


class Report(Base):
    """Generated PDF report (co-branded · 6 pages A4) + email send tracking.

    GH-S7-DB · added 2026-04-30 (Sprint 7).

    One row per generation event. Re-generation is allowed and creates a new
    row · the latest row is the "current" report. `profile_hash` snapshots
    the consolidated_profile hash used at render time so the FE can detect
    staleness vs the current cache.

    The PDF binary lives in storage (Supabase or stub) at:
        {user_id}/reports/<uuid>.pdf
    """

    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Storage
    file_path = Column(String(500), nullable=False)
    size_bytes = Column(Integer, nullable=True)

    # Profile snapshot at render time
    profile_hash = Column(String(64), nullable=True, index=True)
    school_id_at_render = Column(UUID(as_uuid=True), nullable=True)
    locale = Column(String(10), default="es-CO", nullable=False)

    # Metadata
    generator_version = Column(String(50), nullable=True)
    page_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Email send status
    email_sent = Column(Boolean, default=False, nullable=False)
    email_sent_at = Column(DateTime, nullable=True)
    email_to = Column(String(255), nullable=True)
    email_provider = Column(String(30), nullable=True)
    email_message_id = Column(String(255), nullable=True)
    email_reason = Column(String(120), nullable=True)


class LicenseTier(str, enum.Enum):
    """Plan tiers for school licenses · GH-S8-DB-01."""
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class LicenseStatus(str, enum.Enum):
    """License status · GH-S8-DB-01."""
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class License(Base):
    """Per-school license · GH-S8-BE-03.

    A school may have multiple license rows (renewals); the canonical
    one for runtime checks is the latest where status=active and
    (expires_at is null or expires_at > now()).

    `seats` is the cap on active students of the school. Enforced at
    student creation time by school_admin (GH-S8-BE-05).
    """

    __tablename__ = "licenses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tier = Column(String(30), default=LicenseTier.STARTER.value, nullable=False)
    seats = Column(Integer, default=50, nullable=False)
    starts_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    status = Column(String(30), default=LicenseStatus.ACTIVE.value, nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    school = relationship("School", back_populates="licenses")


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


class AuditLog(Base):
    """Audit trail of sensitive admin actions · GH-S8-BE-10.

    Logs every super_admin and school_admin mutation. Read-only from the
    panel (no edit/delete via API). Retention >= 1 year per Habeas Data
    operative compliance.
    """

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action = Column(String(80), nullable=False, index=True)
    resource_type = Column(String(60), nullable=False, index=True)
    resource_id = Column(String(120), nullable=True, index=True)
    payload = Column(JSON, nullable=True)
    ip_address = Column(String(60), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class InvitationStatus(str, enum.Enum):
    """Invitation lifecycle · GH-S9."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


class Invitation(Base):
    """Invitation to join a school · GH-S9.

    Created by school_admin (any role) or psychologist (only role=student).
    The token is opaque and URL-safe; the accept endpoint requires the token
    plus a password choice. Default lifetime is 14 days from creation.

    PII guard: `email` is stored lowercased. The accept-flow reuses the token
    only once · subsequent attempts return 410 Gone.
    """
    __tablename__ = "invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    email = Column(String(255), nullable=False, index=True)
    role = Column(String(30), nullable=False)  # student | psychologist
    token = Column(String(120), nullable=False, unique=True, index=True)
    status = Column(
        String(20),
        default=InvitationStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    accepted_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    invited_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class BitrixSyncStatus(str, enum.Enum):
    """Bitrix sync log status · GH-S10-DB-01."""
    PENDING = "pending"
    SUCCESS = "success"
    RETRY = "retry"
    FAILED = "failed"
    STUB = "stub"


class BitrixSyncLog(Base):
    """Outbound + inbound Bitrix CRM sync log · GH-S10-DB-01.

    One row per sync attempt. The same (entity_type, entity_id) may have
    multiple rows over time (history). Status transitions:

        pending → retry* → success
        pending → retry* → failed   (after N attempts exhausted)
        pending → stub              (no BITRIX_WEBHOOK_URL configured · D-020)
        pending → success           (inbound webhook acknowledged)

    PII guard: payload may contain student name/email/phone. Logs use
    masking (mask_email helper in bitrix_client). DB row is authoritative
    record but never logged in stdout / metrics.

    The `provider` field tracks whether the row came from a real Bitrix
    call ('bitrix') or the stub mock ('stub'). On S12 cutover this lets
    us audit which rows need replay.
    """

    __tablename__ = "bitrix_sync_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    entity_type = Column(String(40), nullable=False, index=True)
    entity_id = Column(String(120), nullable=False, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    action = Column(String(40), nullable=False)
    payload = Column(JSON, nullable=True)
    bitrix_response = Column(JSON, nullable=True)

    status = Column(String(20), default=BitrixSyncStatus.PENDING.value, nullable=False, index=True)
    provider = Column(String(20), default="stub", nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)

    synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


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


class ConsentAuditLog(Base):
    """Immutable audit trail for consent grants and revocations.

    GH-S11.5-BE-07 · D-026 · Ley 1581/2012 (Colombia) · Art. 8.

    Each row records a single consent state transition (or data right
    exercise) for a user. `event` is whitelisted by the service layer
    (NOT a DB enum · enables extension without migrations).

    Valid `event` values (curated whitelist · enforced in
    `app.services.consent_service.CONSENT_EVENTS`):

        data_processing.granted   · global Privacy Policy accepted
        data_processing.revoked   · titular asks for cessation
        crm_sync.granted          · opt-in to Bitrix share
        crm_sync.revoked          · opt-out / right to revoke
        parental.granted          · legal guardian authorization
        parental.revoked          · guardian withdraws authorization
        data_export               · titular invoked GET /me/data
        data_deletion             · titular invoked DELETE /me/data

    Read-only by design · no UPDATE / DELETE expected. user_id stays
    populated even after the user is soft-deleted (FK uses SET NULL).
    """

    __tablename__ = "consent_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event = Column(String(60), nullable=False, index=True)
    ip = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    policy_version = Column(String(20), nullable=True)
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
