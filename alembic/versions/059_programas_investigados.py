"""Catálogo de programas investigados + búsqueda vectorial.

Revision ID: 059_programas_investigados
Revises: 058_bitrix_payload_hash

15.483 programas de 306 instituciones, extraídos del sitio oficial de cada una.

**Por qué tabla aparte y no `programs`.** Este dato lo investigamos nosotros; la
agencia no lo ha confirmado. Verónica tiene un Excel a nivel de programa que
todavía no llega, y cuando llegue hay que poder distinguir qué validó ella y qué
dedujimos: mezclado, esa distinción se pierde para siempre. Separado, lo
confirmado entra a `programs` y esto se borra con un DELETE.

**No hay columna de precio, y es a propósito.** El precio cambia por intake y por
nacionalidad, y la agencia tiene tarifas negociadas propias: un precio de web
puesto aquí es una promesa que un asesor no puede sostener frente a una familia.
Que la columna no exista es la garantía de que nadie la llena "por mientras".

La columna `embedding` habilita la búsqueda semántica. Es nullable porque los
embeddings se generan en una pasada aparte: cargar el catálogo no puede depender
de que un proveedor externo responda.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "059_programas_investigados"
down_revision = "058_bitrix_payload_hash"
branch_labels = None
depends_on = None

# text-embedding-3-small · 1536 dimensiones. Se fija aquí porque cambiar de
# modelo cambia la dimensión y obliga a regenerar todo: no es un parámetro.
DIMENSIONES = 1536


def _tiene_vector(bind) -> bool:
    """pgvector disponible en esta base.

    En Neon está disponible pero no instalada por defecto. En SQLite (los tests)
    no existe, y la tabla debe poder crearse igual sin la columna vectorial —
    si no, toda la suite dependería de Postgres.
    """
    if bind.dialect.name != "postgresql":
        return False
    fila = bind.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
    ).first()
    return fila is not None


def upgrade() -> None:
    bind = op.get_bind()
    vector_ok = _tiene_vector(bind)
    if vector_ok:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    inspector = sa.inspect(bind)
    if "programas_investigados" in inspector.get_table_names():
        return

    columnas = [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # De dónde salió · sin esto no se puede auditar ni rehacer.
        sa.Column("institucion", sa.String(255), nullable=False, index=True),
        sa.Column("nombre", sa.String(500), nullable=False),
        sa.Column("pais", sa.String(80), nullable=True, index=True),
        sa.Column("ciudad", sa.String(160), nullable=True),
        # `nivel` usa el mismo vocabulario que `programs.type`.
        sa.Column("nivel", sa.String(40), nullable=False, index=True),
        # `area` ya normalizada al vocabulario de app/services/areas.py · el
        # texto original se conserva en `area_cruda` para poder rehacer el mapeo
        # sin volver a extraer.
        sa.Column("area", sa.String(80), nullable=True, index=True),
        sa.Column("area_cruda", sa.String(160), nullable=True),
        sa.Column("duracion", sa.String(120), nullable=True),
        # CRICOS, RTO, código nacional · lo que hace verificable la fila.
        sa.Column("codigo_oficial", sa.String(80), nullable=True),
        sa.Column("url_fuente", sa.Text, nullable=True),
        sa.Column("dominio", sa.String(160), nullable=True),
        # Trazabilidad de la extracción.
        sa.Column("lote", sa.String(8), nullable=True),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    ]
    if vector_ok:
        columnas.append(sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True))

    op.create_table("programas_investigados", *columnas)

    if vector_ok:
        # La columna se crea como ARRAY y se convierte a `vector` aquí: declararla
        # como vector desde SQLAlchemy exigiría el paquete pgvector como
        # dependencia de la migración, y la migración tiene que poder correr en
        # una base sin él.
        op.execute(
            f"ALTER TABLE programas_investigados "
            f"ALTER COLUMN embedding TYPE vector({DIMENSIONES}) "
            f"USING embedding::vector({DIMENSIONES})"
        )
        # Índice IVFFlat para el orden por coseno. `lists` ~ raíz de las filas
        # esperadas (15.483 → ~124). Se crea aunque la tabla esté vacía; Postgres
        # lo permite y se reconstruye solo al llenarla.
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_prog_inv_embedding "
            "ON programas_investigados USING ivfflat (embedding vector_cosine_ops) "
            "WITH (lists = 124)"
        )

    # Una institución no repite nombre de programa · lo mismo que garantiza el
    # consolidado, ahora garantizado por la base.
    op.create_index(
        "ux_prog_inv_institucion_nombre",
        "programas_investigados", ["institucion", "nombre"], unique=True,
    )
    # El camino que recorre el recomendador: país → área.
    op.create_index(
        "ix_prog_inv_pais_area", "programas_investigados", ["pais", "area"],
    )


def downgrade() -> None:
    op.drop_table("programas_investigados")
