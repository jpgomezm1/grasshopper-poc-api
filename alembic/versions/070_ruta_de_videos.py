"""La galería de videos pasa a ser una ruta · etapas + qué ha abierto cada uno.

Revision ID: 070_ruta_de_videos
Revises: 069_videos_de_orientacion
Create Date: 2026-08-29

AH: *"quiero que esto se vea como una ruta de aprendizaje, o sea como una
visual de roadmap e ir desbloqueando los videos"*.

Dos cosas, y las dos hacían falta:

**`orientation_videos.stage`** · la etapa del camino ("Descubrirte",
"Conocer carreras", "Decidir"). NO se reusa `topic` porque son ejes
distintos: `topic` son ÁREAS (Salud, Ingeniería, Arte) y son paralelas —
nadie recorre "primero Salud, luego Ingeniería"—, mientras que la etapa sí
tiene un antes y un después. Con un solo campo habría que elegir entre
agrupar por área o por etapa, y las dos vistas sirven.

**`orientation_video_views`** · qué ha abierto cada estudiante. Sin esto no
hay palomitas, ni "sigue aquí", ni porcentaje: la galería sería una lista con
otra forma, no una ruta.

## Lo que NO hace: bloquear

Decisión de AH tras verlo planteado, y coherente con "MEMORIA SÍ, LLAVE NO"
(migración 067, aplicada ya en seis sitios): el camino MUESTRA por dónde vas
y sugiere el siguiente, pero no cierra ninguna puerta. En orientación
vocacional el bloqueo tiene un costo concreto — alguien con curiosidad por
enfermería no debería tener que ver tres videos antes de llegar.

Aditiva, nullable e idempotente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect


revision = '070_ruta_de_videos'
down_revision = '069_videos_de_orientacion'
branch_labels = None
depends_on = None

_VIDEOS = 'orientation_videos'
_VIEWS = 'orientation_video_views'


def _has_table(bind, name: str) -> bool:
    try:
        return name in inspect(bind).get_table_names()
    except Exception:
        return False


def _has_column(bind, table: str, name: str) -> bool:
    try:
        return any(c["name"] == name for c in inspect(bind).get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, _VIDEOS, 'stage'):
        op.add_column(_VIDEOS, sa.Column('stage', sa.String(60), nullable=True))
        op.create_index(f'ix_{_VIDEOS}_stage', _VIDEOS, ['stage'])

    if not _has_table(bind, _VIEWS):
        op.create_table(
            _VIEWS,
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'user_id',
                UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'video_id',
                UUID(as_uuid=True),
                sa.ForeignKey(f'{_VIDEOS}.id', ondelete='CASCADE'),
                nullable=False,
            ),
            # `opened_at` y no `watched_at` a propósito: sabemos que abrió el
            # reproductor, no que vio el video entero. El nombre no promete
            # más de lo que el dato aguanta.
            sa.Column('opened_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('user_id', 'video_id', name='uq_video_view_user_video'),
        )
        op.create_index(f'ix_{_VIEWS}_user_id', _VIEWS, ['user_id'])
        op.create_index(f'ix_{_VIEWS}_video_id', _VIEWS, ['video_id'])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _VIEWS):
        op.drop_table(_VIEWS)
    if _has_column(bind, _VIDEOS, 'stage'):
        op.drop_column(_VIDEOS, 'stage')
