"""A6 · autoanálisis del estudiante después de cada test (2026-07-29).

Revision ID: 051_test_self_assessment
Revises: 050_test_interpretation_cache
Create Date: 2026-07-29

Feedback A6, el único que la clienta escribió EN MAYÚSCULAS ("ESTO NO ESTÁ
FUNCIONANDO"):

    "Una vez realizo un test de orientación, no me pregunta: según el conocimiento
    que adquieres de ti mismo con el último test realizado, ¿qué carreras
    profesionales piensas que se acomodan a tus valores, habilidades e intereses?
    Escribe 3 opciones, siendo 1 la que más se acomoda."

Se guarda POR TEST, no una sola vez: ella dice "con el ÚLTIMO test realizado", así
que la respuesta cambia a medida que la persona se conoce más. Guardarlo por test
permite además mostrarle cómo evolucionó su propia percepción.

    self_assessment              JSON · {"careers": ["...", "...", "..."]} en orden
    self_assessment_at           date · cuándo lo respondió

Nullable: es opcional y se puede omitir. Idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '051_test_self_assessment'
down_revision = '050_test_interpretation_cache'
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
    if not _has_column(bind, _TABLE, 'self_assessment'):
        op.add_column(_TABLE, sa.Column('self_assessment', sa.JSON(), nullable=True))
    if not _has_column(bind, _TABLE, 'self_assessment_at'):
        op.add_column(_TABLE, sa.Column('self_assessment_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for col in ('self_assessment_at', 'self_assessment'):
        if _has_column(bind, _TABLE, col):
            op.drop_column(_TABLE, col)
