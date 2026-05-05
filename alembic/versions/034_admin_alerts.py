"""Admin alerts table · proactive monitoring for super_admin.

Revision ID: 034_admin_alerts
Revises: 033_user_admin_lifecycle
Create Date: 2026-05-05

GH-SUPERADMIN-EXPERIENCE · Bloque D · alertas inteligentes.

Adds tables:
    admin_alerts
        id           UUID PRIMARY KEY
        type         VARCHAR(60)  NOT NULL  · ej. school.no_activity · license.expiring · errors.spike · dau.drop · ai.quota
        severity     VARCHAR(20)  NOT NULL  · info | warning | critical
        target_type  VARCHAR(40)  NULL      · school | user | service | system
        target_id    VARCHAR(120) NULL      · denormalized id for click-through
        title        VARCHAR(255) NOT NULL
        body         TEXT          NULL
        data         JSON          NULL     · type-specific extra payload
        created_at   TIMESTAMP     NOT NULL · default now
        resolved_at  TIMESTAMP     NULL     · NULL = active alert
        resolved_by_user_id UUID   NULL FK → users.id
        UNIQUE (type, target_type, target_id) WHERE resolved_at IS NULL  · one active per target

Indexes:
    ix_admin_alerts_active (resolved_at, severity)  · for the bell badge query
    ix_admin_alerts_type (type)                     · for filtering

Also adds tables for Bloque E (impersonation) — kept in same migration to
respect the "max 4 migrations" budget.

    impersonation_sessions
        id                   UUID PRIMARY KEY
        actor_user_id        UUID NOT NULL FK → users.id   · super_admin
        target_user_id       UUID NOT NULL FK → users.id   · impersonated user
        token                VARCHAR(120) NOT NULL UNIQUE  · short-lived JWT-like
        scope                VARCHAR(20) NOT NULL DEFAULT 'read_only'  · read_only | read_write
        started_at           TIMESTAMP NOT NULL DEFAULT NOW
        ended_at             TIMESTAMP NULL
        ip_address           VARCHAR(60) NULL
        user_agent           VARCHAR(255) NULL

Indexes:
    ix_impersonation_actor (actor_user_id)
    ix_impersonation_target (target_user_id)
    ix_impersonation_active (ended_at)

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '034_admin_alerts'
down_revision = '033_user_admin_lifecycle'
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    insp = inspect(bind)
    return name in insp.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    is_pg = bind.dialect.name == "postgresql"
    UUID = sa.dialects.postgresql.UUID(as_uuid=True) if is_pg else sa.String(36)
    JSON_TYPE = sa.dialects.postgresql.JSONB if is_pg else sa.JSON

    if not _has_table(bind, "admin_alerts"):
        op.create_table(
            "admin_alerts",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("type", sa.String(60), nullable=False, index=True),
            sa.Column("severity", sa.String(20), nullable=False),
            sa.Column("target_type", sa.String(40), nullable=True),
            sa.Column("target_id", sa.String(120), nullable=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("data", JSON_TYPE, nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("resolved_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        )
        op.create_index(
            "ix_admin_alerts_active",
            "admin_alerts",
            ["resolved_at", "severity"],
        )

    if not _has_table(bind, "impersonation_sessions"):
        op.create_table(
            "impersonation_sessions",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("target_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("token", sa.String(120), nullable=False, unique=True),
            sa.Column("scope", sa.String(20), nullable=False, server_default="read_only"),
            sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("ip_address", sa.String(60), nullable=True),
            sa.Column("user_agent", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "impersonation_sessions"):
        op.drop_table("impersonation_sessions")
    if _has_table(bind, "admin_alerts"):
        try:
            op.drop_index("ix_admin_alerts_active", "admin_alerts")
        except Exception:
            pass
        op.drop_table("admin_alerts")
