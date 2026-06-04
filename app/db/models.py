import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Date, Text, Boolean, Integer, Float, ForeignKey, JSON, Enum, UniqueConstraint, LargeBinary
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator
import enum

from app.db.database import Base


# ---------------------------------------------------------------------------
# Encrypted field types (GH-F1-SECURITY · Tarea 4 · clinical_analysis_cache)
# ---------------------------------------------------------------------------

class EncryptedJSON(TypeDecorator):
    """SQLAlchemy TypeDecorator that transparently encrypts/decrypts a JSON field.

    Storage type: LargeBinary (BYTEA in PostgreSQL).
    The cipher is AES-256-GCM via app.core.crypto.

    Usage:
        column = Column(EncryptedJSON, nullable=True)

    Reading returns the deserialized Python object (dict / list / etc.).
    Writing accepts any JSON-serializable Python object.
    None values pass through as-is (no encryption of NULL).
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        from app.core.crypto import encrypt_json
        return encrypt_json(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        from app.core.crypto import decrypt_json
        return decrypt_json(value)


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
    PARENT = "parent"  # GH-SCHOOL-ADMIN-025 · 2026-05-04 · sees only own children


# Convenience tuples used as role guards across endpoints
GH_TEAM_ROLES = (UserRole.GH_ADVISOR, UserRole.GH_COMMERCIAL, UserRole.SUPER_ADMIN)
SCHOOL_STAFF_ROLES = (UserRole.SCHOOL_ADMIN, UserRole.PSYCHOLOGIST)
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

    # Branding extensions · GH-SCHOOL-ADMIN-030 · 2026-05-04 (migration 030)
    secondary_color = Column(String(20), nullable=True)
    locale = Column(String(10), nullable=True, default="es-CO")

    # GH-STUDENT-EXPERIENCE · 2026-05-05 (migration 031) · Bloque A
    # Color principal de marca que se expone al student (chip + banner B2B).
    # Independiente de `secondary_color` (uso interno school_admin).
    branding_primary_color = Column(String(20), nullable=True)

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

    # F-005 · aceptación del aviso legal pre-test, por tipo de test.
    # Shape: { test_id: {"accepted_at": ISO8601, "version": str} }. nullable
    # para filas previas (se lee con `or {}`).
    test_disclaimers = Column(JSON, default=dict, nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Super-admin lifecycle · GH-SUPERADMIN-EXPERIENCE · migration 033
    # `suspended_at` decouples soft-suspend (super_admin action) from is_active
    # (legacy soft-delete). NULL = not suspended. When set, all auth-protected
    # endpoints reject the user.
    suspended_at = Column(DateTime, nullable=True)
    # `last_login_at` stamped on each successful login (auth.login). Drives
    # DAU/MAU/retention metrics in /admin/stats/usage.
    last_login_at = Column(DateTime, nullable=True, index=True)
    # `created_by_user_id` audit who created this user (super_admin via
    # /admin/users POST or invitation flow). NULL for self-registered users
    # and pre-migration data.
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

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

    # CRM pipeline · GH-CRM-001 · 2026-05-03 (migration 016)
    # Tracks the lead's position in the commercial funnel, separate from
    # `gh_contact_status` (which is a student-driven request flag).
    # Statuses: pending · contacted · qualified · converted · declined
    # NULL = no pipeline action yet (default for every user).
    lead_pipeline_status = Column(String(20), nullable=True, index=True)
    lead_pipeline_status_at = Column(DateTime, nullable=True)
    # Optimistic locking · QA-AUD-072 · migration 037
    # Incrementado en cada PATCH de status. El cliente envía expected_version
    # para garantizar compare-and-swap atómico (evita race conditions).
    pipeline_status_version = Column(Integer, nullable=False, server_default="1", default=1)

    # CRM AI analysis cache · GH-CRM-001 · 2026-05-03 (migration 016)
    # JSONB payload · {rationale, program_matches[], next_actions[]}
    # Service enforces TTL (7d) by comparing ai_analysis_cached_at with
    # the canonical scoring + demographics hash before re-rendering.
    ai_analysis_cache = Column(JSON, nullable=True)
    ai_analysis_cached_at = Column(DateTime, nullable=True)

    # Lead assignment · GH-COMMPROD-B2 · 2026-05-03 (migration 018)
    # Only meaningful when the user IS a lead (student / B2C). Service
    # validates that the target user role is gh_commercial / gh_advisor.
    # NULL = unassigned.
    assigned_to_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at = Column(DateTime, nullable=True)

    # Clinical analysis cache · GH-ADVISOR-CLINICAL · 2026-05-04 (migration 024)
    # JSONB payload validated against ClinicalAnalysis Pydantic schema.
    # Service enforces 30d TTL. Tone is clinical / private (advisor-only),
    # NEVER surfaced to the student. Different from `consolidated_profile`
    # which is the cálido/positivo public profile.
    clinical_analysis_cache = Column(JSON, nullable=True)
    # GH-F1-SECURITY · Tarea 4 · migration 037 · cifrado at-rest AES-256-GCM (Ley 1090 + Ley 1581).
    # `clinical_analysis_cache` (JSON) se conserva para backward compat durante FASE B (backfill).
    # New writes use `clinical_analysis_cache_enc` (BYTEA · EncryptedJSON TypeDecorator).
    clinical_analysis_cache_enc = Column(EncryptedJSON, nullable=True)
    clinical_analysis_cached_at = Column(DateTime, nullable=True)

    # GH-STUDENT-EXPERIENCE · 2026-05-05 (migration 031) · Bloque J
    # Stamped once when the student crosses the journey-complete criteria
    # (onboarding done + 3+ tests + 2+ routes). Used by the dashboard to
    # auto-redirect a single time.
    journey_completed_at = Column(DateTime, nullable=True)

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

    def __repr__(self) -> str:
        return f"<User id={self.id}>"


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

    def __repr__(self) -> str:
        return f"<Session id={self.id}>"


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
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

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

    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

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
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    vocational_result = relationship("VocationalTestResult", back_populates="external_upload", uselist=False)


class SavedOferta(Base):
    """User's saved/bookmarked ofertas."""
    __tablename__ = "saved_ofertas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    oferta_id = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String(50), default="interested", nullable=False)

    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

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
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)


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

    def __repr__(self) -> str:
        return f"<License id={self.id}>"


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

    # ---- F-002 etapa 1 (2026-05-21) · Ruta migratoria laboral + ROI ----
    # GH-LOCAL-CLIENT-MODULES · cliente pidió en docx §1 párr 2 calculadora
    # ROI + visados (OPT/CPT/PGWP/etc.) integrada al catálogo.
    visa_type = Column(String(40), nullable=True)
    visa_max_years_work = Column(Integer, nullable=True)
    visa_requires_degree_alignment = Column(Boolean, nullable=True)
    visa_notes = Column(Text, nullable=True)
    entry_salary_local_usd = Column(Integer, nullable=True)
    living_cost_city_usd_year = Column(Integer, nullable=True)

    # F-003 etapa 1 (2026-05-28) · Financial Fit / Becas LatAm
    # Cliente docx §1 párr 3 + §3.G: campo booleano para priorizar opciones con
    # beca explícita para estudiantes latinoamericanos en el matching IA.
    # NULL = no curado (no asumir). TRUE/FALSE = decisión deliberada.
    scholarships_for_latam = Column(Boolean, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# F-002 etapa 1 · 2026-05-21 · catálogo de tipos de visa conocidos (lista abierta).
# Sirve como helper de UI/validación, no se persiste como FK del schema (mantenemos
# `Program.visa_type` como String libre para permitir variantes nuevas sin migration).
VISA_TYPES = (
    "OPT",        # USA · Optional Practical Training (12-36 meses según STEM)
    "CPT",        # USA · Curricular Practical Training (durante estudios)
    "H-1B",       # USA · trabajo post-OPT (lottery)
    "PGWP",       # Canada · Post-Graduation Work Permit (hasta 3 años)
    "PSW",        # UK · Graduate Visa / Post-Study Work (2-3 años)
    "Stayback",   # Ireland · Third Level Graduate Programme (1-2 años)
    "TVR",        # España · Tarjeta de Residencia (búsqueda de empleo 1 año)
    "Subclass-485",  # Australia · Temporary Graduate
    "PostStudyWork",  # NZ · Post-Study Work Visa
    "ICT",        # genérico · Intra-Company Transfer
    "Self-Sponsored",
    "None",
)


class InstitutionCatalog(Base):
    """Institutions catalogue · GH-LOCAL-CLIENT-CATALOG (2026-05-28).

    Catálogo de instituciones reales + relaciones comerciales importado del
    xlsx del cliente. Separado de `programs` porque su grano es distinto:
    `programs` describe programas concretos vendibles (cost, duration);
    `institutions_catalog` describe la institución y el estado del contrato.

    Read-mostly: poblada por `scripts/import_institutions.py` desde el xlsx.
    """

    __tablename__ = "institutions_catalog"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    category = Column(String(60), nullable=True, index=True)
    country = Column(String(120), nullable=True, index=True)
    country_raw = Column(String(120), nullable=True)
    city = Column(String(255), nullable=True)
    partner_group = Column(String(120), nullable=True, index=True)
    programs_offered = Column(JSON, nullable=True)
    agreement_status = Column(String(40), nullable=True, index=True)
    starting_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    contact_name = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)
    website = Column(String(500), nullable=True)
    territories = Column(String(255), nullable=True)
    commissions = Column(JSON, nullable=True)
    source_sheet = Column(String(60), nullable=True)
    active = Column(Boolean, default=True, nullable=False, index=True)
    raw = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class HumanInterventionNote(Base):
    """Advisor-only private notes on a lead · F-006 (2026-05-28).

    Cliente docx §3: campo en el perfil del estudiante que solo el advisor
    asignado pueda ver para anotar qué tan cerca está de cerrar el contrato
    de Counselling Premium. NUNCA expuesto al student, psy ni otros advisors.
    """

    __tablename__ = "human_intervention_notes"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    notes = Column(Text, nullable=True)
    closeness_level = Column(String(20), nullable=True)
    updated_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


