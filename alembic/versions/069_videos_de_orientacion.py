"""Videos de orientación vocacional · una tabla, dos superficies.

Revision ID: 069_videos_de_orientacion
Revises: 068_materias_del_colegio
Create Date: 2026-08-27

Reunión con Verónica del 2026-08-24:

    "hay unas partes donde me gustaria irles poniendo como videos que yo tengo"

El mecanismo para ofrecer un video DENTRO del chat del Journey ya existía
desde esa reunión (`app/data/journey_videos.py` + `VideoOfferCard` en el
front, con tests). Lo que nunca se construyó, y es lo único que impedía que
la clienta cargara un solo video, es dónde se guardan: hasta hoy eran una
lista de Python vacía, en código, que sólo se podía llenar con un despliegue.

## Por qué UNA tabla

Había dos formas de anclar el mismo contenido y eran incompatibles:

  · lo construido  → por `momento` del journey (después de qué pregunta)
  · la spec M-002  → por códigos RIASEC, con galería propia
                     (`docs/Cliente/SCOPE_CLIENTE_FASE_NUEVA.md:254`)

Con dos tablas, la clienta subiría el mismo video dos veces y las copias
divergirían. Aquí los dos anclajes son columnas OPCIONALES del mismo video:
`journey_moment` para el chat, `riasec_codes` para el "Para ti" de la
galería, `topic` para la fila donde vive. Decisión de AH, 2026-08-27.

## Lo que esta migración NO hace

No sube ningún video. La tabla nace vacía a propósito — inventar una URL o
una duración sería el tipo de dato inventado por el que ya hubo un reclamo
del cliente. El contenido entra por `scripts/cargar_videos.py`, desde un
archivo que produce la clienta.

Aditiva e idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect


revision = '069_videos_de_orientacion'
down_revision = '068_materias_del_colegio'
branch_labels = None
depends_on = None

_TABLE = 'orientation_videos'


def _has_table(bind, name: str) -> bool:
    try:
        return name in inspect(bind).get_table_names()
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLE):
        return

    op.create_table(
        _TABLE,
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('thumbnail_url', sa.String(500), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('topic', sa.String(60), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('riasec_codes', sa.JSON(), nullable=True),
        sa.Column('journey_moment', sa.String(50), nullable=True),
        sa.Column('journey_route', sa.String(30), nullable=True),
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        # La URL identifica al video: si la clienta vuelve a mandar la misma
        # fila en el archivo de carga, el script actualiza en vez de duplicar.
        sa.UniqueConstraint('url', name='uq_orientation_video_url'),
    )
    op.create_index(f'ix_{_TABLE}_topic', _TABLE, ['topic'])
    op.create_index(f'ix_{_TABLE}_journey_moment', _TABLE, ['journey_moment'])
    op.create_index(f'ix_{_TABLE}_is_published', _TABLE, ['is_published'])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLE):
        op.drop_table(_TABLE)
