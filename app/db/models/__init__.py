"""Paquete de modelos SQLAlchemy de Grasshopper.

Importa y re-exporta TODO lo público de los submódulos para que cualquier
`from app.db.models import <Foo>` siga funcionando sin cambios.

Bounded contexts:
  base        · Base declarativa (re-export de app.db.database.Base)
  user        · User, UserRole, OnboardingStatus, role-guard constants
  school      · School, License, Cohort, Invitation y entidades administrativas B2B
  journey     · Session, Route, Journal, Snapshot, Program y entidades del journey
  tests       · EnglishTestResult, VocationalTestResult, ExternalTestUpload,
                ConsolidatedProfileCache, Report
  clinical    · StudentDossierNote, OrientationSession, SessionNote + constantes advisor
  commercial  · BitrixSyncLog, LeadProfile, Notification, Task, PipelineStage, etc.
  audit       · AuditLog, ConsentAuditLog, AdminAlert, ImpersonationSession,
                AIUsageLog, ErrorLog, FeatureFlag, AIPrompt, IntegrationConfig
"""

# ------------------------------------------------------------------
# base
# ------------------------------------------------------------------
from app.db.models.base import Base

# ------------------------------------------------------------------
# user
# ------------------------------------------------------------------
from app.db.models.user import (
    OnboardingStatus,
    UserRole,
    GH_TEAM_ROLES,
    SCHOOL_STAFF_ROLES,
    GH_CONTACT_REQUEST_STATUSES,
    User,
)

# ------------------------------------------------------------------
# school
# ------------------------------------------------------------------
from app.db.models.school import (
    LicenseTier,
    LicenseStatus,
    InvitationStatus,
    School,
    License,
    Invitation,
    Cohort,
    StudentCohortAssignment,
    CohortPsychologistAssignment,
    ParentRelationship,
    StudentAdminNote,
    SchoolCustomField,
    StudentCustomFieldValue,
    SchoolEvent,
    SchoolEventRSVP,
    SchoolLegalDocument,
    SchoolLegalSignature,
    StudentCaseFollowup,
    CaseIntervention,
    ClinicalAlert,
    SchoolMassMessage,
    SchoolMassMessageRead,
)

# ------------------------------------------------------------------
# journey
# ------------------------------------------------------------------
from app.db.models.journey import (
    JourneyStage,
    RouteStatus,
    JournalEntryType,
    Session,
    SessionEvent,
    ProfileVersion,
    JournalEntry,
    Route,
    Snapshot,
    AdvisorLead,
    SavedOferta,
    Program,
)

# ------------------------------------------------------------------
# tests
# ------------------------------------------------------------------
from app.db.models.tests import (
    EnglishTestResult,
    VocationalTestResult,
    ExternalTestUpload,
    ConsolidatedProfileCache,
    Report,
)

# ------------------------------------------------------------------
# clinical
# ------------------------------------------------------------------
from app.db.models.clinical import (
    DOSSIER_SECTIONS,
    ORIENTATION_SESSION_TYPES,
    ORIENTATION_SESSION_STATUSES,
    SESSION_NOTE_PRIVACIES,
    StudentDossierNote,
    OrientationSession,
    SessionNote,
)

# ------------------------------------------------------------------
# commercial
# ------------------------------------------------------------------
from app.db.models.commercial import (
    BitrixSyncStatus,
    TaskPriority,
    TaskStatus,
    BitrixSyncLog,
    LeadProfile,
    Notification,
    PushSubscription,
    Task,
    LeadTag,
    LeadTagAssignment,
    SavedSearch,
    LeadComment,
    PipelineStage,
    AutoAssignRule,
    PipelineRule,
)

# ------------------------------------------------------------------
# audit
# ------------------------------------------------------------------
from app.db.models.audit import (
    AdminAlertSeverity,
    ImpersonationScope,
    AuditLog,
    ConsentAuditLog,
    AdminAlert,
    ImpersonationSession,
    AIUsageLog,
    ErrorLog,
    FeatureFlag,
    AIPrompt,
    IntegrationConfig,
)

# ------------------------------------------------------------------
# __all__: inventario explícito de todo lo público
# ------------------------------------------------------------------
__all__ = [
    # base
    "Base",
    # user
    "OnboardingStatus",
    "UserRole",
    "GH_TEAM_ROLES",
    "SCHOOL_STAFF_ROLES",
    "GH_CONTACT_REQUEST_STATUSES",
    "User",
    # school
    "LicenseTier",
    "LicenseStatus",
    "InvitationStatus",
    "School",
    "License",
    "Invitation",
    "Cohort",
    "StudentCohortAssignment",
    "CohortPsychologistAssignment",
    "ParentRelationship",
    "StudentAdminNote",
    "SchoolCustomField",
    "StudentCustomFieldValue",
    "SchoolEvent",
    "SchoolEventRSVP",
    "SchoolLegalDocument",
    "SchoolLegalSignature",
    "StudentCaseFollowup",
    "CaseIntervention",
    "ClinicalAlert",
    "SchoolMassMessage",
    "SchoolMassMessageRead",
    # journey
    "JourneyStage",
    "RouteStatus",
    "JournalEntryType",
    "Session",
    "SessionEvent",
    "ProfileVersion",
    "JournalEntry",
    "Route",
    "Snapshot",
    "AdvisorLead",
    "SavedOferta",
    "Program",
    # tests
    "EnglishTestResult",
    "VocationalTestResult",
    "ExternalTestUpload",
    "ConsolidatedProfileCache",
    "Report",
    # clinical
    "DOSSIER_SECTIONS",
    "ORIENTATION_SESSION_TYPES",
    "ORIENTATION_SESSION_STATUSES",
    "SESSION_NOTE_PRIVACIES",
    "StudentDossierNote",
    "OrientationSession",
    "SessionNote",
    # commercial
    "BitrixSyncStatus",
    "TaskPriority",
    "TaskStatus",
    "BitrixSyncLog",
    "LeadProfile",
    "Notification",
    "PushSubscription",
    "Task",
    "LeadTag",
    "LeadTagAssignment",
    "SavedSearch",
    "LeadComment",
    "PipelineStage",
    "AutoAssignRule",
    "PipelineRule",
    # audit
    "AdminAlertSeverity",
    "ImpersonationScope",
    "AuditLog",
    "ConsentAuditLog",
    "AdminAlert",
    "ImpersonationSession",
    "AIUsageLog",
    "ErrorLog",
    "FeatureFlag",
    "AIPrompt",
    "IntegrationConfig",
]