HUMAN_INTERVENTION_LEVELS = (
    "cold",         # primer contacto · no hay traction
    "warm",         # respondió, interés inicial
    "hot",          # demos hechas, evaluando
    "closing",      # negociando precio / firma
    "closed_won",   # contrato firmado
    "closed_lost",  # perdido (no compite, no quiere, eligió otro)
)


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

    def __repr__(self) -> str:
        return f"<Invitation id={self.id}>"


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

    def __repr__(self) -> str:
        return f"<BitrixSyncLog id={self.id}>"


class LeadProfile(Base):
    """Lead profiles from quick vocational quiz (no account required)."""
    __tablename__ = "lead_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

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

    def __repr__(self) -> str:
        return f"<LeadProfile id={self.id}>"


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


# ===========================================================================
# gh_commercial productivity sprint · 2026-05-03
# Migrations 017-021. Models below are intentionally kept independent of the
# legacy `User`/`School` relationships (no back_populates) to minimize churn
# in the existing eager-loading paths used by HomeDashboard / school panel.
# ===========================================================================


class Notification(Base):
    """In-app notification for any role · GH-COMMPROD-A1 (migration 017).

    Created by hooks across services (lead assigned · pipeline change · SLA
    breach · task due soon · contact request created · @mention received).
    The frontend bell icon polls /notifications/me?status=unread.
    """
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = Column(String(60), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    data = Column(JSON, nullable=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)


class PushSubscription(Base):
    """Web Push API subscription · GH-COMMPROD-A2 (migration 017).

    One row per (user, browser/device). The endpoint URL is unique across
    all users (it's effectively a globally unique push channel).
    """
    __tablename__ = "push_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)


class TaskPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class TaskStatus(str, enum.Enum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class Task(Base):
    """Reminder / to-do · GH-COMMPROD-B3 (migration 018)."""
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assigned_to_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    description = Column(Text, nullable=False)
    due_at = Column(DateTime, nullable=True)
    priority = Column(String(10), default=TaskPriority.NORMAL.value, nullable=False)
    status = Column(String(10), default=TaskStatus.OPEN.value, nullable=False)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    notified_due_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<Task id={self.id}>"


class LeadTag(Base):
    """Catalog of tags applicable to leads · GH-COMMPROD-D1 (migration 019)."""
    __tablename__ = "lead_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(60), nullable=False, unique=True)
    label = Column(String(120), nullable=False)
    color = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)


class LeadTagAssignment(Base):
    """Many-to-many between leads (users) and tags · GH-COMMPROD-D1."""
    __tablename__ = "lead_tag_assignments"
    __table_args__ = (
        UniqueConstraint("lead_user_id", "tag_id", name="uq_lead_tag"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_id = Column(
        UUID(as_uuid=True),
        ForeignKey("lead_tags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # created_at · migration 041_auditability_and_indices
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)


class SavedSearch(Base):
    """Personal saved CRM filter view · GH-COMMPROD-D3 (migration 020)."""
    __tablename__ = "saved_searches"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_saved_search_per_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(120), nullable=False)
    filters = Column(JSON, nullable=False)
    pinned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)


class LeadComment(Base):
    """Threaded comment on a lead · GH-COMMPROD-F1 (migration 020)."""
    __tablename__ = "lead_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    body = Column(Text, nullable=False)
    mentions = Column(JSON, nullable=True)
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("lead_comments.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    edited_at = Column(DateTime, nullable=True)


class PipelineStage(Base):
    """Customizable pipeline stage · GH-COMMPROD-B6 (migration 021)."""
    __tablename__ = "pipeline_stages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(40), nullable=False, unique=True)
    label = Column(String(120), nullable=False)
    color = Column(String(20), nullable=True)
    order_index = Column(Integer, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AutoAssignRule(Base):
    """Rule that decides which gh_* gets a freshly created lead · GH-COMMPROD-E1.

    Strategies:
        round_robin    · cycle through gh_commercial actives
        least_loaded   · pick the gh_commercial with fewest open leads
        by_country     · `config = {"colombia": "<user_id>", ...}`
        by_language    · `config = {"es": "<id>", "en": "<id>"}`
    """
    __tablename__ = "auto_assign_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy = Column(String(40), nullable=False)
    config = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=100, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PipelineRule(Base):
    """IFTTT-style rule applied on lead state changes · GH-COMMPROD-E2."""
    __tablename__ = "pipeline_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    condition = Column(JSON, nullable=False)
    action = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ===========================================================================
# gh_advisor clinical toolkit · 2026-05-04
# Migrations 022-024. Models below are intentionally independent of the legacy
# `User` relationships to keep eager-loading paths fast.
# ===========================================================================


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


# =============================================================================
# GH-SCHOOL-ADMIN · 2026-05-04 · Sprint school_admin · migrations 025-030
# =============================================================================


class ParentRelationship(Base):
    """Links a parent user to their student child(ren).

    Allows multi-parent (mother + father + guardian) and multi-child.
    `is_active=False` represents a soft-revocation (e.g. divorce, custody change).

    GH-SCHOOL-ADMIN · migration 025_add_parent_role.
    """

    __tablename__ = "parent_relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_user_id = Column(
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
    relationship_type = Column("relationship", String(40), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Cohort(Base):
    """Logical group of students within a school (e.g. "11A 2026").

    Used to distribute workload across psychologists, isolate KPIs per cohort,
    and compare performance side-by-side. Soft-archive via `archived_at`.

    GH-SCHOOL-ADMIN · migration 026_cohorts_and_assignments.
    """

    __tablename__ = "cohorts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key = Column(String(40), nullable=False)
    label = Column(String(120), nullable=False)
    grade = Column(String(20), nullable=True)
    academic_year = Column(Integer, nullable=True)
    color = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    archived_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<Cohort id={self.id}>"


class StudentCohortAssignment(Base):
    """Many-to-many between students and cohorts.

    A student may belong to multiple cohorts (rare but valid: cross-program).
    Most schools assign one cohort per student.
    """

    __tablename__ = "student_cohort_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cohort_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cohorts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    assigned_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # created_at · migration 041_auditability_and_indices
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)


class CohortPsychologistAssignment(Base):
    """Many-to-many between psychologists and cohorts."""

    __tablename__ = "cohort_psychologist_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    psychologist_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cohort_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cohorts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    assigned_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # created_at · migration 041_auditability_and_indices
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)


class StudentAdminNote(Base):
    """Administrative (non-clinical) note on a student.

    Visible to school_admin of the school. NOT clinical · separate from
    student_dossier_notes (advisor-only) and session_notes (psychologist-only).

    GH-SCHOOL-ADMIN · migration 027_admin_notes_custom_fields.
    """

    __tablename__ = "student_admin_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class SchoolCustomField(Base):
    """Definition of a custom attribute available for students of one school.

    `type` is one of: text · number · boolean · enum.
    For 'enum', `options` is a JSONB list of strings.
    """

    __tablename__ = "school_custom_fields"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key = Column(String(60), nullable=False)
    label = Column(String(120), nullable=False)
    type = Column(String(20), nullable=False)
    options = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)


class StudentCustomFieldValue(Base):
    """Value assigned to a custom field for a specific student."""

    __tablename__ = "student_custom_field_values"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school_custom_fields.id", ondelete="CASCADE"),
        nullable=False,
    )
    value = Column(JSON, nullable=True)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    # created_at · migration 041_auditability_and_indices
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)


