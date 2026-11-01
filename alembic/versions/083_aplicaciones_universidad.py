"""Las aplicaciones a universidades de cada estudiante (el kit de 12°).

Revision ID: 083_aplicaciones_universidad
Revises: 082_estado_de_prospectos

E-4 · Sprint 4 (2026-10-31). Tabla nueva `aplicaciones_universidad` (ver el
modelo `AplicacionUniversidad`). Solo crea; no toca nada que ya exista.
Idempotente: si la tabla ya está, no hace nada.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "083_aplicaciones_universidad"
down_revision = "082_estado_de_prospectos"
branch_labels = None
depends_on = None

_TABLA = "aplicaciones_universidad"


def _has_table(bind, name: str) -> bool:
    try:
        return name in inspect(bind).get_table_names()
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLA):
        return
    op.create_table(
        _TABLA,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("universidad", sa.String(200), nullable=False),
        sa.Column("programa", sa.String(200), nullable=True),
        sa.Column("pais", sa.String(20), nullable=False),
        sa.Column("fecha_limite", sa.Date(), nullable=True),
        sa.Column("listos", sa.JSON(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
    )
    op.create_index(f"ix_{_TABLA}_user_id", _TABLA, ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLA):
        op.drop_index(f"ix_{_TABLA}_user_id", table_name=_TABLA)
        op.drop_table(_TABLA)
