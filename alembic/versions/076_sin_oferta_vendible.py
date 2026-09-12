"""Marca las fichas que se investigaron y no tienen oferta vendible.

Por qué hace falta una columna y no basta con `active`
------------------------------------------------------
La cola de investigación es "fichas activas que no tienen ni un programa".
Una institución cuyo catálogo existe pero **no se le puede vender a un
colombiano** —no acepta solicitudes internacionales, es formación subvencionada
para desempleados de una comunidad, el holding no dicta nada él mismo— termina
con cero programas y por tanto vuelve a la cola en cada tanda. Se gastó un lote
entero de 8 agentes reconfirmando ocho callejones sin salida ya conocidos.

`active = false` no sirve para esto: significa "la ficha no va en el producto",
y se usa para dominios secuestrados o instituciones que cerraron. Aquí la ficha
es legítima y el cliente la tiene en su archivo; lo que pasa es que hoy no hay
nada que ofrecerle a un estudiante. Es un estado distinto y reversible: si
Guildford reabre solicitudes internacionales el año que viene, se limpia el
campo y vuelve a la cola.

El texto es la evidencia, no una bandera: queda escrito por qué, para poder
llevárselo al cliente sin volver a mirar el sitio.

Revision ID: 076_sin_oferta_vendible
Revises: 075_catalogo_autorizado
"""
from alembic import op
import sqlalchemy as sa

revision = '076_sin_oferta_vendible'
down_revision = '075_catalogo_autorizado'
branch_labels = None
depends_on = None


def _tiene_columna(nombre: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return nombre in {c["name"] for c in insp.get_columns("institutions_catalog")}


def upgrade() -> None:
    # Idempotente: la migración se corre a mano en local y en Heroku, y ya pasó
    # una vez que una columna existiera en la base sin estar declarada.
    if not _tiene_columna("sin_oferta_vendible"):
        op.add_column(
            "institutions_catalog",
            sa.Column("sin_oferta_vendible", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _tiene_columna("sin_oferta_vendible"):
        op.drop_column("institutions_catalog", "sin_oferta_vendible")