class SchoolEvent(Base):
    """Workshop, fair, talk, or any school program event.

    Audience: students | parents | both.
    Vinculate to RSVPs via SchoolEventRSVP.

    GH-SCHOOL-ADMIN · migration 028_school_events.
    """

    __tablename__ = "school_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    starts_at = Column(DateTime, nullable=False, index=True)
    ends_at = Column(DateTime, nullable=True)
    location = Column(String(200), nullable=True)
    audience = Column(String(20), nullable=False, default="both")
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    archived_at = Column(DateTime, nullable=True)


class SchoolEventRSVP(Base):
    """RSVP from a student / parent to a school event."""

    __tablename__ = "school_event_rsvps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(String(20), nullable=False)
    responded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # created_at · migration 041_auditability_and_indices
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)


class SchoolLegalDocument(Base):
    """Privacy / TyC / parental_consent doc owned by a school.

    Versioned (immutable once created) and signable by parents at invitation.

    GH-SCHOOL-ADMIN · migration 029_school_legal_documents.
    """

    __tablename__ = "school_legal_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = Column(String(40), nullable=False)
    version = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    effective_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)


class SchoolLegalSignature(Base):
    """Audit trail of a signature on a legal document."""

    __tablename__ = "school_legal_signatures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school_legal_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    signer_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    signer_name = Column(String(200), nullable=True)
    signer_email = Column(String(200), nullable=True)
    signed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    # created_at · migration 041_auditability_and_indices
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)


