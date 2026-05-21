"""Extracurricular activities table · F-001 CV builder etapa 1.

Revision ID: 043_extracurricular_activities
Revises: 042_ai_recommendation_feedback
Create Date: 2026-05-21

GH-LOCAL-CLIENT-MODULES · primer módulo del scope cliente Fase 1. El
estudiante registra sus actividades extracurriculares (deportes,
voluntariados, etc.) en su perfil. Visible en el dossier del psy/advisor.

Etapa 1: CRUD básico + UI · Etapa 2: IA gap analysis · Etapa 3: PDF CV.

Table:
    extracurricular_activities
        id              UUID PRIMARY KEY
        user_id         UUID NOT NULL FK → users.id ON DELETE CASCADE
        category        VARCHAR(20) NOT NULL   · sport | volunteering | arts | academic | leadership | work | other
        name            VARCHAR(120) NOT NULL
        role            VARCHAR(120) NULL
        hours_per_week  INTEGER NULL
        start_date      DATE NULL
        end_date        DATE NULL  · NULL = en curso
        description     TEXT NULL
        achievements    JSON NULL  · list of strings
        evidence_urls   JSON NULL  · list of URLs
        created_at      TIMESTAMP NOT NULL DEFAULT NOW
        updated_at      TIMESTAMP NOT NULL DEFAULT NOW

Indexes:
    - (user_id)      · queries "mis actividades"
    - (category)     · filtros / agregados
    - (created_at)   · ordenamientos

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '043_extracurricular_activities'
down_revision = '042_ai_recommendation_feedback'
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    insp = inspect(bind)
    return name in insp.get_table_names()


def _has_index(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    try:
        indexes = insp.get_indexes(table)
    except Exception:
        return False
    return any(ix["name"] == name for ix in indexes)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    UUID = sa.dialects.postgresql.UUID(as_uuid=True) if is_pg else sa.String(36)
    JSON_T = sa.dialects.postgresql.JSONB if is_pg else sa.JSON

    if not _has_table(bind, "extracurricular_activities"):
        op.create_table(
            "extracurricular_activities",
            sa.Column("id", UUID, primary_key=True),
            sa.Column(
                "user_id",
                UUID,
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("category", sa.String(20), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("role", sa.String(120), nullable=True),
            sa.Column("hours_per_week", sa.Integer(), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("achievements", JSON_T, nullable=True),
            sa.Column("evidence_urls", JSON_T, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _has_index(bind, "extracurricular_activities", "ix_extracurricular_user_id"):
        op.create_index(
            "ix_extracurricular_user_id",
            "extracurricular_activities",
            ["user_id"],
        )
    if not _has_index(bind, "extracurricular_activities", "ix_extracurricular_category"):
        op.create_index(
            "ix_extracurricular_category",
            "extracurricular_activities",
            ["category"],
        )
    if not _has_index(bind, "extracurricular_activities", "ix_extracurricular_created_at"):
        op.create_index(
            "ix_extracurricular_created_at",
            "extracurricular_activities",
            ["created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "extracurricular_activities"):
        for ix in (
            "ix_extracurricular_user_id",
            "ix_extracurricular_category",
            "ix_extracurricular_created_at",
        ):
            try:
                op.drop_index(ix, "extracurricular_activities")
            except Exception:
                pass
        op.drop_table("extracurricular_activities")
