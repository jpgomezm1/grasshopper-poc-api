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
            for p, v in zip(filas, vectores):
                # El vector se escribe por SQL directo: la columna es de tipo
                # `vector` de pgvector y el modelo no la declara (ver models.py).
                db.execute(
                    text("UPDATE programas_investigados SET embedding = :v "
                         "WHERE id = :id"),
                    {"v": "[" + ",".join(f"{x:.6f}" for x in v) + "]", "id": p.id},
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


def reconstruir_indice(db) -> None:
    """Crea (o rehace) el índice IVFFlat · **sólo con los vectores ya cargados**.

    Va aquí y no en la migración porque IVFFlat calcula sus centroides con
    k-means sobre las filas existentes al crear el índice. Creado sobre una tabla
    vacía queda con clusters degenerados y, como Postgres escanea una sola lista
    por defecto, las búsquedas devuelven resultados casi aleatorios: pasó, y
    devolvía Skilled Trades a quien preguntaba por dibujo.

    Por eso también se **rehace** cada vez que se completan embeddings: un índice
    calculado sobre 1.000 vectores no representa bien a 15.000.
    """
    n = db.execute(text(
        "SELECT count(*) FROM programas_investigados WHERE embedding IS NOT NULL"
    )).scalar()
    if not n:
        return
    # Recomendación de pgvector: lists ~ filas/1000 hasta 1M de filas, con un
    # mínimo razonable para que haya de dónde escoger.
    lists = max(10, min(1000, n // 1000 or 1))
    print(f"reconstruyendo indice ivfflat sobre {n} vectores (lists={lists})…")
    db.execute(text("DROP INDEX IF EXISTS ix_prog_inv_embedding"))
    db.execute(text(
        f"CREATE INDEX ix_prog_inv_embedding ON programas_investigados "
        f"USING ivfflat (embedding vector_cosine_ops) WITH (lists = {lists})"
    ))
    db.commit()
    print("indice listo")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
