"""Qué ejercicios de práctica ya respondió cada estudiante.

Revision ID: 080_practica_vista
Revises: 079_vectores_de_familia

## Por qué existe

I-1 · Sprint 4 (2026-10-29) · Verónica: *"Revisé el Pre SAT y las preguntas se
empiezan a repetir desde la 19 o algo así en adelante"*. La práctica no recordaba
nada entre visitas: la cola vivía en la memoria del navegador y al volver se
servía la primera ronda otra vez. Con esta tabla cada sesión trae solo lo que la
persona no ha respondido, y cuando lo ha respondido todo se le dice.

Una fila por (estudiante, ejercicio). `item_id` no es FK porque el banco vive en
código (`app/data/exam_prep.py`), no en la base. Detalle en el modelo
`ExamPracticeSeen`.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "080_practica_vista"
down_revision = "079_vectores_de_familia"
branch_labels = None
depends_on = None

_TABLA = "exam_practice_seen"


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
        sa.Column("exam_id", sa.String(20), nullable=False),
        sa.Column("item_id", sa.String(60), nullable=False),
        # "Respondido", no "servido": se escribe al corregir. Ver el modelo.
        sa.Column("answered_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "item_id", name="uq_exam_practice_seen_user_item"),
    )
    op.create_index(f"ix_{_TABLA}_user_id", _TABLA, ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLA):
        op.drop_table(_TABLA)
