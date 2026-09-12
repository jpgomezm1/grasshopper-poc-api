"""Segunda pasada · completa las instituciones que se truncaron en el tope de 150.

Por qué hace falta
------------------
La extracción tiene un tope de 150 programas por institución para que un agente
no se quede atrapado en una universidad grande y deje el lote sin hacer. Funcionó
—el barrido cerró con 0 pendientes— pero dejó a las universidades **más grandes
entregadas a medias**, que son justo las que un estudiante busca primero:
Portsmouth publica 465 programas y hay 150, Kansas 550, Buffalo 404, UCF 439.

Este script arma los lotes de la segunda pasada. La diferencia con
`preparar_lotes_investigacion.py` es que aquí la institución **ya tiene catálogo**,
así que el lote incluye la lista de lo que ya está cargado. Sin eso el agente
vuelve a extraer los mismos 150, el cargador los descarta por duplicado y la
pasada no añade nada.

El tope
-------
Se sube a 400. No se quita del todo: sin ningún límite, un agente puede gastar su
contexto en el catálogo de posgrado de una sola universidad. 400 cubre el total
real de casi todas las medidas; las tres que lo superan (Kansas 550, Portsmouth
465, Oregon State 746 con minors) quedan señaladas para una tercera vuelta.

Uso
---
    python scripts/preparar_lotes_completado.py
    python scripts/preparar_lotes_completado.py --por-lote 6
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from scripts.preparar_lotes_investigacion import dominio, ruta  # noqa: E402

SALIDA = Path("data/catalogo/lotes_completado")


def main() -> int:
    ap = argparse.ArgumentParser(description="Arma los lotes de completado")
    ap.add_argument("--por-lote", type=int, default=6)
    # La firma del truncamiento es quedarse EXACTAMENTE en el tope. Una
    # institucion con 340 o 755 no se trunco: se completo en varias pasadas o
    # se reconecto con su catalogo de agosto, y volver a lanzarla es gastar un
    # agente en algo que ya esta.
    ap.add_argument("--min", type=int, default=148)
    ap.add_argument("--max", type=int, default=152)
    # El tope es por pasada, no absoluto: una universidad que ya llego al
    # limite anterior necesita uno mayor para terminar su catalogo.
    ap.add_argument("--tope", type=int, default=400)
    args = ap.parse_args()

    db = SessionLocal()
    filas = list(
        db.execute(
            text(
                """
                select pi.institucion,
                       count(*) cargados,
                       max(ic.country), max(ic.city), max(ic.website),
                       max(ic.niveles_autorizados::text)
                  from programas_investigados pi
                  join institutions_catalog ic
                    on lower(ic.name) = lower(pi.institucion) and ic.active
                 group by 1
                having count(*) between :min and :max
                 order by 1
                """
            ),
            {"min": args.min, "max": args.max},
        )
    )

    lote_datos: List[Dict[str, Any]] = []
    for inst, cargados, pais, ciudad, web, niveles in filas:
        ya = [
            r[0]
            for r in db.execute(
                text(
                    "select nombre from programas_investigados "
                    "where institucion = :i order by nombre"
                ),
                {"i": inst},
            )
        ]
        lote_datos.append(
            {
                "institucion": inst,
                "pais": pais,
                "ciudad": ciudad,
                "dominio": dominio(web),
                "ruta_catalogo": ruta(web),
                "puede_vender": json.loads(niveles) if niveles else [],
                "ya_cargados": cargados,
                "tope_de_esta_pasada": args.tope,
                "programas_que_YA_estan": ya,
            }
        )
    db.close()

    SALIDA.mkdir(parents=True, exist_ok=True)
    for f in SALIDA.glob("comp_*.json"):
        f.unlink()

    lotes = [lote_datos[i : i + args.por_lote] for i in range(0, len(lote_datos), args.por_lote)]
    print(f"Instituciones truncadas : {len(lote_datos)}")
    print(f"Lotes de {args.por_lote}             : {len(lotes)}")
    print()
    for n, lote in enumerate(lotes, start=1):
        p = SALIDA / f"comp_{n:02d}.json"
        p.write_text(
            json.dumps({"lote": f"{n:02d}", "instituciones": lote}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  {p}  ·  {len(lote)}: {', '.join(x['institucion'][:22] for x in lote)}")
    print()
    print(f"Listos en {SALIDA.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
