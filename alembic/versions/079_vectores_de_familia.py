"""El vector de cada familia profesional aconsejada.

Revision ID: 079_vectores_de_familia
Revises: 078_glosa_de_programa

## Por qué una tabla y no una columna

`career_families` vive dentro del JSON de `consolidated_profiles.profile_data`,
y ahí no se puede indexar ni comparar por vector. Son 3-5 por estudiante y cada
una necesita su propio embedding, así que la fila natural es
(estudiante, familia), no (estudiante).

## Por qué se cachea

Es el mismo argumento de `perfil_vectores` (migración 060): pedirle un embedding
al proveedor en cada visita a la pantalla de programas mete una dependencia de
red en el camino crítico para recalcular algo que no cambió. La `firma` es la
huella del texto que se embebió; cuando el perfil se regenera y el modelo
reescribe las familias, la firma deja de coincidir y el vector se rehace solo.

Lo que NO hace esta migración, a propósito: crear el índice vectorial. Son unas
pocas filas por estudiante y siempre se leen por `user_id`, que sí está en la
llave primaria — un índice HNSW aquí no tendría a quién servir. (En `059` y
`060` la razón para no crearlo era otra: los centroides degenerados sobre una
columna recién creada.)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "079_vectores_de_familia"
down_revision = "078_glosa_de_programa"
branch_labels = None
depends_on = None

DIMENSIONES = 1536


def _tiene_vector(bind) -> bool:
    if bind.dialect.name != "postgresql":
        return False
    return bind.execute(
        sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    ).first() is not None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "familias_vectores" in inspector.get_table_names():
        return  # idempotente · el release la puede correr dos veces

    vector_ok = _tiene_vector(bind)
    columnas = [
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  primary_key=True),
        # La posición de la familia dentro del perfil · el modelo las devuelve
        # en orden de calce y ese orden es parte del consejo, así que es la
        # forma honesta de nombrarlas. No hay un id estable: el nombre lo
        # escribe un LLM y cambia entre generaciones.
        sa.Column("indice", sa.SmallInteger, primary_key=True),
        # Huella del texto embebido. Si el perfil se regenera y el modelo
        # reescribe la familia, deja de coincidir y el vector se rehace.
        sa.Column("firma", sa.String(64), nullable=False),
        sa.Column("actualizado", sa.DateTime, nullable=False),
    ]
    if vector_ok:
        columnas.append(
            sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True)
        )
    op.create_table("familias_vectores", *columnas)
    if vector_ok:
        op.execute(
            f"ALTER TABLE familias_vectores ALTER COLUMN embedding "
            f"TYPE vector({DIMENSIONES}) USING embedding::vector({DIMENSIONES})"
        )


def downgrade() -> None:
    op.drop_table("familias_vectores")
