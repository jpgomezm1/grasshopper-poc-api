"""P1-1 · caché de la interpretación narrativa por test (2026-07-29).

Revision ID: 050_test_interpretation_cache
Revises: r5_session_ai_content
Create Date: 2026-07-29

Feedback A1 de la clienta: "cuando entro al resultado de los tests, le da muy poca
información sobre su resultado al estudiante... la idea es que cada test pueda darle
más información sobre él al estudiante Y SU FAMILIA".

Guarda la lectura generada por IA de un resultado concreto:
    interpretation              JSON  · el contenido estructurado
    interpretation_hash         str   · hash de los scores que la originaron
    interpretation_generated_at date  · para poder auditar y expirar

`interpretation_hash` es lo que permite detectar que el estudiante repitió el test:
si los scores cambian, el hash deja de coincidir y se regenera. Sin él, alguien
podría repetir un test y seguir leyendo la interpretación del resultado anterior.

Todas nullable: las filas previas quedan en NULL y se generan bajo demanda.
Idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '050_test_interpretation_cache'
down_revision = 'r5_session_ai_content'
branch_labels = None
depends_on = None

_TABLE = 'vocational_test_results'


def _has_column(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    try:
        return any(c["name"] == name for c in insp.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, _TABLE, 'interpretation'):
        op.add_column(_TABLE, sa.Column('interpretation', sa.JSON(), nullable=True))
    if not _has_column(bind, _TABLE, 'interpretation_hash'):
        op.add_column(_TABLE, sa.Column('interpretation_hash', sa.String(64), nullable=True))
    if not _has_column(bind, _TABLE, 'interpretation_generated_at'):
        op.add_column(
            _TABLE, sa.Column('interpretation_generated_at', sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    for col in ('interpretation_generated_at', 'interpretation_hash', 'interpretation'):
        if _has_column(bind, _TABLE, col):
            op.drop_column(_TABLE, col)
