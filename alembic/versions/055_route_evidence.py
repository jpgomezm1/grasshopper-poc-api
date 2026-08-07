"""§1 · De dónde salió cada ruta, y cuáles son genéricas (2026-08-07).

Revision ID: 055_route_evidence
Revises: 054_bot_conversations
Create Date: 2026-08-07

Dos columnas sobre `routes`:

- `evidence` · las trazas de dónde salió la ruta. Mismo movimiento que JR-7 hizo
  con las fortalezas, y responde a la misma queja de la clienta: no saber de
  dónde viene lo que el sistema le muestra.
- `is_generic` · marca las rutas de fallback. Hasta ahora, cuando la IA fallaba
  el estudiante recibía tres rutas estáticas presentadas **idénticas** a las
  personalizadas, sin forma de distinguirlas. Es el mismo criterio con el que
  este sprint quitó los percentiles inventados y el "encaja en tu presupuesto".

Ambas **aditivas y nullable**: las rutas ya generadas se quedan con `NULL`, que
significa "de antes de que esto existiera" — y no "no tiene evidencia" ni "no es
genérica". Distinguirlo importa para no afirmarle nada al estudiante sobre una
ruta vieja.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '055_route_evidence'
down_revision = '054_bot_conversations'
branch_labels = None
depends_on = None

_TABLE = 'routes'


def _tiene_columna(bind, tabla: str, columna: str) -> bool:
    try:
        return columna in {c['name'] for c in inspect(bind).get_columns(tabla)}
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _tiene_columna(bind, _TABLE, 'evidence'):
        op.add_column(_TABLE, sa.Column('evidence', sa.JSON(), nullable=True))
    if not _tiene_columna(bind, _TABLE, 'is_generic'):
        op.add_column(_TABLE, sa.Column('is_generic', sa.Boolean(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _tiene_columna(bind, _TABLE, 'is_generic'):
        op.drop_column(_TABLE, 'is_generic')
    if _tiene_columna(bind, _TABLE, 'evidence'):
        op.drop_column(_TABLE, 'evidence')
