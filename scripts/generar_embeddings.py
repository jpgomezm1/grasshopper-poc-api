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
            print("nada que hacer")
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
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
