"""El catálogo autorizado · qué niveles puede vender la agencia en cada institución.

Hasta hoy `institutions_catalog.programs_offered` guardaba el texto crudo del
Excel del cliente ("Vocacionales (Cert, Dip, Adv Dip)", "Pregrado & Postgrado",
"Undergraduate & Graduate", "High school"…) — mismo concepto escrito de ocho
maneras, en dos idiomas. Sirve para mostrar, no para filtrar.

`niveles_autorizados` es ese mismo dato normalizado a un vocabulario cerrado.
Existe porque es la mitad del pedido de Verónica que no se podía cumplir: *"el
Excel te dice que de FIU Miami solo puedes vender los pregrados, ya al sistema
con IA le toca ir a buscar cuáles son"*. Sin un nivel comparable, la búsqueda de
programas no puede saber que la maestría de esa universidad NO se puede vender.

`prioridad` queda nullable y vacía a propósito. Es el 1-10 / estrellas que la
clienta prometió el 21-07 y que el archivo del 08-09 todavía no trae. Se deja
lista para cargarla sin volver a importar las 694 filas · NULL significa "sin
priorizar", no "prioridad cero".

Ambas son aditivas: nada de lo que hoy existe cambia de significado.

Revision ID: 075_catalogo_autorizado
Revises: 074_escala_gpa_programa
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '075_catalogo_autorizado'
down_revision = '074_escala_gpa_programa'
branch_labels = None
depends_on = None


def _columnas() -> set:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns('institutions_catalog')}


def _indices() -> set:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {i['name'] for i in insp.get_indexes('institutions_catalog')}


def upgrade():
    # Idempotente · las ramas de Neon (local y producción) no van siempre a la
    # misma altura, y un release que revienta por "column already exists" deja
    # el despliegue a medias.
    cols = _columnas()
    if 'niveles_autorizados' not in cols:
        op.add_column(
            'institutions_catalog',
            sa.Column(
                'niveles_autorizados',
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )
    if 'prioridad' not in cols:
        op.add_column(
            'institutions_catalog',
            sa.Column('prioridad', sa.Integer(), nullable=True),
        )
    # Se consulta siempre junto con `active` al armar el catálogo del estudiante.
    if 'ix_institutions_catalog_prioridad' not in _indices():
        op.create_index(
            'ix_institutions_catalog_prioridad',
            'institutions_catalog',
            ['prioridad'],
        )


def downgrade():
    if 'ix_institutions_catalog_prioridad' in _indices():
        op.drop_index('ix_institutions_catalog_prioridad', table_name='institutions_catalog')
    cols = _columnas()
    if 'prioridad' in cols:
        op.drop_column('institutions_catalog', 'prioridad')
    if 'niveles_autorizados' in cols:
        op.drop_column('institutions_catalog', 'niveles_autorizados')