class StudentCaseFollowup(Base):
    """A case being tracked by school staff (academic / emotional / familiar).

    Status: open | in_progress | resolved | escalated.
    GH-SCHOOL-ADMIN · migration 030_cases_followup.
    """

    __tablename__ = "student_cases_followup"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opened_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    case_type = Column(String(40), nullable=False)
    status = Column(String(20), nullable=False, default="open")
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    resolved_at = Column(DateTime, nullable=True)


class CaseIntervention(Base):
    """Action taken on a case (note / meeting / referral / parent_contact / closure)."""

    __tablename__ = "case_interventions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("student_cases_followup.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action = Column(String(60), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)


class ClinicalAlert(Base):
    """Materialized clinical signal flagged from AI behavioral analysis.

    Sourced from `behavioral_patterns` with severity in {medium, high}, but
    the alert lives independently so school_admin can ack / triage / link
    to a case without re-running the AI.

    GH-SCHOOL-ADMIN · migration 030.
    """

    __tablename__ = "clinical_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    severity = Column(String(20), nullable=False)
    pattern_type = Column(String(60), nullable=False)
    summary = Column(Text, nullable=True)
    source = Column(String(40), nullable=False, default="ai_analysis")
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("student_cases_followup.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)


class SchoolMassMessage(Base):
    """Mass message (newsletter / announcement) sent to students/parents.

    Tracks open rate via opened_count (incremented from a tracking pixel).
    """

    __tablename__ = "school_mass_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    subject = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    audience = Column(String(20), nullable=False, default="both")
    cohort_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cohorts.id", ondelete="SET NULL"),
        nullable=True,
    )
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_count = Column(Integer, default=0, nullable=False)
    opened_count = Column(Integer, default=0, nullable=False)
    # updated_at · migration 041_auditability_and_indices
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)


