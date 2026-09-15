"""Pasada 1 · auditoría de fichas, antes de gastar la pasada de extracción.

Por qué esta pasada existe
--------------------------
El piloto del 08-09 investigó 24 instituciones y **9 tenían el dominio o el
nombre mal en el archivo del cliente. El 37%**:

  · 2 dominios que no existen (NXDOMAIN, no caída temporal)
  · 1 rebrand con 301 permanente a otro dominio
  · 1 dominio asignado a TRES fichas distintas — dos de ellas equivocadas
  · 1 ficha cuyo nombre no es el de la institución (una "School of Beauty" que
    resultó ser peluquería y barbería, sin un solo curso de estética)
  · 2 con el catálogo real en un subdominio o en el dominio del grupo matriz
  · 2 con bloqueo de Cloudflare en el dominio entero

El piloto de agosto ya había encontrado 2 de 3 con el dato mal, y una de esas
—Brisbane School of Beauty— **volvió intacta en el archivo del 08-09**. No es
mala suerte: es la calidad del insumo, y hay que medirla antes de trabajar sobre
ella.

La extracción es cara (un agente entero por lote de 8). La auditoría es barata:
una petición por institución para responder cuatro preguntas. Correrla primero
evita gastar la cara sobre fichas rotas, **y es un entregable para el cliente por
sí solo**: la lista de sus fichas con el dato malo, que nadie más le va a dar.

Uso
---
    python scripts/preparar_lotes_auditoria.py                  # todas las pendientes
    python scripts/preparar_lotes_auditoria.py --por-lote 30
    python scripts/preparar_lotes_auditoria.py --incluir-sin-sitio
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from scripts.import_catalogo_autorizado import clave_nombre  # noqa: E402
from scripts.preparar_lotes_investigacion import dominio  # noqa: E402

SALIDA = Path("data/catalogo/lotes_auditoria")
AUDITADAS = Path("data/catalogo/auditoria_agentes")


def _ya_auditadas() -> set:
    """Fichas que ya tienen veredicto · no se vuelven a auditar.

    Los lotes se regeneran cada vez que cambia el catalogo (la resolucion movio
    116 fichas), y sin esto una ficha ya auditada volveria a caer en un lote
    nuevo y un agente gastaria su trabajo en repetirla.
    """
    import csv

    vistas = set()
    if not AUDITADAS.exists():
        return vistas
    for archivo in sorted(AUDITADAS.rglob("*.csv")):
        with open(archivo, encoding="utf-8-sig", newline="") as fh:
            for fila in csv.DictReader(fh):
                k = clave_nombre((fila.get("institucion") or "").strip())
                if k:
                    vistas.add(k)
    return vistas


def main() -> int:
    ap = argparse.ArgumentParser(description="Arma los lotes de auditoría de fichas")
    # 25 y no 8: la auditoría son cuatro preguntas por institución, no un
    # catálogo entero. Cabe mucho más en un solo agente.
    ap.add_argument("--por-lote", type=int, default=25)
    ap.add_argument("--max-lotes", type=int)
    ap.add_argument("--pais")
    ap.add_argument(
        "--incluir-sin-sitio",
        action="store_true",
        help="Incluye las 192 sin website · el agente intenta encontrar el dominio",
    )
    args = ap.parse_args()

    db = SessionLocal()
    sql = """
        select ic.name, ic.country, ic.city, ic.website, ic.category,
               ic.niveles_autorizados
        from institutions_catalog ic
        where ic.active
          and not exists (
                select 1 from programas_investigados pi
                where lower(pi.institucion) = lower(ic.name)
          )
    """
    params: Dict[str, Any] = {}
    if not args.incluir_sin_sitio:
        sql += " and coalesce(ic.website, '') <> ''"
    if args.pais:
        sql += " and ic.country = :pais"
        params["pais"] = args.pais
    sql += " order by ic.country, ic.name"

    ya = _ya_auditadas()
    filas: List[Dict[str, Any]] = []
    por_dominio: Dict[str, List[str]] = defaultdict(list)
    saltadas = 0
    for r in db.execute(text(sql), params):
        if clave_nombre(r[0]) in ya:
            saltadas += 1
            continue
        d = dominio(r[3])
        filas.append(
            {
                "institucion": r[0],
                "pais": r[1],
                "ciudad": r[2],
                "dominio_en_la_ficha": d,
                "categoria": r[4],
                "puede_vender": list(r[5] or []) or ["(el archivo del cliente no lo dice)"],
            }
        )
        if d:
            por_dominio[d].append(r[0])
    db.close()

    # El caso `alg.edu.au`: un dominio en tres fichas. Se le avisa al agente en
    # la ficha misma, porque es donde va a poder resolverlo — mirando el sitio.
    compartidos = {d: n for d, n in por_dominio.items() if len(n) > 1}
    for f in filas:
        otras = compartidos.get(f["dominio_en_la_ficha"] or "", [])
        if len(otras) > 1:
            f["ojo"] = (
                "Este dominio aparece en "
                + str(len(otras))
                + " fichas distintas ("
                + " · ".join(x[:40] for x in otras if x != f["institucion"])
                + "). Al menos una está mal asignada: di a cuál corresponde el sitio."
            )

    SALIDA.mkdir(parents=True, exist_ok=True)
    lotes = [filas[i : i + args.por_lote] for i in range(0, len(filas), args.por_lote)]
    if args.max_lotes:
        lotes = lotes[: args.max_lotes]

    print(f"Ya auditadas antes : {saltadas}  (no se repiten)")
    print(f"Fichas a auditar   : {len(filas)}")
    print(f"  sin sitio        : {sum(1 for f in filas if not f['dominio_en_la_ficha'])}")
    print(f"  dominio repetido : {sum(1 for f in filas if f.get('ojo'))} "
          f"en {len(compartidos)} dominios")
    print(f"Lotes de {args.por_lote}       : {len(lotes)}")
    print()
    for n, lote in enumerate(lotes, start=1):
        ruta = SALIDA / f"aud_{n:02d}.json"
        ruta.write_text(
            json.dumps({"lote": f"{n:02d}", "instituciones": lote}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paises = sorted({x["pais"] or "?" for x in lote})
        print(f"  {ruta}  ·  {len(lote)} fichas  ·  {', '.join(paises[:4])}")

    print()
    print(f"Listos en {SALIDA.resolve()}")
    print("El resultado se aplica con  python scripts/aplicar_auditoria.py --commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
