"""Índices para la búsqueda de programas · el catálogo se duplicó con creces.

Por qué ahora
-------------
`programas_investigados` pasó de 15.483 a 49.111 filas (33.907 activas) en las
tandas de septiembre 2026, y la búsqueda que las consulta cambia de forma en el
mismo movimiento: multi-selección, facetas con conteo y texto libre.

**Toda consulta de la búsqueda lleva `pi.activo = true`** (`busqueda_programas.py`,
`_where()`), y hasta hoy `activo` no tenía índice — a diferencia de
`Program.active`, que sí lo tiene. Los índices de aquí son **parciales sobre esa
condición**: indexan sólo el 69% de la tabla que se consulta y dejan fuera las
15.204 filas ocultas, que nadie busca.

Sobre `CREATE INDEX CONCURRENTLY`
--------------------------------
No se usa, a propósito. `CONCURRENTLY` existe para no bloquear escrituras en
tablas grandes con tráfico, y tiene un coste: no puede correr dentro de una
transacción, y si falla deja un índice inválido que hay que limpiar a mano. Esta
tabla tiene 49k filas —el índice se construye en segundos— y sólo se escribe en
lote desde un script, nunca desde la API. Un bloqueo de menos de un segundo
durante el release es más barato que un índice inválido en producción.

Sobre `unaccent`
----------------
`unaccent()` no es IMMUTABLE (depende de un diccionario que podría cambiar), así
que Postgres no deja indexarla directamente. El envoltorio de abajo es el patrón
aceptado para rodearlo. La alternativa era indexar sólo `lower(nombre)` y perder
las tildes, y eso importa: el catálogo tiene nombres en español
(`Grado en Administración`) y un estudiante colombiano escribe sin tilde la mitad
de las veces. La coincidencia literal es un **refuerzo** del puntaje, no una
compuerta, así que el riesgo de un fallo aquí es que un programa puntúe un poco
más bajo — nunca que desaparezca.

Revision ID: 077_indices_busqueda
Revises: 076_sin_oferta_vendible
"""
from alembic import op
import sqlalchemy as sa

revision = '077_indices_busqueda'
down_revision = '076_sin_oferta_vendible'
branch_labels = None
depends_on = None


def _indices() -> set:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {i["name"] for i in insp.get_indexes("programas_investigados")}


def upgrade() -> None:
    # Idempotente: estas migraciones se corren a mano en local y en Heroku, y ya
    # pasó una vez que una columna existiera en la base sin estar declarada.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # `IMMUTABLE` es una promesa que le hacemos a Postgres para poder indexar.
    # Es cierta mientras nadie cambie el diccionario de unaccent, cosa que no
    # hacemos. Si algún día se cambiara, habría que reindexar.
    op.execute("""
        CREATE OR REPLACE FUNCTION inmutable_unaccent(text)
        RETURNS text AS $$
            SELECT public.unaccent('public.unaccent'::regdictionary, $1)
        $$ LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
    """)

    existentes = _indices()

    # El camino que recorre la búsqueda: filtro duro por país + área + nivel.
    # Ya existe `ix_prog_inv_pais_area` sin `nivel` y sin la condición parcial;
    # se deja porque otras consultas lo usan y borrarlo es otro cambio.
    if "ix_prog_inv_activo_pais_area_nivel" not in existentes:
        op.execute("""
            CREATE INDEX ix_prog_inv_activo_pais_area_nivel
                ON programas_investigados (pais, area, nivel)
             WHERE activo
        """)

    # La página de una institución y el filtro por institución del asesor.
    if "ix_prog_inv_activo_institucion" not in existentes:
        op.execute("""
            CREATE INDEX ix_prog_inv_activo_institucion
                ON programas_investigados (institucion)
             WHERE activo
        """)

    # Coincidencia literal sobre el nombre · `%termino%` no puede usar un btree,
    # y con 33.907 nombres un scan secuencial por cada tecleo no es viable.
    if "ix_prog_inv_nombre_trgm" not in existentes:
        op.execute("""
            CREATE INDEX ix_prog_inv_nombre_trgm
                ON programas_investigados
             USING gin (inmutable_unaccent(lower(nombre)) gin_trgm_ops)
             WHERE activo
        """)


def downgrade() -> None:
    for nombre in ("ix_prog_inv_nombre_trgm",
                   "ix_prog_inv_activo_institucion",
                   "ix_prog_inv_activo_pais_area_nivel"):
        op.execute(f"DROP INDEX IF EXISTS {nombre}")
    op.execute("DROP FUNCTION IF EXISTS inmutable_unaccent(text)")
    # Las extensiones no se quitan: puede haber otra cosa usándolas.
