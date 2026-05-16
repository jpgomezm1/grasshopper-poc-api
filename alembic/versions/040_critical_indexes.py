"""Critical performance indexes on high-frequency filter columns.

Revision ID: 040_critical_indexes
Revises: 037_pipeline_status_version
Create Date: 2026-05-15

F7.1 · Pulido final post-audit.

Cuatro índices sobre columnas filtradas frecuentemente en queries de producción.
Cada índice elimina un seq-scan en la tabla más grande (users) o en tablas
consultadas en cada request autenticado (licenses, ai_prompts).

Decisión sobre CONCURRENTLY:
    Se evaluó usar `postgresql_concurrently=True` para evitar lock en tablas
    grandes en prod. Sin embargo, PostgreSQL requiere que CONCURRENTLY corra
    FUERA de una transacción explícita. Alembic envuelve upgrade() en una
    transacción por defecto, lo que hace incompatible el flag sin workarounds
    (op.execute("COMMIT") manual antes del índice rompe la atomicidad del upgrade).

    Decisión tomada: usar create_index estándar (con lock breve).
    Para tablas de producción grandes, aplicar este upgrade en ventana de
    mantenimiento off-hours. Lock estimado: < 1 segundo en tabla hasta 100K filas.
    Ver MIGRATION_MERGE_PLAN para instrucciones de deploy en prod.

Índices creados:
    ix_users_role            · WHERE role = 'student' / 'school_admin' / etc.
    ix_users_is_active       · WHERE is_active = TRUE (login + listings admin)
    ix_licenses_status       · WHERE status = 'active' (runtime license check)
    ix_ai_prompts_is_active  · WHERE is_active = TRUE (resolución de prompt activo por key)
"""
from alembic import op


revision = "040_critical_indexes"
down_revision = "039_webhook_nonces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # ix_users_role
    # Beneficia: SELECT * FROM users WHERE role = 'student'
    # Usado en: admin listings, dashboards, school_admin student counts,
    #           license seat checks, gh_team student listings.
    # -------------------------------------------------------------------------
    op.create_index(
        "ix_users_role",
        "users",
        ["role"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # ix_users_is_active
    # Beneficia: SELECT * FROM users WHERE is_active = TRUE
    # Usado en: todos los admin listings que filtran usuarios activos,
    #           invitation accept (check de cuenta establecida).
    # -------------------------------------------------------------------------
    op.create_index(
        "ix_users_is_active",
        "users",
        ["is_active"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # ix_licenses_status
    # Beneficia: SELECT * FROM licenses WHERE status = 'active' AND school_id = ?
    # Usado en: assert_can_register_student() en cada invitación de estudiante
    #           y en runtime license checks del login B2B.
    # -------------------------------------------------------------------------
    op.create_index(
        "ix_licenses_status",
        "licenses",
        ["status"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # ix_ai_prompts_is_active
    # Beneficia: SELECT * FROM ai_prompts WHERE key = ? AND is_active = TRUE
    # Usado en: resolución de prompt activo por key en CADA llamada a Claude.
    #           Sin índice → seq scan en la tabla de prompts en cada request IA.
    # -------------------------------------------------------------------------
    op.create_index(
        "ix_ai_prompts_is_active",
        "ai_prompts",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_prompts_is_active", table_name="ai_prompts")
    op.drop_index("ix_licenses_status", table_name="licenses")
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
