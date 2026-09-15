"""Pasada 3 · resolución · arregla las fichas que la auditoría dejó rotas.

Por qué existe
-------------
La auditoría (pasada 1) diagnostica y corrige lo fácil: un dominio que redirige,
uno que faltaba. Lo que no resuelve son los casos donde hay que **decidir algo**:

  · `otra_institucion` · el dominio es de otra entidad. ¿Cuál es el real?
  · `dominio_muerto`   · ¿la institución cerró, o sólo el sitio bloquea?
  · `sin_catalogo`     · ¿no publica programas, o directamente no es una escuela?
  · dominio compartido · ¿son la misma ficha dos veces, o dos miembros de una red
                         que necesitan cada uno su subdominio?

Eso quedaba en un CSV para mandarle al cliente. Pero devolverle su archivo con
tareas es lento y es trabajo que podemos hacer nosotros: casi todo se resuelve
mirando el sitio, los registros oficiales (CRICOS, IPEDS, el registro de sponsors
del Reino Unido) y los avisos de cierre. Esta pasada lo hace.

Lo que NO toca, y es deliberado
-------------------------------
**`niveles_autorizados`.** Es el contrato de la agencia — qué le permiten vender
en cada institución. No se deduce del sitio: que una universidad tenga pregrado no
significa que la agencia pueda venderlo. Autorizar de más por nuestra cuenta le
haría prometer al estudiante algo que la agencia no puede entregar.

Y no hace falta tocarlo: si la ficha autoriza un nivel que la institución no
ofrece, no se extrae nada de ese nivel y la autorización queda inerte. Si autoriza
de menos, mostramos menos de lo vendible — que es el lado seguro del error.

Uso
---
    python scripts/preparar_lotes_resolucion.py
    python scripts/preparar_lotes_resolucion.py --por-lote 10
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from scripts.import_catalogo_autorizado import clave_nombre  # noqa: E402
from scripts.cargar_investigacion_agentes import _host  # noqa: E402

AUDITORIA = Path("data/catalogo/auditoria_agentes")
SALIDA = Path("data/catalogo/lotes_resolucion")


def main() -> int:
    ap = argparse.ArgumentParser(description="Arma los lotes de resolución")
    ap.add_argument("--por-lote", type=int, default=10)
    ap.add_argument("--max-lotes", type=int)
    args = ap.parse_args()

    # ── Lo que dijo la auditoría ────────────────────────────────────────────
    veredictos: Dict[str, dict] = {}
    for archivo in sorted(AUDITORIA.rglob("*.csv")):
        with open(archivo, encoding="utf-8-sig", newline="") as fh:
            for fila in csv.DictReader(fh):
                k = clave_nombre((fila.get("institucion") or "").strip())
                if k:
                    veredictos[k] = fila

    db = SessionLocal()
    fichas: Dict[str, dict] = {}
    por_dominio: Dict[str, List[str]] = defaultdict(list)
    for r in db.execute(
        text(
            "select name, country, city, website, category, niveles_autorizados "
            "from institutions_catalog where active"
        )
    ):
        k = clave_nombre(r[0])
        d = _host(r[3])
        fichas[k] = {
            "institucion": r[0],
            "pais": r[1],
            "ciudad": r[2],
            "dominio_actual": d,
            "categoria": r[4],
            "puede_vender": list(r[5] or []),
        }
        if d:
            por_dominio[d].append(k)
    db.close()

    casos: Dict[str, dict] = {}

    # ── Caso 1 · las que la auditoría marcó rotas ───────────────────────────
    for k, v in veredictos.items():
        estado = (v.get("estado") or "").strip().lower()
        if estado not in ("otra_institucion", "dominio_muerto", "sin_catalogo"):
            continue
        if k not in fichas:
            continue
        caso = dict(fichas[k])
        caso["motivo"] = estado
        caso["lo_que_vio_el_auditor"] = (v.get("nota") or "").strip() or None
        caso["dominio_que_propuso"] = (v.get("dominio_real") or "").strip() or None
        casos[k] = caso

    # ── Caso 2 · el dominio es un portal de pathway ─────────────────────────
    #
    # Ocho fichas de universidades grandes (UMass Amherst, Oklahoma, Texas State,
    # Thomas Jefferson...) apuntan a su portal `*.intostudy.com`.
    #
    # ⚠️ Ojo con el diagnostico, porque hay dos cosas distintas que se ven igual:
    #
    #   a) `/en/search` devuelve "0 results · No programs found" a un fetcher sin
    #      JavaScript. Eso NO prueba que el portal este vacio: estos sitios pintan
    #      el listado por JS y el HTML crudo solo trae la plantilla. Con navegador
    #      pueden tener catalogo. (Se concluyo "vacio" el 2026-09-10 y era
    #      prematuro · lo corrigio el auditor del lote 15.)
    #   b) Pero el portal, aun con catalogo, es el del PATHWAY: son 2-15 rutas de
    #      preparacion, no las 100-300 titulaciones de la universidad. Y en varios
    #      casos ni siquiera existe centro: `txst.intostudy.com` resuelve y da 404
    #      porque Texas State es "Direct Entry only Partner".
    #
    # Lo que hay que decidir es (b), que es una pregunta de producto: si la ficha
    # nombra la universidad, su dominio deberia ser el de la universidad; si nombra
    # el centro de pathway, el portal esta bien y el volumen esperado es pequeno.
    PORTALES_DE_PATHWAY = ("intostudy.com", "kaplanpathways.com", "studygroup.com")
    for k, f in fichas.items():
        d = f["dominio_actual"] or ""
        if not any(p in d for p in PORTALES_DE_PATHWAY):
            continue
        caso = casos.get(k) or dict(f)
        caso.setdefault("motivo", "portal_de_pathway")
        caso.setdefault(
            "lo_que_vio_el_auditor",
            "El dominio es un portal de pathway (INTO/Kaplan/Study Group). Dos avisos: "
            "(1) su listado se pinta por JavaScript, asi que un fetcher sin navegador ve "
            "'0 results' aunque haya catalogo — no concluyas que esta vacio sin render; "
            "(2) aunque tenga catalogo, es el del pathway: 2-15 rutas de preparacion, no "
            "las 100-300 titulaciones de la universidad. Decide si la ficha nombra la "
            "universidad (y entonces el dominio debe ser el suyo) o el centro de pathway "
            "(y el portal esta bien, con volumen esperado pequeno). Verifica que el centro "
            "exista: txst.intostudy.com resuelve pero da 404 porque no hay centro ahi.",
        )
        casos[k] = caso

    # ── Caso 3 · dominios que sirven a varias fichas ────────────────────────
    # Aquí está la decisión que ningún filtro puede tomar solo: `Speos` y
    # `Spéos, Paris Photographic Institute` son la misma escuela y hay que
    # fusionarlas; `navitas.com` en siete fichas son siete colleges distintos y
    # hay que darle a cada uno su subdominio. Se ven idénticos desde la base.
    for dominio, claves in por_dominio.items():
        if len(claves) < 2:
            continue
        for k in claves:
            if k not in fichas:
                continue
            caso = casos.get(k) or dict(fichas[k])
            caso.setdefault("motivo", "dominio_compartido")
            caso["comparte_dominio_con"] = [
                fichas[o]["institucion"] for o in claves if o != k and o in fichas
            ]
            v = veredictos.get(k) or {}
            caso.setdefault("lo_que_vio_el_auditor", (v.get("nota") or "").strip() or None)
            casos[k] = caso

    lista = sorted(casos.values(), key=lambda c: (c["pais"] or "", c["institucion"]))
    SALIDA.mkdir(parents=True, exist_ok=True)
    lotes = [lista[i : i + args.por_lote] for i in range(0, len(lista), args.por_lote)]
    if args.max_lotes:
        lotes = lotes[: args.max_lotes]

    motivos: Dict[str, int] = defaultdict(int)
    for c in lista:
        motivos[c["motivo"]] += 1

    print(f"Fichas a resolver : {len(lista)}")
    for m, n in sorted(motivos.items(), key=lambda x: -x[1]):
        print(f"    {n:5}  {m}")
    print(f"Lotes de {args.por_lote}       : {len(lotes)}")
    print()
    for n, lote in enumerate(lotes, start=1):
        ruta = SALIDA / f"res_{n:02d}.json"
        ruta.write_text(
            json.dumps({"lote": f"{n:02d}", "fichas": lote}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  {ruta}  ·  {len(lote)} fichas")

    print()
    print(f"Listos en {SALIDA.resolve()}")
    print("Se aplican con  python scripts/aplicar_resolucion.py --commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
