"""Vector del perfil del estudiante + vector de cada institución del catálogo.

Revision ID: 060_vectores_perfil_y_catalogo
Revises: 059_programas_investigados

Dos columnas vectoriales más, por dos razones distintas:

**`perfil_vectores`** · el perfil de un estudiante crece cada vez que usa la app
(tests, journey, journal). Recalcular su vector en cada búsqueda es una llamada a
un proveedor externo por request: lento, y una dependencia de red en el camino
crítico. Se guarda con una *firma* de las señales que lo produjeron, y sólo se
regenera cuando esa firma cambia — o sea, cuando la persona aportó algo nuevo.

**`programs.embedding`** · el catálogo autorizado del cliente (2.511 fichas a
nivel institución) también se ordena por afinidad con el estudiante. Va como
columna de `programs` y no como tabla aparte porque es un atributo de la ficha,
igual que `area` o `priority`, y muere con ella.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "060_vectores_perfil_y_catalogo"
down_revision = "059_programas_investigados"
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
    vector_ok = _tiene_vector(bind)
    inspector = sa.inspect(bind)

    if "perfil_vectores" not in inspector.get_table_names():
        columnas = [
            # Uno por estudiante · la clave primaria es el usuario, no un id
            # propio: no tiene sentido que existan dos vectores del mismo perfil.
            sa.Column("user_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="CASCADE"),
                      primary_key=True),
            # Huella de las señales que lo produjeron. Si no coincide con la
            # firma actual del perfil, el vector está viejo y se regenera.
            sa.Column("firma", sa.String(64), nullable=False),
            sa.Column("actualizado", sa.DateTime, nullable=False),
        ]
        if vector_ok:
            columnas.append(
                sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True)
            )
        op.create_table("perfil_vectores", *columnas)
        if vector_ok:
            op.execute(
                f"ALTER TABLE perfil_vectores ALTER COLUMN embedding "
                f"TYPE vector({DIMENSIONES}) USING embedding::vector({DIMENSIONES})"
            )

    columnas_programs = {c["name"] for c in inspector.get_columns("programs")}
    if vector_ok and "embedding" not in columnas_programs:
        op.execute(f"ALTER TABLE programs ADD COLUMN embedding vector({DIMENSIONES})")

    # Igual que en la 059: **el índice IVFFlat no se crea aquí**. Sus centroides
    # salen de un k-means sobre las filas existentes, y sobre una columna recién
    # creada (toda NULL) quedan degenerados. Lo crea el script que llena los
    # vectores, cuando ya hay sobre qué calcularlos.


def downgrade() -> None:
    op.drop_table("perfil_vectores")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE programs DROP COLUMN IF EXISTS embedding")
