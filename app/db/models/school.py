"""Bounded context: colegios (B2B) y todo lo administrativo del school.

Contiene: School, License/LicenseTier/LicenseStatus, Cohort,
StudentCohortAssignment, CohortPsychologistAssignment, Invitation/InvitationStatus,
SchoolCustomField, StudentCustomFieldValue, SchoolEvent, SchoolEventRSVP,
SchoolLegalDocument, SchoolLegalSignature, SchoolMassMessage,
SchoolMassMessageRead, StudentAdminNote, StudentCaseFollowup,
CaseIntervention, ClinicalAlert, ParentRelationship.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.models.base import Base


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


class InvitationStatus(str, enum.Enum):
    """Invitation lifecycle · GH-S9."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


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
    archived_at = Column(DateTime, nullable=True)


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
