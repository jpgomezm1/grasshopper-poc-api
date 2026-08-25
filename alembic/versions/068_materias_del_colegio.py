"""Materias que ofrece el colegio · cimientos para recomendación de electivas.

Revision ID: 068_materias_del_colegio
Revises: 067_cimientos_malla_completa
Create Date: 2026-08-25

Fase 1 de 4 ("Los logros del estudiante") · reunión con la clienta del
2026-08-24. La tabla de logros del estudiante YA EXISTE desde el 2026-05-21
(`extracurricular_activities`, migración 043) y ya está conectada al perfil
consolidado / SOP / hoja de vida (ver `consolidation_service._gather_activities`
y `cv_pdf_service.py`) — no hace falta tabla ni migración nueva para eso.

Lo que SÍ faltaba, y es lo único que aporta esta migración: un lugar para
guardar qué materias ofrece el colegio de un estudiante. Otro agente de esta
misma corrida construye la recomendación de electivas y necesita saber
"contra qué" recomendar — sin este dato tendría que adivinar o preguntarlo en
cada conversación, y es información del COLEGIO (constante para todos sus
estudiantes), no de cada estudiante individual.

    schools.subjects_offered   JSON NULL · lista de strings, p.ej.
        ["Cálculo", "Física", "Programación", "Economía", "Arte"]
        NULL = todavía no se ha cargado (no es lo mismo que lista vacía).

Igual que la migración 067 (mismo patrón "cimientos"): esta migración SOLO
agrega la columna. Quién la llena (formulario de school_admin, import, o se
pregunta al estudiante y se propone al colegio) y quién la lee (el motor de
electivas) es decisión de una fase posterior — deliberadamente fuera del
alcance de este agente, que sólo tiene permiso de tocar `app/db/models.py`,
`alembic/versions/` y los archivos nuevos de logros.

Aditivo, nullable, idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '068_materias_del_colegio'
down_revision = '067_cimientos_malla_completa'
branch_labels = None
depends_on = None

_SCHOOLS = 'schools'
_COLUMN = 'subjects_offered'


def _has_column(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    try:
        return any(c["name"] == name for c in insp.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, _SCHOOLS, _COLUMN):
        op.add_column(_SCHOOLS, sa.Column(_COLUMN, sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, _SCHOOLS, _COLUMN):
        op.drop_column(_SCHOOLS, _COLUMN)
