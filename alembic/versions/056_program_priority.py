"""A8 · Prioridad comercial de cada institución del catálogo (2026-08-07).

Revision ID: 056_program_priority
Revises: 055_route_evidence
Create Date: 2026-08-07

Verónica, reunión del 21-07, sobre el catálogo: *"¿tengo cómo ponerle estrellas
para que determine qué sale primero?"*.

`programs.priority` · entero 1-10 que escribe el equipo de la agencia desde el
panel de super_admin y que el recomendador usa para desempatar.

**Nullable y sin default a propósito.** "Sin priorizar" no es "prioridad baja":
poner 0 o 5 en las 2.511 filas existentes sería inventar un juicio comercial que
nadie emitió, y el orden del catálogo lo mostraría como si fuera real. Hoy el
Excel priorizado todavía no ha llegado, así que **todas** las filas quedan en
NULL — y el orden se comporta exactamente como antes hasta que alguien priorice.

Aditiva, nullable e idempotente, como el resto de la serie 05*.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '056_program_priority'
down_revision = '055_route_evidence'
branch_labels = None
depends_on = None

_TABLE = 'programs'
_COLUMNA = 'priority'
_INDICE = 'ix_programs_priority'


def _tiene_columna(bind, tabla: str, columna: str) -> bool:
    try:
        return columna in {c['name'] for c in inspect(bind).get_columns(tabla)}
    except Exception:
        return False


def _tiene_indice(bind, tabla: str, indice: str) -> bool:
    try:
        return indice in {i['name'] for i in inspect(bind).get_indexes(tabla)}
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _tiene_columna(bind, _TABLE, _COLUMNA):
        op.add_column(_TABLE, sa.Column(_COLUMNA, sa.Integer(), nullable=True))
    if not _tiene_indice(bind, _TABLE, _INDICE):
        op.create_index(_INDICE, _TABLE, [_COLUMNA])


def downgrade() -> None:
    bind = op.get_bind()
    if _tiene_indice(bind, _TABLE, _INDICE):
        op.drop_index(_INDICE, table_name=_TABLE)
    if _tiene_columna(bind, _TABLE, _COLUMNA):
        op.drop_column(_TABLE, _COLUMNA)
