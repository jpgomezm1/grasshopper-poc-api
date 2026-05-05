"""AI usage log + error log · observability for super_admin.

Revision ID: 035_ai_usage_and_error_log
Revises: 034_admin_alerts
Create Date: 2026-05-05

GH-SUPERADMIN-EXPERIENCE · Bloque J (AI costs) + Bloque K (errors).

Tables:
    ai_usage_log
        id              UUID PRIMARY KEY
        provider        VARCHAR(20)  NOT NULL  · anthropic | openai | whisper
        model           VARCHAR(80)  NOT NULL  · claude-3-5-sonnet-... | gpt-4o-mini | whisper-1
        feature         VARCHAR(60)  NOT NULL  · clinical_analysis | hop_chat | route_gen | ...
        tokens_input    INTEGER      NULL
        tokens_output   INTEGER      NULL
        cost_usd        NUMERIC(10,6) NULL
        latency_ms      INTEGER      NULL
        user_id         UUID         NULL FK → users.id
        created_at      TIMESTAMP    NOT NULL DEFAULT NOW

    error_log
        id              UUID PRIMARY KEY
        level           VARCHAR(10)  NOT NULL  · error | warning | critical
        path            VARCHAR(255) NULL      · request path (sanitized)
        method          VARCHAR(10)  NULL
        status_code     INTEGER      NULL
        exception_type  VARCHAR(120) NULL      · ej. SQLAlchemyError
        message         TEXT         NULL      · short summary, NO PII
        trace           TEXT         NULL      · stacktrace (truncated)
        user_id         UUID         NULL FK → users.id
        created_at      TIMESTAMP    NOT NULL DEFAULT NOW
        resolved_at     TIMESTAMP    NULL

Indexes for both tables on (created_at) for time-window queries.

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '035_ai_usage_and_error_log'
down_revision = '034_admin_alerts'
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    insp = inspect(bind)
    return name in insp.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    UUID = sa.dialects.postgresql.UUID(as_uuid=True) if is_pg else sa.String(36)

    if not _has_table(bind, "ai_usage_log"):
        op.create_table(
            "ai_usage_log",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("provider", sa.String(20), nullable=False, index=True),
            sa.Column("model", sa.String(80), nullable=False),
            sa.Column("feature", sa.String(60), nullable=False, index=True),
            sa.Column("tokens_input", sa.Integer(), nullable=True),
            sa.Column("tokens_output", sa.Integer(), nullable=True),
            sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_ai_usage_created_at", "ai_usage_log", ["created_at"])

    if not _has_table(bind, "error_log"):
        op.create_table(
            "error_log",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("level", sa.String(10), nullable=False, server_default="error"),
            sa.Column("path", sa.String(255), nullable=True),
            sa.Column("method", sa.String(10), nullable=True),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("exception_type", sa.String(120), nullable=True, index=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("trace", sa.Text(), nullable=True),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_error_log_created_at", "error_log", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "error_log"):
        try:
            op.drop_index("ix_error_log_created_at", "error_log")
        except Exception:
            pass
        op.drop_table("error_log")
    if _has_table(bind, "ai_usage_log"):
        try:
            op.drop_index("ix_ai_usage_created_at", "ai_usage_log")
        except Exception:
            pass
        op.drop_table("ai_usage_log")
