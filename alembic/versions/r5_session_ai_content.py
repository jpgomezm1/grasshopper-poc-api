"""R5 (auditoría Journey 2026-07-08) · sessions.ai_content JSON nullable.

Persiste el contenido IA generado por paso del journey (empathy / synthesis /
routes) para que lo que la usuaria VIO sea lo que se selecciona, journalea y
re-renderiza. Antes, cada GET del paso regeneraba con otra llamada IA y
`_handle_route_selection` comparaba el route_key clickeado contra un set de
rutas RECIÉN generado (keys distintas) → la elección se perdía en silencio.

Columna nullable → migración segura, sin backfill (las sesiones viejas
regeneran una vez y quedan cacheadas).
"""
from alembic import op
import sqlalchemy as sa


revision = "r5_session_ai_content"
down_revision = "faseA_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("ai_content", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "ai_content")
