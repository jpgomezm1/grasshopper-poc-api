"""La foto del CV se guarda en Neon, no en un bucket (2026-08-10).

Revision ID: 065_foto_en_la_base
Revises: 064_cv_targets
Create Date: 2026-08-10

La 063 añadió `users.photo_url` para apuntar a un objeto en Supabase. Pero ese
storage corre contra un stub en memoria hasta que alguien configure las
credenciales, así que la foto se perdía en cada reinicio: la columna existía y
lo que apuntaba, no.

Se guarda la imagen en la base. A esta escala sale a cuenta —son estudiantes,
la foto va topada a 2 MB— y entra en el mismo backup y la misma transacción que
el resto de la hoja de vida.

**En su propia tabla, no como columna de `users`.** SQLAlchemy trae todas las
columnas por defecto y `users` se consulta en cada request autenticado: un
`bytea` de 2 MB ahí dentro viajaría en cada login y en cada llamada a la API,
para algo que sólo hace falta al generar el PDF.

`users.photo_url` se elimina, y es la única migración de esta serie que quita
algo. Se justifica porque la introdujo la 063 **hoy mismo**, en este mismo
cambio sin desplegar: no hay código en producción que la lea ni datos que
perder. Dejarla sería exactamente el error nº1 del CLAUDE.md de este backend —
un campo que nadie lee.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = '065_foto_en_la_base'
down_revision = '064_cv_targets'
branch_labels = None
depends_on = None

_TABLE = 'user_photos'


def _has_table(bind, name: str) -> bool:
    try:
        return inspect(bind).has_table(name)
    except Exception:
        return False


def _has_column(bind, tabla: str, columna: str) -> bool:
    try:
        inspector = inspect(bind)
        if not inspector.has_table(tabla):
            return False
        return columna in {c['name'] for c in inspector.get_columns(tabla)}
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, _TABLE):
        es_postgres = bind.dialect.name == 'postgresql'
        uuid_type = postgresql.UUID(as_uuid=True) if es_postgres else sa.String(36)

        op.create_table(
            _TABLE,
            # El user_id ES la clave primaria · una foto por persona.
            sa.Column(
                'user_id', uuid_type,
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                primary_key=True,
            ),
            sa.Column('content_type', sa.String(60), nullable=False),
            sa.Column('data', sa.LargeBinary(), nullable=False),
            sa.Column('size_bytes', sa.Integer(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )

    if _has_column(bind, 'users', 'photo_url'):
        op.drop_column('users', 'photo_url')


def downgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, 'users', 'photo_url'):
        op.add_column('users', sa.Column('photo_url', sa.String(500), nullable=True))

    if _has_table(bind, _TABLE):
        op.drop_table(_TABLE)
