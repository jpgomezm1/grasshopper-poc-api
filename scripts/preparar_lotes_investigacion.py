"""Prepara los lotes de instituciones para que los investiguen subagents.

Por qué por agentes y no por API
--------------------------------
La versión por API (`investigar_programas.py`) funciona y quedó medida: ~240.000
tokens de entrada por institución, porque cada búsqueda inyecta el contenido de
las páginas al contexto. Eso son ~USD 0,85 por institución y ~USD 310 por las 363
pendientes, facturados como API. Los 15.483 programas que ya existen se hicieron
con agentes leyendo lotes, que es lo mismo sin esa factura.

Este script sólo arma los lotes; investigar lo hacen los agentes y cargar lo hace
`cargar_investigacion_agentes.py`. Tres pasos separados a propósito: si un agente
devuelve basura, se descarta su archivo sin tocar la base.

Uso
---
    python scripts/preparar_lotes_investigacion.py                    # todos los pendientes
    python scripts/preparar_lotes_investigacion.py --por-lote 8
    python scripts/preparar_lotes_investigacion.py --pais Australia --max-lotes 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402

SALIDA = Path("data/catalogo/lotes_agentes")


def dominio(website: Optional[str]) -> Optional[str]:
    if not website:
        return None
    s = website.strip()
    if not s:
        return None
    if "//" not in s:
        s = "https://" + s
    host = (urlparse(s).netloc or "").lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host or None


def ruta(website: Optional[str]) -> Optional[str]:
    """La ruta del catalogo, si la ficha la tiene.

    64 fichas la llevan, y es el resultado de la pasada de resolucion: distingue
    `lokmani.com/courses/law-programme/` de `/courses/postgraduate-programmes/`,
    acota `latrobe.edu.au/sydney` para que no se lleve la universidad entera, y
    separa las tres sedes de SAE. Pasarle al agente solo el host descartaria todo
    eso y volveria a producir los catalogos cruzados que la resolucion arreglo.
    """
    if not website:
        return None
    s = website.strip()
    if "//" not in s:
        s = "https://" + s
    p = urlparse(s)
    camino = (p.path or "").rstrip("/")
    if p.query:
        camino += "?" + p.query
    return camino or None


def pendientes(db, pais: Optional[str]) -> List[Dict[str, Any]]:
    """Autorizadas, con sitio, sin un programa investigado y sin veredicto.

    El `sin_oferta_vendible is null` es lo que impide que la cola se muerda la
    cola. Una ficha que se investigó y no dio nada vendible —Guildford no acepta
    solicitudes internacionales, Aspasia solo tiene formación subvencionada para
    desempleados— sigue teniendo cero programas, así que sin esta condición
    vuelve a entrar en cada tanda. Pasó: un lote completo de 8 agentes se gastó
    reconfirmando ocho callejones sin salida ya documentados en la bitácora.
    """
    sql = """
        select ic.name, ic.country, ic.city, ic.website, ic.niveles_autorizados,
               ic.category
        from institutions_catalog ic
        where ic.active
          and coalesce(ic.website, '') <> ''
          and ic.sin_oferta_vendible is null
          and not exists (
                select 1 from programas_investigados pi
                where lower(pi.institucion) = lower(ic.name)
          )
    """
    params: Dict[str, Any] = {}
    if pais:
        sql += " and ic.country = :pais"
        params["pais"] = pais
    # Las que declaran nivel primero: de esas sabemos qué se puede vender, así que
    # su resultado entra completo al catálogo en vez de a medias.
    sql += """
        order by (ic.niveles_autorizados is null
                  or ic.niveles_autorizados::text = '[]') asc,
                 ic.country, ic.name
    """
    filas = []
    for r in db.execute(text(sql), params):
        d = dominio(r[3])
        if not d:
            continue
        filas.append(
            {
                "institucion": r[0],
                "pais": r[1],
                "ciudad": r[2],
                "dominio": d,
                "ruta_catalogo": ruta(r[3]),
                "puede_vender": list(r[4] or []) or ["(el archivo del cliente no lo dice)"],
                "categoria": r[5],
            }
        )
    return filas


def main() -> int:
    ap = argparse.ArgumentParser(description="Arma los lotes para los subagents")
    ap.add_argument("--por-lote", type=int, default=8, help="Instituciones por lote")
    ap.add_argument("--max-lotes", type=int, help="Cuántos lotes generar (por defecto, todos)")
    ap.add_argument("--pais", help="Limitar a un país")
    ap.add_argument("--desde", type=int, default=1, help="Número del primer lote")
    args = ap.parse_args()

    db = SessionLocal()
    filas = pendientes(db, args.pais)
    db.close()

    SALIDA.mkdir(parents=True, exist_ok=True)
    lotes = [filas[i : i + args.por_lote] for i in range(0, len(filas), args.por_lote)]
    if args.max_lotes:
        lotes = lotes[: args.max_lotes]

    print(f"Instituciones pendientes con sitio : {len(filas)}")
    print(f"Lotes de {args.por_lote}                       : {len(lotes)}")
    print()
    for n, lote in enumerate(lotes, start=args.desde):
        ruta = SALIDA / f"lote_{n:02d}.json"
        ruta.write_text(
            json.dumps({"lote": f"{n:02d}", "instituciones": lote}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paises = sorted({x["pais"] or "?" for x in lote})
        print(f"  {ruta}  ·  {len(lote)} instituciones  ·  {', '.join(paises)}")

    print()
    print(f"Listos en {SALIDA.resolve()}")
    print("Cada lote lo toma un subagent · el resultado se carga con")
    print("  python scripts/cargar_investigacion_agentes.py --commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
