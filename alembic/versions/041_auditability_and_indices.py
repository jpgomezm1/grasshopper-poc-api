"""Auditability metadata + performance indices (medium/low risk backlog).

Revision ID: 041_auditability_and_indices
Revises: 040_critical_indexes
Create Date: 2026-05-15

Backlog cerrado de antipatterns detectados en el refactor F5.3 (QA_AUDIT.md).
Esta migración es de auditability pura: no cambia ningún comportamiento de
negocio existente. Todas las columnas nuevas son nullable con server_default
para que las filas existentes en producción reciban un timestamp válido
(el momento de aplicar la migración) en lugar de NULL.

Decisión sobre CONCURRENTLY (heredada de 040):
    Se usa create_index estándar (lock breve). Las tablas afectadas son pequeñas
    o medianas (row count estimado < 10k en prod al momento de este deploy).
    Para tablas grandes en el futuro, ver MIGRATION_MERGE_PLAN.

Grupos de cambios:
    A. Índices medio-riesgo (5):
        tasks.status                       → ix_tasks_status
        student_cases_followup.status      → ix_student_cases_followup_status
        orientation_sessions.type          → ix_orientation_sessions_type
        bitrix_sync_log.provider           → ix_bitrix_sync_log_provider
        invitations.role                   → ix_invitations_role

    B. Columnas updated_at faltantes (18 modelos):
        tasks · cohorts · school_events · lead_tags · lead_profiles
        notifications · reports · saved_ofertas · school_legal_documents
        vocational_test_results · external_test_uploads · case_interventions
        clinical_alerts · saved_searches · school_mass_messages
        push_subscriptions · school_custom_fields · english_test_results

    C. Columnas created_at faltantes en modelos join (8):
        cohort_psychologist_assignments · student_cohort_assignments
        lead_tag_assignments · school_event_rsvps
        school_mass_message_reads · student_custom_field_values
        school_legal_signatures · integration_configs
"""
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "041_auditability_and_indices"
down_revision = "040_critical_indexes"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # =========================================================================
    # A. Índices medio-riesgo
    # =========================================================================

    # A1. tasks.status — filtro frecuente en dashboards de tareas abiertas
    op.create_index(
        "ix_tasks_status",
        "tasks",
        ["status"],
        unique=False,
    )

    # A2. student_cases_followup.status — filtro por casos abiertos/escalados
    op.create_index(
        "ix_student_cases_followup_status",
        "student_cases_followup",
        ["status"],
        unique=False,
    )

    # A3. orientation_sessions.type — filtro por tipo de sesión en agenda advisor
    op.create_index(
        "ix_orientation_sessions_type",
        "orientation_sessions",
        ["type"],
        unique=False,
    )

    # A4. bitrix_sync_log.provider — filtrar stub vs real para auditoría de replay
    op.create_index(
        "ix_bitrix_sync_log_provider",
        "bitrix_sync_log",
        ["provider"],
        unique=False,
    )

    # A5. invitations.role — filtrar invitaciones por tipo de rol
    op.create_index(
        "ix_invitations_role",
        "invitations",
        ["role"],
        unique=False,
    )

    # =========================================================================
    # B. Columnas updated_at faltantes (18 modelos)
    # server_default=sa.func.now() → filas existentes en prod reciben el
    # timestamp del momento de la migración (no NULL) · backward-safe.
    # =========================================================================

    _add_updated_at = lambda table: op.add_column(
        table,
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.func.now(),
        ),
    )

    _add_updated_at("tasks")
    _add_updated_at("cohorts")
    _add_updated_at("school_events")
    _add_updated_at("lead_tags")
    _add_updated_at("lead_profiles")
    _add_updated_at("notifications")
    _add_updated_at("reports")
    _add_updated_at("saved_ofertas")
    _add_updated_at("school_legal_documents")
    _add_updated_at("vocational_test_results")
    _add_updated_at("external_test_uploads")
    _add_updated_at("case_interventions")
    _add_updated_at("clinical_alerts")
    _add_updated_at("saved_searches")
    _add_updated_at("school_mass_messages")
    _add_updated_at("push_subscriptions")
    _add_updated_at("school_custom_fields")
    _add_updated_at("english_test_results")

    # =========================================================================
    # C. Columnas created_at faltantes en modelos join (8)
    # server_default=sa.func.now() misma razón que updated_at arriba.
    # =========================================================================

    _add_created_at = lambda table: op.add_column(
        table,
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.func.now(),
        ),
    )

    _add_created_at("cohort_psychologist_assignments")
    _add_created_at("student_cohort_assignments")
    _add_created_at("lead_tag_assignments")
    _add_created_at("school_event_rsvps")
    _add_created_at("school_mass_message_reads")
    _add_created_at("student_custom_field_values")
    _add_created_at("school_legal_signatures")
    _add_created_at("integration_configs")


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # =========================================================================
    # A. Eliminar índices (inverso del upgrade)
    # =========================================================================
    op.drop_index("ix_invitations_role", table_name="invitations")
    op.drop_index("ix_bitrix_sync_log_provider", table_name="bitrix_sync_log")
    op.drop_index("ix_orientation_sessions_type", table_name="orientation_sessions")
    op.drop_index("ix_student_cases_followup_status", table_name="student_cases_followup")
    op.drop_index("ix_tasks_status", table_name="tasks")

    # =========================================================================
    # B. Eliminar columnas updated_at (inverso del upgrade)
    # =========================================================================
    for table in (
        "tasks",
        "cohorts",
        "school_events",
        "lead_tags",
        "lead_profiles",
        "notifications",
        "reports",
        "saved_ofertas",
        "school_legal_documents",
        "vocational_test_results",
        "external_test_uploads",
        "case_interventions",
        "clinical_alerts",
        "saved_searches",
        "school_mass_messages",
        "push_subscriptions",
        "school_custom_fields",
        "english_test_results",
    ):
        op.drop_column(table, "updated_at")

    # =========================================================================
    # C. Eliminar columnas created_at en join models (inverso del upgrade)
    # =========================================================================
    for table in (
        "cohort_psychologist_assignments",
        "student_cohort_assignments",
        "lead_tag_assignments",
        "school_event_rsvps",
        "school_mass_message_reads",
        "student_custom_field_values",
        "school_legal_signatures",
        "integration_configs",
    ):
        op.drop_column(table, "created_at")