class SchoolMassMessageRead(Base):
    """Per-recipient read receipt for a mass message.

    The mass-message row is broadcast-shaped (`opened_count` aggregate is the
    school_admin metric). This table tracks individual recipients (parents,
    eventually students) so the parent inbox can compute unread counts and
    keep messages read-only · NEVER a chat thread.

    GH-PARENT-EXPERIENCE · migration 032_parent_message_reads · 2026-05-05.
    """

    __tablename__ = "school_mass_message_reads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school_mass_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    read_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # created_at · migration 041_auditability_and_indices
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)


# =============================================================================
# Super-admin observability & ops · GH-SUPERADMIN-EXPERIENCE · 2026-05-05
# Migrations 034 (admin_alerts + impersonation_sessions) · 035 (ai_usage_log +
# error_log) · 036 (feature_flags + ai_prompts + integration_configs).
# =============================================================================


class AdminAlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AdminAlert(Base):
    """Proactive alert for super_admin attention · Bloque D (migration 034).

    Generated by `admin_alerts_service.run_checks()` (cron-style worker called
    on /admin/alerts/refresh or background scheduler). One row per
    (type, target) while active; resolving stamps `resolved_at` so a fresh
    alert can fire later.
    """

    __tablename__ = "admin_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(60), nullable=False, index=True)
    severity = Column(String(20), nullable=False, default=AdminAlertSeverity.WARNING.value)
    target_type = Column(String(40), nullable=True)
    target_id = Column(String(120), nullable=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class ImpersonationScope(str, enum.Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class ImpersonationSession(Base):
    """Audit trail for super_admin impersonation · Bloque E (migration 034).

    Token grants the actor (super_admin) a session that authenticates as the
    target user with reduced scope. Hard rules enforced by service:
      - actor MUST be super_admin
      - target MUST NOT be super_admin (no peer-impersonation)
      - cannot start a new session while another is active for same actor
      - banner is forced in the FE while ended_at IS NULL
      - every action during the session is also audit-logged with both ids
    """

    __tablename__ = "impersonation_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token = Column(String(120), nullable=False, unique=True, index=True)
    scope = Column(String(20), nullable=False, default=ImpersonationScope.READ_ONLY.value)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    ip_address = Column(String(60), nullable=True)
    user_agent = Column(String(255), nullable=True)


class AIUsageLog(Base):
    """Per-call AI cost ledger · Bloque J (migration 035)."""

    __tablename__ = "ai_usage_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(20), nullable=False, index=True)
    model = Column(String(80), nullable=False)
    feature = Column(String(60), nullable=False, index=True)
    tokens_input = Column(Integer, nullable=True)
    tokens_output = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class ErrorLog(Base):
    """Captured backend exceptions · Bloque K (migration 035)."""

    __tablename__ = "error_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level = Column(String(10), nullable=False, default="error")
    path = Column(String(255), nullable=True)
    method = Column(String(10), nullable=True)
    status_code = Column(Integer, nullable=True)
    exception_type = Column(String(120), nullable=True, index=True)
    message = Column(Text, nullable=True)
    trace = Column(Text, nullable=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)


# F-001 · CV builder etapa 1 (2026-05-21) · categorías de actividades
# extracurriculares para el perfil del estudiante. Lista abierta (el FE puede
# enviar otros valores) pero estos son los buckets canónicos para UI.
EXTRACURRICULAR_CATEGORIES = (
    "sport",          # deporte
    "volunteering",   # voluntariado / servicio social
    "arts",           # arte / cultura
    "academic",       # academia / clubes / olimpiadas
    "leadership",     # liderazgo / consejo estudiantil
    "work",           # trabajo / práctica
    "other",
)


class ExtracurricularActivity(Base):
    """Actividad extracurricular declarada por el estudiante · F-001 (2026-05-21).

    GH-LOCAL-CLIENT-MODULES · primer módulo de scope cliente Fase 1. El
    estudiante registra sus actividades (deportes, voluntariados, etc.) en
    su perfil. Visible para el psy / advisor en el dossier · NO visible
    para otros estudiantes ni school_admin sin scope.

    Etapa 1 (este sprint): CRUD + UI básica.
    Etapa 2 (sprint siguiente): IA gap analysis vs carrera objetivo.
    Etapa 3: CV PDF builder.
    """

    __tablename__ = "extracurricular_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = Column(String(20), nullable=False, index=True)  # ver EXTRACURRICULAR_CATEGORIES
    name = Column(String(120), nullable=False)
    role = Column(String(120), nullable=True)  # ej. "capitán", "voluntario"
    hours_per_week = Column(Integer, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)  # NULL = en curso
    description = Column(Text, nullable=True)
    # achievements como JSON list of strings (e.g., ["1er lugar regional 2024"])
    achievements = Column(JSON, nullable=True)
    # evidence_urls como JSON list of strings (links a diplomas/certificados)
    evidence_urls = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


# Valid rating values for ai_recommendation_feedback (M-001 · 2026-05-21).
AI_FEEDBACK_RATINGS = ("thumbs_up", "thumbs_down")

# Valid recommendation_type values. New types can be added without migration
# (the column is just a String) but listing them here documents the contract.
AI_FEEDBACK_TYPES = (
    "clinical_analysis",       # Hop's analysis on the dossier (advisor surface)
    "program_recommendation",  # /recommendations/me items
    "journey_synthesis",       # the synthesis reflection at end of journey
    "career_exploration",      # career exploration prompts (Módulo A, future)
    "consolidated_profile",    # AI-derived profile chips
    "other",                   # catch-all (FE can send custom string)
)


class AiRecommendationFeedback(Base):
    """Audit log of human ratings on AI recommendations · M-001 (2026-05-21).

    GH-LOCAL-CLIENT-MODULES · 2026-05-21 · cliente pidió un panel donde su
    equipo (gh_advisor, gh_commercial, super_admin) pueda calificar las
    recomendaciones de Hop con 👍/👎 + comentario. Las calificaciones se
    agregan para ciclos de prompt engineering. Migration 042.
    """

    __tablename__ = "ai_recommendation_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_type = Column(String(60), nullable=False, index=True)
    # Optional reference to the entity being rated (student_user_id, session_id,
    # recommendation_id, etc.). Free-form string so the same table can serve
    # multiple surfaces without coupling.
    recommendation_ref = Column(String(120), nullable=True, index=True)
    # Snapshot of context (e.g., truncated input/output) for later audit.
    # JSON · keep small · never log PII without redaction.
    context = Column(JSON, nullable=True)
    rating = Column(String(20), nullable=False, index=True)  # thumbs_up | thumbs_down
    comment = Column(Text, nullable=True)
    rated_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class FeatureFlag(Base):
    """Runtime feature toggle · Bloque M (migration 036).

    Resolution order in `is_feature_enabled(key, user)`:
      1. flag missing → False
      2. flag.enabled is True → True (global on)
      3. user.role in enabled_for_roles → True
      4. user.school_id in enabled_for_school_ids → True
      5. otherwise False
    """

    __tablename__ = "feature_flags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(80), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, default=False, nullable=False)
    enabled_for_roles = Column(JSON, default=list, nullable=False)
    enabled_for_school_ids = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class AIPrompt(Base):
    """Versioned AI prompts persisted in DB · Bloque N (migration 036).

    Active prompt per key is resolved via (key, is_active=True). Activating
    a new version flips the previous active row to is_active=False inside a
    single transaction. Services read with TTL cache (60s) to keep latency
    low.
    """

    __tablename__ = "ai_prompts"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_ai_prompts_key_version"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(80), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes = Column(Text, nullable=True)


class IntegrationConfig(Base):
    """Per-integration UI-editable settings · Bloque O (migration 036).

    SECURITY:
      - is_secret=True rows have setting_value = env var NAME (e.g.
        "BITRIX_WEBHOOK_URL"). Actual secret values STAY in env. Never copy.
      - is_secret=False rows can carry plain metadata (notify_email,
        sync_interval_minutes, enabled flag).
    """

    __tablename__ = "integration_configs"
    __table_args__ = (
        UniqueConstraint("integration_key", "setting_key", name="uq_integration_configs_key_setting"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    integration_key = Column(String(40), nullable=False, index=True)
    setting_key = Column(String(80), nullable=False)
    setting_value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=False, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # created_at · migration 041_auditability_and_indices
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
