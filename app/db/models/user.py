"""Bounded context: usuarios y autenticación.

Contiene: OnboardingStatus, UserRole, constantes de role-guards, User.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Date, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.models.base import Base


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
    pipeline_status_version = Column(Integer, nullable=False, default=1)

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
