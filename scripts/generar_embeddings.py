"""Genera el embedding de cada programa investigado.

    python scripts/generar_embeddings.py --limit 50   # prueba
    python scripts/generar_embeddings.py              # todos los que falten

Es **reanudable**: sólo toca las filas con `embedding IS NULL`, así que si se
corta a la mitad se vuelve a lanzar y sigue donde iba. Con 15.483 programas de
~40 tokens cada uno el costo ronda un centavo de dólar, pero la llamada puede
fallar por red y repetir 15.000 vectores por gusto es tonto.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import ProgramaInvestigado  # noqa: E402
from app.services import embeddings as emb  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="cuántos generar · sin esto, todos los que falten")
    ap.add_argument("--batch", type=int, default=emb.TAMANO_LOTE)
    args = ap.parse_args()

    db = SessionLocal()
    try:
        pendientes = db.execute(text(
            "SELECT count(*) FROM programas_investigados WHERE embedding IS NULL"
        )).scalar()
        total = db.query(ProgramaInvestigado).count()
        print(f"programas: {total} · sin embedding: {pendientes}")
        if not pendientes:
            # Sin pendientes NO se sale sin más: el índice puede faltar (la
            # migración ya no lo crea) o haberse quedado calculado sobre menos
            # vectores de los que hay hoy. Salir aquí dejaba la búsqueda
            # semántica corriendo sin índice y a nadie avisado.
            print("nada que embeber · se revisa el índice")
            reconstruir_indice(db)
            return 0

        hechos = 0
        objetivo = args.limit or pendientes
        while hechos < objetivo:
            faltan = min(args.batch, objetivo - hechos)
            filas = (
                db.query(ProgramaInvestigado)
                .from_statement(text(
                    "SELECT * FROM programas_investigados "
                    "WHERE embedding IS NULL ORDER BY institucion, nombre LIMIT :n"
                ).bindparams(n=faltan))
                .all()
            )
            if not filas:
                break

            vectores = await emb.embeber([emb.texto_de_programa(p) for p in filas])

            # Un solo viaje por lote, no uno por fila.
            #
            # Escribir fila a fila son 256 ida-y-vuelta a Neon por lote, y con
            # ~75 ms de latencia cada uno eso son ~19 s de espera por lote
            # contra ~4 s que tarda la API de embeddings: el cuello no era el
            # proveedor, éramos nosotros. Medido sobre el catálogo de 33.907
            # programas, la diferencia es de ~2,7 horas a ~20 minutos, y este
            # script hay que correrlo también contra producción.
            #
            # El vector se escribe por SQL directo porque la columna es de tipo
            # `vector` de pgvector y el modelo no la declara (ver models.py).
            db.execute(
                text("UPDATE programas_investigados AS pi "
                     "   SET embedding = CAST(v.emb AS vector) "
                     "  FROM (SELECT unnest(CAST(:ids AS uuid[])) AS id, "
                     "               unnest(CAST(:embs AS text[])) AS emb) AS v "
                     " WHERE pi.id = v.id"),
                {
                    "ids": [str(p.id) for p in filas],
                    "embs": ["[" + ",".join(f"{x:.6f}" for x in v) + "]"
                             for v in vectores],
                },
            )
            db.commit()
            hechos += len(filas)
            print(f"  {hechos}/{objetivo}")

        restantes = db.execute(text(
            "SELECT count(*) FROM programas_investigados WHERE embedding IS NULL"
        )).scalar()
        print(f"\nlisto · quedan sin embedding: {restantes}")

        if not restantes:
            reconstruir_indice(db)
    finally:
        db.close()
    return 0


def _soporta_hnsw(db) -> bool:
    v = db.execute(text(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    )).scalar()
    if not v:
        return False
    try:
        partes = tuple(int(x) for x in str(v).split(".")[:2])
    except ValueError:
        return False
    return partes >= (0, 5)


def reconstruir_indice(db) -> None:
    """Crea (o rehace) el índice vectorial · **sólo con los vectores cargados**.

    Va aquí y no en la migración porque IVFFlat calcula sus centroides con
    k-means sobre las filas existentes al crear el índice. Creado sobre una tabla
    vacía queda con clusters degenerados y, como Postgres escanea una sola lista
    por defecto, las búsquedas devuelven resultados casi aleatorios: pasó, y
    devolvía Skilled Trades a quien preguntaba por dibujo.

    ## Por qué HNSW cuando se puede (pgvector ≥ 0.5)

    El defecto de IVFFlat en este producto no es la velocidad: es que **hay que
    rehacerlo cada vez que el catálogo crece**, y el catálogo crece por tandas
    de extracción constantemente. Un índice calculado sobre 5.086 vectores no
    representa a 33.907, y la forma en que se degrada es la peor posible para
    detectarla: sigue devolviendo resultados, sólo que peores. Es la misma clase
    de fallo silencioso que el `embedding IS NOT NULL` que se acaba de arreglar.

    HNSW es incremental —cada fila nueva se inserta en el grafo— así que no
    caduca al crecer la tabla, y su parámetro de búsqueda (`hnsw.ef_search`,
    por defecto 40) no depende del número de filas, a diferencia de `probes`,
    que sí. Cuesta más construirlo, y eso se paga una vez.

    Si pgvector es anterior a 0.5 se cae a IVFFlat con `lists` recalculado, que
    es lo que había.
    """
    n = db.execute(text(
        "SELECT count(*) FROM programas_investigados WHERE embedding IS NOT NULL"
    )).scalar()
    if not n:
        return

    db.execute(text("DROP INDEX IF EXISTS ix_prog_inv_embedding"))
    if _soporta_hnsw(db):
        # ⚠️ **Parcial `WHERE activo`, y no es cosmético.**
        #
        # HNSW **post-filtra**: saca `ef_search` candidatos del índice y recién
        # después aplica el `WHERE`. Con el índice completo, las 15.216 filas
        # ocultas compiten por esos candidatos y se los llevan — medido, una
        # búsqueda sin filtro devolvía **9 resultados de 33.552**. Y el síntoma
        # engaña: con un filtro estrecho (un país, un área) Postgres deja de
        # usar el índice y escanea, así que ahí devolvía los 120 correctos. O
        # sea que fallaba justo en el caso por defecto del estudiante.
        #
        # Con el predicado parcial, todo lo que hay en el índice ya pasa el
        # filtro y los candidatos no se desperdician. El predicado tiene que
        # coincidir con el de la consulta (`busqueda_programas._DESDE`) para que
        # el planificador lo use.
        print(f"construyendo indice hnsw parcial sobre {n} vectores…")
        db.execute(text(
            "CREATE INDEX ix_prog_inv_embedding ON programas_investigados "
            "USING hnsw (embedding vector_cosine_ops) "
            "WHERE activo AND embedding IS NOT NULL"
        ))
    else:
        # Recomendación de pgvector: lists ~ filas/1000 hasta 1M de filas, con un
        # mínimo razonable para que haya de dónde escoger.
        lists = max(10, min(1000, n // 1000 or 1))
        print(f"reconstruyendo indice ivfflat sobre {n} vectores (lists={lists})…")
        db.execute(text(
            f"CREATE INDEX ix_prog_inv_embedding ON programas_investigados "
            f"USING ivfflat (embedding vector_cosine_ops) WITH (lists = {lists})"
        ))
    db.commit()
    print("indice listo")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
