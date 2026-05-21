"""AI recommendation feedback table · M-001 panel auditoría IA.

Revision ID: 042_ai_recommendation_feedback
Revises: 041_auditability_and_indices
Create Date: 2026-05-21

GH-LOCAL-CLIENT-MODULES · 2026-05-21 · cliente pidió un panel donde su equipo
(gh_advisor, gh_commercial, super_admin) pueda calificar cada recomendación
de Hop con 👍/👎 + comentario libre. Las calificaciones se agregan para
ciclos de prompt engineering. Visible en `/admin/ai-audit` (FE).

Table:
    ai_recommendation_feedback
        id                    UUID PRIMARY KEY
        recommendation_type   VARCHAR(60)   NOT NULL  · clinical_analysis | program_recommendation | journey_synthesis | career_exploration | consolidated_profile | other
        recommendation_ref    VARCHAR(120)  NULL      · optional FK-ish (student_id / session_id / etc)
        context               JSON          NULL      · snapshot input+output (keep small, no PII)
        rating                VARCHAR(20)   NOT NULL  · thumbs_up | thumbs_down
        comment               TEXT          NULL
        rated_by_user_id      UUID          NULL FK → users.id ON DELETE SET NULL
        created_at            TIMESTAMP     NOT NULL DEFAULT NOW
        updated_at            TIMESTAMP     NOT NULL DEFAULT NOW

Indexes:
    - (created_at)            · time-window queries (last 30d, etc.)
    - (recommendation_type)   · filter by type
    - (rated_by_user_id)      · "my ratings" view
    - (recommendation_ref)    · joining with referenced entity

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '042_ai_recommendation_feedback'
down_revision = '041_auditability_and_indices'
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

    if not _has_table(bind, "ai_recommendation_feedback"):
        op.create_table(
            "ai_recommendation_feedback",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("recommendation_type", sa.String(60), nullable=False),
            sa.Column("recommendation_ref", sa.String(120), nullable=True),
            sa.Column("context", JSON_T, nullable=True),
            sa.Column("rating", sa.String(20), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column(
                "rated_by_user_id",
                UUID,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
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

    # Indexes (idempotent)
    if not _has_index(bind, "ai_recommendation_feedback", "ix_ai_feedback_created_at"):
        op.create_index(
            "ix_ai_feedback_created_at",
            "ai_recommendation_feedback",
            ["created_at"],
        )
    if not _has_index(bind, "ai_recommendation_feedback", "ix_ai_feedback_type"):
        op.create_index(
            "ix_ai_feedback_type",
            "ai_recommendation_feedback",
            ["recommendation_type"],
        )
    if not _has_index(bind, "ai_recommendation_feedback", "ix_ai_feedback_rated_by"):
        op.create_index(
            "ix_ai_feedback_rated_by",
            "ai_recommendation_feedback",
            ["rated_by_user_id"],
        )
    if not _has_index(bind, "ai_recommendation_feedback", "ix_ai_feedback_ref"):
        op.create_index(
            "ix_ai_feedback_ref",
            "ai_recommendation_feedback",
            ["recommendation_ref"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "ai_recommendation_feedback"):
        for ix in (
            "ix_ai_feedback_created_at",
            "ix_ai_feedback_type",
            "ix_ai_feedback_rated_by",
            "ix_ai_feedback_ref",
        ):
            try:
                op.drop_index(ix, "ai_recommendation_feedback")
            except Exception:
                pass
        op.drop_table("ai_recommendation_feedback")
