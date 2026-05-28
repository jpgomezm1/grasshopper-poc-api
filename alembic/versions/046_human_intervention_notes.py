"""Human intervention private notes · F-006 (2026-05-28).

Revision ID: 046_human_intervention_notes
Revises: 045_institutions_catalog
Create Date: 2026-05-28

GH-LOCAL-CLIENT-MODULES · cliente docx §3: "Campos de Intervención Humana:
un campo en el perfil del estudiante que solo yo pueda ver para anotar qué
tan cerca está de cerrar el contrato de Counselling Premium."

Tabla 1-1 con users (PK = user_id). Solo el advisor asignado al lead
(``users.assigned_to_user_id``) y super_admin pueden leer/escribir. NUNCA
visible al student, psy ni otros advisors. Cuando el lead se re-asigna
a otro advisor, las notas siguen ahí pero solo el nuevo advisor puede verlas.

Table:
    human_intervention_notes
        user_id            UUID PRIMARY KEY FK → users.id ON DELETE CASCADE
        notes              TEXT NULL
        closeness_level    VARCHAR(20) NULL · cold | warm | hot | closing | closed_won | closed_lost
        updated_by_user_id UUID NULL FK → users.id ON DELETE SET NULL
        created_at         TIMESTAMP NOT NULL
        updated_at         TIMESTAMP NOT NULL

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '046_human_intervention_notes'
down_revision = '045_institutions_catalog'
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    insp = inspect(bind)
    return name in insp.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    UUID = sa.dialects.postgresql.UUID(as_uuid=True) if is_pg else sa.String(36)

    if not _has_table(bind, "human_intervention_notes"):
        op.create_table(
            "human_intervention_notes",
            sa.Column(
                "user_id",
                UUID,
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("closeness_level", sa.String(20), nullable=True),
            sa.Column(
                "updated_by_user_id",
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


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "human_intervention_notes"):
        op.drop_table("human_intervention_notes")
