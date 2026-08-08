"""Genera el embedding de cada ficha del catálogo autorizado (`programs`).

    python scripts/generar_embeddings_catalogo.py

Hermano de `generar_embeddings.py`, que hace lo mismo con los programas
investigados. Son dos scripts y no uno porque son dos catálogos con distinto
dueño: `programs` es lo que la agencia autorizó vender y se regenera cuando la
clienta actualiza su Excel; `programas_investigados` es nuestro y se regenera
cuando volvemos a extraer.

Reanudable: sólo toca las filas con `embedding IS NULL`.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Program  # noqa: E402
from app.services import embeddings as emb  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--batch", type=int, default=emb.TAMANO_LOTE)
    args = ap.parse_args()

    db = SessionLocal()
    try:
        pendientes = db.execute(text(
            "SELECT count(*) FROM programs WHERE embedding IS NULL AND active"
        )).scalar()
        print(f"fichas activas sin embedding: {pendientes}")

        hechos = 0
        objetivo = args.limit or pendientes
        while hechos < objetivo:
            faltan = min(args.batch, objetivo - hechos)
            filas = (
                db.query(Program)
                .from_statement(text(
                    "SELECT * FROM programs WHERE embedding IS NULL AND active "
                    "ORDER BY institution, name LIMIT :n"
                ).bindparams(n=faltan))
                .all()
            )
            if not filas:
                break
            vectores = await emb.embeber([emb.texto_de_institucion(p) for p in filas])
            for p, v in zip(filas, vectores):
                db.execute(
                    text("UPDATE programs SET embedding = :v WHERE id = :id"),
                    {"v": "[" + ",".join(f"{x:.6f}" for x in v) + "]", "id": p.id},
                )
            db.commit()
            hechos += len(filas)
            print(f"  {hechos}/{objetivo}")

        restantes = db.execute(text(
            "SELECT count(*) FROM programs WHERE embedding IS NULL AND active"
        )).scalar()
        print(f"\nquedan sin embedding: {restantes}")
        if not restantes:
            reconstruir_indice(db)
    finally:
        db.close()
    return 0


def reconstruir_indice(db) -> None:
    """Crea (o rehace) el índice IVFFlat de `programs`.

    Va aquí y no en la migración por lo mismo que en el catálogo investigado:
    IVFFlat calcula sus centroides con k-means sobre las filas existentes, y
    sobre una columna recién creada (toda NULL) quedan degenerados. Ya pasó una
    vez y las búsquedas devolvían casi cualquier cosa.
    """
    n = db.execute(text(
        "SELECT count(*) FROM programs WHERE embedding IS NOT NULL"
    )).scalar()
    if not n:
        return
    lists = max(10, min(1000, n // 1000 or 1))
    print(f"reconstruyendo indice ivfflat sobre {n} vectores (lists={lists})…")
    db.execute(text("DROP INDEX IF EXISTS ix_programs_embedding"))
    db.execute(text(
        f"CREATE INDEX ix_programs_embedding ON programs "
        f"USING ivfflat (embedding vector_cosine_ops) WITH (lists = {lists})"
    ))
    db.commit()
    print("indice listo")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
