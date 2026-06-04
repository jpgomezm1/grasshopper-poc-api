"""F-005 · aceptación de aviso legal pre-test por tipo de test (2026-06-04).

Revision ID: 049_user_test_disclaimers
Revises: 048_programs_nullable_financials
Create Date: 2026-06-04

Agrega `users.test_disclaimers` (JSON) que guarda, por tipo de test, cuándo y
qué versión del aviso legal aceptó el estudiante:
    { test_id: {"accepted_at": ISO8601, "version": str} }

nullable=True: las filas previas quedan en NULL y el código las lee con `or {}`.
Idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '049_user_test_disclaimers'
down_revision = '048_programs_nullable_financials'
branch_labels = None
depends_on = None


def _has_column(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    try:
        return any(c["name"] == name for c in insp.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "users", "test_disclaimers"):
        op.add_column(
            "users",
            sa.Column("test_disclaimers", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "users", "test_disclaimers"):
        op.drop_column("users", "test_disclaimers")
