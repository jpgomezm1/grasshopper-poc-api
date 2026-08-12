"""La convocatoria a la que el estudiante quiere adaptar su CV (2026-08-10).

Revision ID: 064_cv_targets
Revises: 063_cv_variantes_y_foto
Create Date: 2026-08-10

El estudiante pega el texto de una vacante, un programa, una beca o una
práctica, y la IA le dice **qué le falta** y le propone un CV adaptado.

Por qué es una tabla y no un campo más de `cv_profiles`:

  * son varias — uno se postula a más de un sitio, y comparar la propuesta de
    cada convocatoria contra el CV base es justo el valor;
  * el análisis tarda más de lo que Heroku aguanta en un request (corta a los
    30 s), así que hace falta un `status` para poder encolar y consultar;
  * `raw_text` es texto ajeno pegado por el usuario y merece vivir aparte.

**`proposal` no es el CV.** Es una propuesta con forma de `overrides`, que el
estudiante aplica si quiere. Es el mismo principio que ya defiende
`linkedin_import_service`: es su hoja de vida y lleva su nombre, así que nada
se escribe sin que lo confirme.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = '064_cv_targets'
down_revision = '063_cv_variantes_y_foto'
branch_labels = None
depends_on = None

_TABLE = 'cv_targets'


def _has_table(bind, name: str) -> bool:
    try:
        return inspect(bind).has_table(name)
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLE):
        return

    es_postgres = bind.dialect.name == 'postgresql'
    uuid_type = postgresql.UUID(as_uuid=True) if es_postgres else sa.String(36)

    op.create_table(
        _TABLE,
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column(
            'user_id', uuid_type,
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False, index=True,
        ),
        # job · program · scholarship · internship · other. Sin CHECK: el tipo
        # lo deduce la IA del propio texto y encajarlo a la fuerza en cinco
        # valores fijos a nivel de base sólo produce inserciones fallidas.
        sa.Column('kind', sa.String(30), nullable=True),
        sa.Column('title', sa.String(300), nullable=True),
        sa.Column('organization', sa.String(200), nullable=True),
        sa.Column('raw_text', sa.Text(), nullable=True),

        # Qué pide la convocatoria · cómo le va al estudiante · qué proponemos.
        sa.Column('parsed', sa.JSON(), nullable=True),
        sa.Column('analysis', sa.JSON(), nullable=True),
        sa.Column('proposal', sa.JSON(), nullable=True),

        # pending → analyzing → ready | failed
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('error', sa.String(500), nullable=True),

        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, _TABLE):
        op.drop_table(_TABLE)
