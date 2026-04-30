"""Create reports table for PDF generation tracking + email status

Revision ID: 008_create_reports
Revises: 007_create_consolidated_profiles
Create Date: 2026-04-30

GH-S7-DB · Sprint 7 (PDF report co-branded + email transactional).

What this migration does:

  Creates `reports` to track every PDF report generated for a student:
    - storage path of the PDF (Supabase / stub via storage_service)
    - profile_hash at generation time (so we know if it's stale vs current
      consolidated_profile cache)
    - email send status (provider · sent flag · reason · timestamp)

  One row per generation event. We do NOT enforce uniqueness per user
  because re-generations are valid (new test → new report). The latest
  row is the canonical one for "Descargar reporte PDF".

  PII guard: this table contains FK to user but no plaintext PII. The
  PDF binary lives in storage with `{user_id}/reports/<uuid>.pdf` path.

Idempotent: uses table_exists / column_exists guards.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "008_create_reports"
down_revision = "007_create_consolidated_profiles"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if not table_exists("reports"):
        op.create_table(
            "reports",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            # Storage path inside the configured bucket
            # Convention: "{user_id}/reports/<uuid>.pdf"
            sa.Column("file_path", sa.String(500), nullable=False),
            sa.Column("size_bytes", sa.Integer, nullable=True),
            # Profile snapshot · hash at the time the PDF was rendered.
            # When User has a fresher consolidated_profiles row with a
            # different hash, the FE knows to offer "regenerate".
            sa.Column("profile_hash", sa.String(64), nullable=True, index=True),
            sa.Column("school_id_at_render", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("locale", sa.String(10), nullable=False, server_default="es-CO"),
            # Generation metadata
            sa.Column("generator_version", sa.String(50), nullable=True),
            sa.Column("page_count", sa.Integer, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.func.now(),
            ),
            # Email status
            sa.Column(
                "email_sent",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("email_sent_at", sa.DateTime, nullable=True),
            sa.Column("email_to", sa.String(255), nullable=True),
            sa.Column("email_provider", sa.String(30), nullable=True),
            sa.Column("email_message_id", sa.String(255), nullable=True),
            sa.Column("email_reason", sa.String(120), nullable=True),
        )
        op.create_index(
            "ix_reports_user_created",
            "reports",
            ["user_id", "created_at"],
        )


def downgrade() -> None:
    if table_exists("reports"):
        op.drop_index("ix_reports_user_created", table_name="reports")
        op.drop_table("reports")
