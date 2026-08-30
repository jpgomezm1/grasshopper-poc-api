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
    - gh_advisor     · orientador interno Mentoring · ve B2C + B2B con contact_request
    - gh_commercial  · asesora comercial Mentoring · pipeline Bitrix + contact requests
    - super_admin    · staff de Mentoring · CRUD global de colegios, licencias, catálogo

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
    """B2B client (colegio) of Mentoring.

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

    # ---- Materias que ofrece el colegio · cimientos malla completa (migración 068) ----
    # Lista de strings (p.ej. ["Cálculo", "Física", "Programación"]). NULL =
    # todavía no se cargó (no es lo mismo que "colegio sin electivas": eso
    # sería lista vacía). Es un dato del COLEGIO, no del estudiante — constante
    # para todos los alumnos de ese `school_id`, por eso vive aquí y no en
    # `User` ni en `ExtracurricularActivity`.
    #
    # OJO para quien construya la recomendación de electivas (otro agente de
    # esta misma corrida): esta columna hoy NO la escribe ni la lee ningún
    # endpoint — es sólo el cimiento. Falta decidir y conectar: (a) quién la
    # llena (formulario school_admin, import masivo, o inferencia desde lo que
    # el estudiante reporta) y (b) quién la lee (el motor de electivas). No
    # repetir aquí el error típico de este repo (campo que nadie escribe o que
    # nadie lee) — conectar ambos lados en el mismo cambio cuando se aborde esa
    # fase, no antes.
    subjects_offered = Column(JSON, nullable=True)

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

    # ---- Grado real del estudiante · Cimientos malla completa (migración 067) ----
    # `grade`: 9 | 10 | 11 | 12. NULL para quien no está en colegio (perfil
    # `profesional` de `onboarding_hechos.PERFIL_POR_LIFE_STAGE`) o para quien
    # todavía no lo ha dicho.
    #
    # Va en COLUMNA, no sólo en `onboarding_answers`, por tres razones que no
    # aplican a la mayoría de hechos del onboarding (esos sí viven sólo en el
    # JSON, ver `app/data/onboarding_hechos.py`):
    #   1. La malla completa son **5 rutas** (grado 9, 10, 11, 12, adulto
    #      profesional) y `life_stage` no alcanza esa resolución: su valor
    #      `high_school_early` junta 9° y 10°, y `high_school` sólo cubre 11°
    #      (ver `app/services/academic_level.py`, que hoy filtra por etapas de
    #      3-4 valores, no por grado exacto). Sin una columna con dominio
    #      cerrado (9-12), un valor libre como "9°", "Grado 9" o "noveno" no
    #      sirve para enrutar programáticamente a una de las 5 rutas.
    #   2. La tabla de memoria por año (`StudentYearSnapshot`, más abajo)
    #      necesita el grado como dato estructurado para comparar "qué grado
    #      cursaba el año pasado" contra "qué grado cursa hoy" sin parsear texto.
    #   3. Precedente ya sentado en este mismo modelo con `birthdate`: un hecho
    #      del onboarding puede vivir A LA VEZ como columna tipada (fuente de
    #      verdad para lo que filtra/enruta) y como clave en
    #      `onboarding_answers` (contrato que ya leen otros consumidores).
    #
    # OJO para quien conecte el chat de onboarding (otro agente, dueño de
    # `onboarding_hechos.py` y `onboarding_conversacional.py`): YA EXISTEN
    # lectores muertos de `onboarding_answers["grade"]` / `onboarding_answers["grado"]`
    # (`cv_pdf_service.py:148`, `pdf_service.py:317`) y de
    # `answers.get("grade") o answers.get("currentGrade")` (`dossier_service.py:99`,
    # vía `_get_combined_answers` = onboarding_answers + session.answers). Ninguno
    # escribe ese valor todavía — es exactamente el error tipo A de este repo
    # (leer un campo que nadie escribe). Al conectar la pregunta del grado hay
    # que escribir ESTA columna (`user.grade`, entero) Y espejarla en
    # `onboarding_answers["grade"]` (string, p.ej. "11"), igual que
    # `onboarding_chat.py` hace hoy con `birthdate` (líneas ~106-110). No basta
    # con una sola escritura: dejar sólo el JSON revive el campo muerto a medias
    # (se ve en el CV pero no enruta la malla); dejar sólo la columna no lo
    # arregla en el CV/dossier.
    grade = Column(Integer, nullable=True)

    # ---- Lo que el estudiante CREE de su colegio · NO dato verificado ----
    # Se pregunta en el chat de onboarding (con opción "no sé"), no se valida
    # contra ningún registro del colegio. El prefijo `school_reported_` es
    # deliberado para que nadie los confunda con un dato de `School` (la
    # institución) ni los trate como verificados en un reporte o export.
    #
    # `school_reported_last_grade`: hasta qué grado llega el colegio del
    # estudiante · 11 o 12. NULL = no preguntado o no aplica (perfil profesional).
    school_reported_last_grade = Column(Integer, nullable=True)
    # `school_reported_accreditation`: "ib" | "ap" | "american" | "bilingual" |
    # "local" | "unknown". "unknown" es la respuesta explícita "no sé" (persona
    # SÍ preguntada); NULL es "todavía no se le ha preguntado". La regla de
    # producto ("si no se sabe, NO se muestran módulos AP/IB") trata los dos
    # casos igual al momento de decidir qué mostrar — la distinción sólo importa
    # para no volver a preguntar algo ya contestado.
    school_reported_accreditation = Column(String(20), nullable=True)

    # Contact info
    phone = Column(String(50), nullable=True)

    # (La foto de la hoja de vida vive en `user_photos`, no aquí · ver esa clase.)

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
    # M-006 · e-sign nativo de consentimiento parental para menores.
    # Token de un solo uso enviado por email al acudiente + su expiración +
    # el email del acudiente (para mostrarlo enmascarado en el estado).
    # index (no unique): el token es aleatorio de 32 bytes, no necesita constraint
    # UNIQUE y así coincide con la migración (que crea índice no único).
    parental_consent_token = Column(String(255), nullable=True, index=True)
    parental_consent_token_expires = Column(DateTime, nullable=True)
    parental_consent_parent_email = Column(String(255), nullable=True)

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
    # RM-1 · consentimiento para el acompañamiento periódico ("¿cómo vas con tu
    # proyecto?"). Es INDEPENDIENTE del de tratamiento de datos: alguien puede
    # aceptar que tratemos su información y no querer que le escribamos.
    # NULL = no otorgado → no se le manda nada (ver consent_service.can_send_communications).
    consent_communications_at = Column(DateTime, nullable=True)

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
    # Memoria por año escolar (migración 067) · ver `StudentYearSnapshot`.
    year_snapshots = relationship(
        "StudentYearSnapshot",
        back_populates="user",
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
    # R5 (auditoría Journey) · contenido IA persistido por paso
    # ({empathy|synthesis|routes: {hash, data}}). Lo que la usuaria VIO es lo
    # que se guarda/selecciona/journalea — antes cada GET regeneraba con otra
    # llamada IA y la selección de ruta comparaba contra un set distinto.
    ai_content = Column(JSON, nullable=True)

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

    # §1 · De dónde salió la ruta · mismo patrón que JR-7 usó con las fortalezas.
    # La clienta no sabía de dónde venía lo que el sistema le mostraba.
    evidence = Column(JSON, nullable=True)
    # §1 · True = son las sugerencias estáticas de fallback, no una lectura de
    # este perfil. Nullable porque las rutas anteriores no lo tienen y `None`
    # significa "generada antes de que existiera esta marca".
    is_generic = Column(Boolean, nullable=True)

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

    # P1-1 · Lectura narrativa del resultado, generada por IA (migración 050).
    # Feedback A1: "cada test tiene que darle más información al estudiante Y SU
    # FAMILIA". `interpretation_hash` guarda el hash de los scores que la
    # originaron: si el estudiante repite el test, deja de coincidir y se
    # regenera — si no, seguiría leyendo la lectura del resultado anterior.
    interpretation = Column(JSON, nullable=True)
    interpretation_hash = Column(String(64), nullable=True)
    interpretation_generated_at = Column(DateTime, nullable=True)

    # A6 · Lo que el ESTUDIANTE cree que le encaja, después de ver este resultado
    # (migración 051). Feedback en mayúsculas de la clienta: "según el conocimiento
    # que adquieres de ti mismo con el último test realizado, ¿qué carreras piensas
    # que se acomodan? Escribe 3 opciones, siendo 1 la que más se acomoda".
    # Formato: {"careers": ["primera", "segunda", "tercera"]} en orden de preferencia.
    # Va por test —no una sola vez— porque la autopercepción cambia con cada test.
    self_assessment = Column(JSON, nullable=True)
    self_assessment_at = Column(DateTime, nullable=True)

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

    # Migración 048 (2026-06-03): financieros opcionales. NULL = "a confirmar"
    # (el catálogo real del cliente no trae precio/duración/presupuesto).
    # El modelo estaba en drift con la migración; alineado en B-042 y Fase C
    # (2026-06-09).
    duration_months = Column(Integer, nullable=True)
    cost_total = Column(Integer, nullable=True)
    currency = Column(String(10), default="USD", nullable=False)
    budget_tier = Column(String(20), nullable=True, index=True)
    alliance_type = Column(String(30), default="estandar", nullable=False)
    language_requirement = Column(String(50), nullable=True)

    active = Column(Boolean, default=True, nullable=False, index=True)
    raw = Column(JSON, nullable=True)

    # A8 · Prioridad comercial 1-10 · migración 056 (2026-08-07).
    # Verónica, 21-07: "¿tengo cómo ponerle estrellas para que determine qué
    # sale primero?". La escribe el equipo de la agencia desde el panel de
    # super_admin (PATCH /v1/programs/{id}).
    #
    # NULL a propósito y sin default: "sin priorizar" NO es "prioridad baja".
    # Poner 0 o 5 por defecto sería inventar un juicio comercial que nadie
    # emitió, y el orden del catálogo lo reflejaría como si fuera real.
    priority = Column(Integer, nullable=True, index=True)

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

    # D-002 (2026-06-04) · variables de admisión para clasificar Reach/Match/Safety.
    # Cliente docx §3.G. NULL = no curado (no se muestra badge). acceptance_rate
    # en porcentaje 0-100. min_english_level en CEFR (A1..C2).
    acceptance_rate = Column(Float, nullable=True)
    avg_admitted_gpa = Column(Float, nullable=True)
    min_sat = Column(Integer, nullable=True)
    avg_sat = Column(Integer, nullable=True)
    min_english_level = Column(String(10), nullable=True)

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
    # `payload` va ENMASCARADO (`bitrix_client.safe_summary`) · los logs no
    # llevan PII, y eso no cambia.
    payload = Column(JSON, nullable=True)
    # Hash del payload REAL, sin enmascarar · migración 058 (2026-08-07).
    #
    # Existe porque el dedup comparaba los dos lados enmascarados: `NAME: "Ana"`
    # y `NAME: "Ana María"` daban el mismo hash, así que **cambiar el nombre de
    # un estudiante nunca llegaba al CRM del cliente**. El hash permite comparar
    # datos reales sin escribirlos en ningún log.
    #
    # NULL en las filas anteriores a la migración · el dedup lo trata como
    # "no sé" y sincroniza, que es el lado seguro.
    payload_hash = Column(String(32), nullable=True, index=True)
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


class BotConversation(Base):
    """Conversación del perfilador comercial · el bot que reemplaza el Typeform.

    Es pública y anónima: vive sin `User`, igual que `LeadProfile`. La diferencia
    con esa tabla es que aquí SÍ hay quien lea — `lead_profiles` se escribe desde
    `lead_profile.py:70` y ningún otro sitio del backend la consulta, así que los
    leads del quiz llevan meses cayendo en un pozo. La bandeja del bot existe
    para que eso no se repita.

    `hechos` guarda los ~20 datos ya validados contra el catálogo (nunca texto
    crudo del modelo); `transcript` guarda la conversación entera, que es lo que
    el asesor quiere leer antes de llamar.
    """
    __tablename__ = "bot_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    # Contacto · se llena a medida que la persona lo va diciendo, no al final.
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)

    # Estado de la conversación
    hechos = Column(JSON, default=dict, nullable=False)
    transcript = Column(JSON, default=list, nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False)

    # Veredicto comercial · lo escribe `bot_lead_scoring.evaluar`
    score = Column(Integer, nullable=True)
    band = Column(String(20), nullable=True)      # hot · warm · cold
    route = Column(String(20), nullable=True)     # asesor · telemercadeo · descartar
    alarms = Column(JSON, nullable=True)
    score_rationale = Column(JSON, nullable=True)

    # Derivación a Mentoring · la "miga de pan" de la reunión del 21-07
    wants_orientation = Column(Boolean, default=False, nullable=False)

    # Si la persona después se registra, se cuelga aquí para no repreguntarle
    # en el onboarding lo que el bot ya sabe.
    converted_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Trazabilidad de campaña · el Typeform ya traía utm_*
    utm_source = Column(String(120), nullable=True)
    utm_medium = Column(String(120), nullable=True)
    utm_campaign = Column(String(120), nullable=True)

    # Estado del envío al CRM del cliente · hoy Bitrix corre en stub
    crm_synced_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<BotConversation id={self.id} route={self.route}>"


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


class OutreachLog(Base):
    """RM-1 · Una fila por mensaje de acompañamiento · migración 057.

    Existe por tres razones distintas, y ninguna es opcional:

    1. **No repetirle a la misma persona.** `outreach_service` lo consulta antes
       de armar la lista. Sin esta tabla, cada corrida del scheduler volvería a
       escribirle a todo el mundo.
    2. **Auditoría.** Parte de los usuarios son menores de edad. Tiene que poder
       responderse "¿qué se le mandó a esta persona y con qué permiso?" sin
       adivinar. Por eso se guarda también lo que NO se envió y el motivo
       (`resultado`), no sólo lo entregado.
    3. Para que el equipo de la agencia vea el historial de una cuenta.

    `resultado` distingue enviado · sin_consentimiento · fallo_envio ·
    simulacro. `simulacro` es lo que escribe el preview: se ve qué habría
    salido sin que salga nada.
    """

    __tablename__ = "outreach_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Clave estable del motivo (`outreach_service.Motivo.clave`).
    motivo = Column(String(50), nullable=False, index=True)
    canal = Column(String(20), nullable=False)  # email · in_app
    resultado = Column(String(30), nullable=False, index=True)

    # Qué se le dijo · guardado para poder mostrarlo tal cual en el panel.
    asunto = Column(String(255), nullable=True)
    cuerpo = Column(Text, nullable=True)
    # True cuando el texto vino de la plantilla determinista y no del modelo.
    es_plantilla = Column(Boolean, nullable=True)
    # Motivo del no-envío cuando `resultado` no es "enviado".
    detalle = Column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<OutreachLog user={self.user_id} motivo={self.motivo} → {self.resultado}>"


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

    NOTA (2026-08-25 · reunión clienta 2026-08-24, "capitán del equipo de
    fútbol / spelling bee en noveno"): ESTA es la tabla de "logros del
    estudiante" que pidió la clienta. `category` ya cubre liderazgo
    ("leadership") · deportivo ("sport") · académico ("academic") ·
    artístico ("arts") · voluntariado ("volunteering") · otro ("other"),
    más "work" que no pidió pero no estorba. Ya está conectada al perfil
    consolidado / SOP (`consolidation_service._gather_activities`) y a la
    hoja de vida (`cv_pdf_service.py`, `cv_docx_service.py`). No crear una
    tabla nueva de "logros" — es esta.
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


class CVProfile(Base):
    """A3 · lo que el estudiante responde y edita de su Hoja de Vida.

    Feedback literal de la clienta:

        "Hoja de vida: antes de generarla debe preguntar QUÉ HAGO ACTUALMENTE y
         EN QUÉ COLEGIO ESTUDIO (si estoy en colegio). (...) Además DEBE PODER
         EDITARSE (habrá cosas que uno quiera quitar o mejorar)."

    Antes, `GET /me/cv` armaba el PDF de una: no preguntaba nada y no se podía
    tocar nada. Migración `052_cv_profile`.

    `overrides` guarda las ediciones del estudiante sobre lo que arma
    `build_cv_data`: titular, resumen, fortalezas, intereses, valores, caminos, y
    las listas de lo que decidió quitar (`excluded_activity_ids`,
    `excluded_test_ids`). Va en JSON porque son los mismos campos que ya produce
    el generador; volverlos columnas obligaría a migrar cada vez que el CV gane
    una sección.
    """

    __tablename__ = "cv_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # --- Las dos preguntas que ella pidió ---------------------------------
    current_occupation = Column(String(80), nullable=True)
    occupation_detail = Column(String(200), nullable=True)
    studies_at_school = Column(Boolean, nullable=True)
    school_name = Column(String(200), nullable=True)

    # --- Lo que el estudiante editó o quitó -------------------------------
    overrides = Column(JSON, nullable=True)

    # --- Destino y apariencia · migración 063 -----------------------------
    # `estandar` decide el CONTENIDO (foto, páginas, orden de secciones) y
    # `estilo` sólo el CSS. La separación vive en `services/cv_variants.py`.
    # Nullable a propósito: sin elegir nada, el renderizador cae en latam +
    # clásico, que es exactamente el CV que ya existía.
    estandar = Column(String(20), nullable=True)
    estilo = Column(String(20), nullable=True)
    incluir_foto = Column(Boolean, nullable=True)

    # --- Enlace público · nace apagado ------------------------------------
    # Son menores de edad: un enlace con nombre, colegio y foto no se enciende
    # sin visto bueno de la clienta. Las columnas existen para no migrar el día
    # que se autorice, no porque esté activo.
    share_token = Column(String(64), nullable=True, unique=True, index=True)
    share_habilitado = Column(Boolean, nullable=True)
    share_creado_en = Column(DateTime, nullable=True)

    answered_at = Column(DateTime, nullable=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True
    )


class Lugar(Base):
    """Dónde queda una ciudad · caché de geocodificación · migración 066.

    **No es data de negocio.** Se puede vaciar de un DELETE y regenerar con
    `scripts/geocodificar_lugares.py`: lo único que se pierde es el tiempo de
    volver a preguntarle al geocodificador.

    La `clave` la produce `services/lugares.clave_lugar()` con formato
    `<iso>:<ciudad>` (por ejemplo `gb:london`), y es lo que hace que
    `'Londres'/'Reino Unido'` del catálogo investigado y `'London'/'UK'` del
    autorizado sean **el mismo punto en el mapa**.

    `precision` es la parte honesta de esta tabla:

    * `ciudad`       · el geocodificador devolvió una ciudad concreta.
    * `region`       · devolvió algo más grande (`'Ontario'` es una provincia,
                       no una ciudad). El punto sirve para orientar, no para
                       decir "la universidad queda aquí".
    * `sin_resolver` · no se encontró, o el campo trae varios lugares a la vez
                       (`'Madrid, Valencia, Canarias'`). **Se queda sin
                       coordenadas**: inventar un punto es peor que no tenerlo.
    """

    __tablename__ = "lugares"

    clave = Column(String(160), primary_key=True)

    #: Tal como lo escribió la agencia · para mostrar, no para cruzar.
    ciudad = Column(String(160), nullable=True)
    pais_iso = Column(String(8), nullable=False, index=True)

    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

    precision = Column(String(20), nullable=True)
    #: Quién lo resolvió (`nominatim`, `manual`…) · para poder rehacer sólo lo
    #: que vino de una fuente concreta si algún día se cambia de proveedor.
    fuente = Column(String(40), nullable=True)
    verificado_en = Column(DateTime, nullable=True)


class UserPhoto(Base):
    """La foto de la hoja de vida, guardada en Neon · migración 065.

    ## Por qué en la base y no en un bucket

    El proyecto tiene `storage_service`, pero corre contra un stub en memoria
    hasta que alguien configure Supabase — y mientras tanto la foto se pierde en
    cada reinicio del dyno. Guardarla aquí la vuelve real hoy, sin depender de
    credenciales que todavía no existen, y de paso entra en el mismo backup y en
    la misma transacción que el resto del CV.

    A esta escala la decisión es cómoda: son estudiantes, la foto va topada a
    2 MB y hay decenas de usuarios, no millones. Si algún día son muchos, mover
    esto a un bucket es cambiar este servicio y no el resto del código.

    ## Por qué una tabla aparte y no una columna en `users`

    **Ésta es la parte importante.** SQLAlchemy trae todas las columnas por
    defecto, y `users` se consulta en cada request autenticado. Una columna
    `bytea` de 2 MB ahí dentro se descargaría en cada login y en cada llamada a
    la API, para algo que sólo hace falta al generar el PDF.

    Aquí, `db.query(User)` no la toca nunca: hay que pedirla a propósito.
    """

    __tablename__ = "user_photos"

    # El user_id ES la clave primaria · una foto por persona, y sustituirla es
    # un UPDATE en vez de tener que limpiar filas viejas.
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    content_type = Column(String(60), nullable=False)
    data = Column(LargeBinary, nullable=False)
    size_bytes = Column(Integer, nullable=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True
    )


class CVTarget(Base):
    """Una convocatoria a la que el estudiante quiere adaptar su CV · migración 064.

    Vacante, programa, beca o práctica: pega el texto y la IA le dice **qué le
    falta** y le propone una versión adaptada.

    Tres cosas que explican la forma de esta tabla:

    * Son varias. Comparar lo que pide cada convocatoria contra el mismo CV base
      es justo el valor; un campo suelto en `cv_profiles` sólo dejaría la última.
    * `status` existe porque el análisis no cabe en un request: Heroku corta a
      los 30 s y aquí hay dos llamadas al modelo. Se encola y se consulta.
    * **`proposal` no es el CV.** Es una propuesta con forma de `overrides` que
      el estudiante aplica si quiere. Mismo principio que
      `linkedin_import_service`: es su hoja de vida y lleva su nombre, así que
      nada se escribe sin que lo confirme.
    """

    __tablename__ = "cv_targets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # job · program · scholarship · internship · other · lo deduce la IA del
    # propio texto, así que no lleva CHECK en la base.
    kind = Column(String(30), nullable=True)
    title = Column(String(300), nullable=True)
    organization = Column(String(200), nullable=True)
    raw_text = Column(Text, nullable=True)

    parsed = Column(JSON, nullable=True)      # qué pide la convocatoria
    analysis = Column(JSON, nullable=True)    # {ajuste, faltantes[], sugerencias[]}
    proposal = Column(JSON, nullable=True)    # el CV adaptado, como overrides

    # pending → analyzing → ready | failed
    status = Column(String(20), nullable=True, default="pending")
    error = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True
    )


class ProgramaInvestigado(Base):
    """Programa extraído del sitio oficial de la institución · migración 059.

    15.483 filas de 306 instituciones. **No es `Program`**: esto lo investigamos
    nosotros y la agencia todavía no lo confirma. Cuando llegue el Excel a nivel
    de programa de la clienta, lo confirmado pasa a `programs` y esta tabla se
    vacía de un DELETE. Mezclarlo perdería para siempre la distinción entre lo
    que ella validó y lo que dedujimos.

    **No tiene precio a propósito.** El precio cambia por intake y nacionalidad y
    la agencia tiene tarifas negociadas: uno sacado de la web es una promesa que
    el asesor no puede sostener. Que la columna no exista es la garantía.
    """

    __tablename__ = "programas_investigados"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institucion = Column(String(255), nullable=False, index=True)
    nombre = Column(String(500), nullable=False)

    pais = Column(String(80), nullable=True, index=True)
    ciudad = Column(String(160), nullable=True)

    nivel = Column(String(40), nullable=False, index=True)
    # Vocabulario cerrado de `app/services/areas.py`. El texto original se
    # conserva al lado para poder rehacer el mapeo sin volver a extraer.
    area = Column(String(80), nullable=True, index=True)
    area_cruda = Column(String(160), nullable=True)

    duracion = Column(String(120), nullable=True)
    codigo_oficial = Column(String(80), nullable=True)
    url_fuente = Column(Text, nullable=True)
    dominio = Column(String(160), nullable=True)

    lote = Column(String(8), nullable=True)
    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # La ficha del catalogo autorizado a la que pertenece · migracion 061.
    #
    # Nullable a proposito: hay instituciones cuyos programas extrajimos y que
    # no tienen ficha (redes que se descompusieron en sus miembros). Esos
    # programas siguen siendo validos y visibles; solo no cuelgan de una oferta.
    program_id = Column(
        UUID(as_uuid=True), ForeignKey("programs.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # `embedding` (vector(1536)) existe en la tabla pero NO se declara aquí: el
    # tipo `vector` necesitaría el paquete pgvector como dependencia del modelo,
    # y la búsqueda semántica lo consulta por SQL directo de todos modos. Ver
    # `app/services/busqueda_programas.py`.


class PerfilVector(Base):
    """Vector del perfil de un estudiante · migración 060.

    El perfil crece cada vez que la persona usa la app (tests, journey, journal),
    pero entre visita y visita no cambia. `firma` es la huella de las señales que
    produjeron este vector: mientras coincida con la del perfil actual, el vector
    sirve y no hay que pedirle nada al proveedor de embeddings.

    Clave primaria = usuario. No tiene sentido que existan dos vectores del mismo
    perfil, y hacerlo explícito ahorra la lógica de "cuál de los dos es el bueno".
    """

    __tablename__ = "perfil_vectores"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    firma = Column(String(64), nullable=False)
    actualizado = Column(DateTime, default=datetime.utcnow, nullable=False)
    # `embedding` (vector(1536)) vive en la tabla pero no se declara aquí · el
    # tipo necesitaría pgvector como dependencia del modelo. Se lee y escribe
    # por SQL directo desde `busqueda_programas`.


class StudentYearSnapshot(Base):
    """Memoria por año escolar · migración 067 (Cimientos, fase 1 de 4).

    "MEMORIA SÍ, LLAVE NO" (decisión de producto ya tomada): el sistema
    recuerda y compara año a año, pero no bloquea ni desbloquea contenido por
    fecha. Esta tabla es sólo el registro — no hay ningún lector todavía que
    lea calendario escolar ni feature-gate por él.

    Una fila = "lo que este estudiante dijo/tenía en este año escolar". Se
    llena UNA vez por (estudiante, año) — ver `uq_student_year_snapshot` — con
    una copia de `onboarding_answers` en ese momento y el grado que cursaba.
    "Comparar el año pasado con hoy" es entonces:

        anterior = (
            db.query(StudentYearSnapshot)
            .filter_by(user_id=user.id)
            .order_by(StudentYearSnapshot.school_year.desc())
            .first()
        )
        hoy = user.onboarding_answers  # ya vive en User, no hace falta copiarlo

    No se guarda una fila para "hoy": el dato de hoy YA está en `users` (
    `onboarding_answers`, `grade`) y duplicarlo aquí sería la segunda fuente de
    verdad que este repo ya pagó una vez (ver comentario de
    `onboarding_hechos.PERFIL_POR_LIFE_STAGE`). Esta tabla sólo existe para
    conservar lo que ya no está vigente: cuando el estudiante pasa de año y
    sus respuestas cambian, ALGUIEN (fuera del alcance de esta fase — la
    escribe el agente que construya el flujo de "nuevo año escolar") debe
    copiar el estado saliente aquí ANTES de sobrescribirlo en `users`.

    Quién escribe esta tabla y cuándo (ej. al detectar que `life_stage`/`grade`
    cambiaron entre sesiones, o por un cron de inicio de año) es una decisión
    de producto que no toma esta fase — aquí sólo se deja el cimiento: dónde
    cabe la memoria y cómo se consulta.
    """

    __tablename__ = "student_year_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Año calendario en que se tomó la foto (ej. 2026). Mismo tipo (Integer)
    # que `Cohort.academic_year`, para que un futuro cruce cohort↔snapshot no
    # tenga que convertir tipos.
    school_year = Column(Integer, nullable=False)

    # El grado que cursaba EN ESE momento · mismo dominio que `User.grade`
    # (9-12, NULL si el perfil era profesional). Es una copia deliberada: si
    # `User.grade` cambia después, esta fila no debe cambiar con él.
    grade = Column(Integer, nullable=True)

    # Copia de `User.onboarding_answers` en el momento del snapshot · mismo
    # shape que la columna viva, así cualquier consumidor que ya sepa leer
    # `onboarding_answers` (recomendador, dossier, CV) sabe leer esto sin
    # aprender un formato nuevo.
    onboarding_answers_snapshot = Column(JSON, nullable=True)

    # Cuándo se tomó la foto (puede no coincidir con `created_at` si algún día
    # se hace un backfill retroactivo).
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="year_snapshots")

    __table_args__ = (
        # Un estudiante, un año, una foto · quien escriba esta tabla más
        # adelante puede hacer upsert sin duplicar filas por reintentos.
        UniqueConstraint("user_id", "school_year", name="uq_student_year_snapshot"),
    )

    def __repr__(self) -> str:
        return f"<StudentYearSnapshot user_id={self.user_id} school_year={self.school_year}>"


class StudentAcademicProfile(Base):
    """La ficha académica · GPA, SAT, AP e IB. Migración 072.

    Verónica (Paso 3 · College List): *"para construir esto es importante
    preguntarle al estudiante su GPA (promedio acumulado) y su sistema de
    colegio … ¿tienes AP? ¿cuántas? ¿qué puntajes? ¿tienes SAT?"*.

    ## Qué NO está aquí, y dónde está

    La **acreditación del colegio** (IB / AP / americano / bilingüe / local) ya
    se captura estructurada en el onboarding y vive en
    `users.onboarding_answers`. No se copia: sería la segunda fuente de verdad
    que este repo ya pagó cuatro veces.

    ## `gpa` sin `gpa_scale` no significa nada

    Un 4.2 sobre 5.0 (Colombia) y un 3.8 sobre 4.0 (EE. UU.) son el mismo
    número en dos idiomas: traducido, el 4.2 es 3.36 y está POR DEBAJO del 3.8.

    `Program.avg_admitted_gpa` ya arrastra ese defecto —es un `Float` sin
    escala— y hoy es inofensivo sólo porque el GPA del estudiante siempre llega
    `None`. Por eso aquí la escala se guarda SIEMPRE junto al número, y por eso
    `academic_profile_service` expone además el porcentaje normalizado: quien
    compare, que compare peras con peras.

    ## Por qué la editas tú y no se deduce

    AH eligió (2026-08-30) que esto viva en "Mi perfil" como una ficha que el
    estudiante llena y ACTUALIZA: las notas suben, el SAT se repite, el IB
    previsto cambia. Un dato que se congela en el onboarding envejece mal
    justo en el año en que más importa.
    """

    __tablename__ = "student_academic_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # El promedio y su escala · van juntos o no van. Ver arriba.
    gpa = Column(Float, nullable=True)
    gpa_scale = Column(Float, nullable=True)

    # SAT · 400-1600 en todo el mundo. Es la única métrica académica que se
    # puede comparar tal cual, sin traducir.
    sat_score = Column(Integer, nullable=True)
    sat_taken_on = Column(Date, nullable=True)

    # [{"materia": "Calculus AB", "puntaje": 5}, ...] · son N materias, y no
    # hay un número fijo: columnas obligarían a migrar por cada examen nuevo.
    ap_scores = Column(JSON, nullable=True)

    # El total previsto del Diploma (0-45) · es lo que mira la universidad
    # mientras el estudiante todavía lo está cursando.
    ib_predicted_total = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<StudentAcademicProfile user_id={self.user_id}>"


class CounselorSyncReport(Base):
    """El reporte que el ESTUDIANTE le manda a su colegio · migración 071.

    Verónica, revisión Sprint 2 (Paso 5): *"al finalizar cada etapa, el sistema
    genera un reporte ejecutivo de progreso que el estudiante envía a su
    consejera antes de su reunión presencial"*.

    ## Quién es el dueño de esto

    El ESTUDIANTE. Es la diferencia con `StudentDossierNote`, que la escribe el
    profesional y que el estudiante no puede ver nunca. Aquí es al revés: él lo
    genera, él decide mandarlo, y él ve lo que mandó.

    Por eso tampoco va con las alertas clínicas: "mi estudiante me mandó su
    avance" no es una señal de riesgo.

    ## `content` es una FOTO, no una vista

    La consejera prepara la reunión con lo que recibió. Si esto se recalculara
    al abrirlo, un estudiante que hace tres tests entre el envío y la cita
    cambiaría en silencio el documento sobre el que ella ya trabajó.

    Mismo criterio que `StudentYearSnapshot`: un recuerdo que se actualiza solo
    no es un recuerdo.

    ## Le llega al colegio, no a una persona

    El modelo no asigna psicóloga a estudiante — el staff del colegio ve a los
    de su escuela (`SCHOOL_STAFF_ROLES`). Guardar un destinatario individual
    inventaría un vínculo que no existe.
    """

    __tablename__ = "counselor_sync_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # `SET NULL` y nullable: si el colegio se borra, el estudiante conserva lo
    # que mandó. Y un B2C sin colegio no puede enviar (lo impide el endpoint),
    # pero sus envíos viejos no deben re-apuntar si mañana se une a uno.
    school_id = Column(
        UUID(as_uuid=True), ForeignKey("schools.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # La foto del reporte en el momento del envío · ver arriba.
    content = Column(JSON, nullable=False)

    # Lo que el estudiante quiera añadir de su puño.
    student_note = Column(Text, nullable=True)

    # Cuándo lo abrió alguien del colegio. Sirve para que el estudiante sepa
    # que llegó — NO para medir a la consejera, que ya está saturada y no
    # necesita otro cronómetro encima.
    read_at = Column(DateTime, nullable=True)

    student = relationship("User", foreign_keys=[student_user_id])

    def __repr__(self) -> str:
        return f"<CounselorSyncReport student={self.student_user_id} sent_at={self.sent_at}>"


class OrientationVideo(Base):
    """Un video de orientación vocacional · reunión con Verónica del 2026-08-24.

        "hay unas partes donde me gustaria irles poniendo como videos que yo tengo"

    ## Por qué UNA tabla y no dos

    Este contenido lo pedían dos sitios distintos y cada uno lo anclaba a su
    manera: el chat del Journey por `momento` (después de qué pregunta se
    ofrece, ver `app/data/journey_videos.py`) y la spec M-002 del cliente por
    códigos RIASEC, con galería propia. Un video no puede tener dos
    identidades: con dos tablas, la clienta subiría el mismo video dos veces y
    las dos copias divergirían — que es el defecto que este repo ya documenta.

    Así que los anclajes son COLUMNAS OPCIONALES del mismo video:

        journey_moment  → aparece en el chat después de ese hecho
        riasec_codes    → sube en "Para ti" de quien tenga esos códigos
        topic           → la fila de la galería donde vive

    Un video puede tener los tres, uno, o ninguno (y entonces sólo sale en la
    galería general). Decisión de AH, 2026-08-27.

    ## No alojamos el archivo

    `url` es un enlace a YouTube o Vimeo. El almacenamiento propio
    (`storage_service`) está en modo stub en producción y, aunque no lo
    estuviera, transcodificar y servir video no es algo que queramos
    construir. La clienta produce y sube a su plataforma; aquí va el enlace.
    """

    __tablename__ = "orientation_videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # --- el contenido ------------------------------------------------------
    url = Column(String(500), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    # Miniatura propia. Si es NULL el front la deriva del id de YouTube · por
    # eso es nullable y no obligatoria: pedirle a la clienta una imagen por
    # video sería una barrera para que suba contenido.
    thumbnail_url = Column(String(500), nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # --- dónde vive en la galería -----------------------------------------
    # Texto libre a propósito: la taxonomía la pone quien carga el contenido,
    # no nosotros. Inventar una lista cerrada de áreas sería adivinar de qué
    # va a grabar la clienta.
    topic = Column(String(60), nullable=False, index=True)
    # Orden dentro de su fila · empates se resuelven por created_at.
    sort_order = Column(Integer, nullable=False, default=0)

    # --- anclajes opcionales ----------------------------------------------
    # Lista de letras RIASEC, p.ej. ["R", "I"]. NULL = no está etiquetado y
    # no puede subir a "Para ti" — que es correcto: sin etiqueta no sabemos
    # a quién le sirve, y ordenarlo igual sería inventar relevancia.
    riasec_codes = Column(JSON, nullable=True)
    # Id de un Hecho de `app.data.journey_chat_hechos` · NULL = no se ofrece
    # dentro de la conversación.
    journey_moment = Column(String(50), nullable=True, index=True)
    # Una de las 5 rutas de la malla · NULL = aplica a todas.
    journey_route = Column(String(30), nullable=True)

    # --- la ruta de aprendizaje --------------------------------------------
    # Etapa del camino, p.ej. "Descubrirte" · "Conocer carreras" · "Decidir".
    #
    # NO es lo mismo que `topic`, y por eso son dos columnas. `topic` son
    # AREAS (Salud, Ingeniería, Arte) y son paralelas: nadie recorre "primero
    # Salud, luego Ingeniería". `stage` es la secuencia pedagógica, que sí
    # tiene un antes y un después. Meterlas en el mismo campo obligaría a
    # elegir entre agrupar por área o por etapa, y las dos vistas son útiles.
    #
    # NULL = todavía sin clasificar · cae al final del camino.
    stage = Column(String(60), nullable=True, index=True)

    # --- gestión -----------------------------------------------------------
    # Permite cargar un video y dejarlo invisible hasta que la clienta lo
    # apruebe, sin borrar la fila.
    is_published = Column(Boolean, nullable=False, default=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("url", name="uq_orientation_video_url"),
    )

    def __repr__(self) -> str:
        return f"<OrientationVideo {self.title!r} topic={self.topic!r}>"


class OrientationVideoView(Base):
    """Qué videos ha abierto cada estudiante · AH, 2026-08-29.

    Hace falta para que la galería sea una RUTA y no una lista: sin esto no
    hay palomitas, ni "sigue aquí", ni porcentaje de avance.

    ## Marca "abierto", no "visto entero"

    Se escribe cuando el reproductor lleva unos segundos abierto. No sabemos si
    la persona vio el video completo —eso exigiría la API de YouTube y
    escuchar sus eventos— y el nombre del campo lo dice: `opened_at`. La UI lo
    llama "visto" porque es lo que la persona entiende, pero el dato que
    tenemos es más flojo que la palabra, y conviene que quien lea esta tabla
    dentro de seis meses lo sepa.

    ## Y no bloquea nada

    "MEMORIA SÍ, LLAVE NO" (decisión de producto, ver migración 067): esta
    tabla se lee para MOSTRAR por dónde va la persona y sugerir el siguiente
    paso. Ningún video se cierra por no haber visto el anterior. En orientación
    vocacional bloquear tiene un costo concreto: alguien con curiosidad por
    enfermería no debería tener que ver tres videos antes de llegar.
    """

    __tablename__ = "orientation_video_views"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    video_id = Column(
        UUID(as_uuid=True),
        ForeignKey("orientation_videos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # Una fila por (estudiante, video) · volver a abrirlo no crea otra.
        UniqueConstraint("user_id", "video_id", name="uq_video_view_user_video"),
    )

    def __repr__(self) -> str:
        return f"<OrientationVideoView user={self.user_id} video={self.video_id}>"
