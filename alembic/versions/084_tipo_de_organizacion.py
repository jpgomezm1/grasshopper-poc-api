"""Qué clase de organización es cada `school`: colegio, programa o empresa.

Revision ID: 084_tipo_de_organizacion
Revises: 083_aplicaciones_universidad

F-2 / F-4 · Sprint 4 (2026-11-01). Una columna nullable en `schools`. NULL =
colegio, que es lo que eran todas las filas: no se escribe nada en las que ya
existen. Aditiva e idempotente, como pide el repo.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "084_tipo_de_organizacion"
down_revision = "083_aplicaciones_universidad"
branch_labels = None
depends_on = None


def _columnas(bind) -> set:
    try:
        return {c["name"] for c in inspect(bind).get_columns("schools")}
    except Exception:
        return set()


def upgrade() -> None:
    if "tipo" not in _columnas(op.get_bind()):
        op.add_column("schools", sa.Column("tipo", sa.String(20), nullable=True))


def downgrade() -> None:
    if "tipo" in _columnas(op.get_bind()):
        op.drop_column("schools", "tipo")
