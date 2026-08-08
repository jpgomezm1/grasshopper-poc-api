"""Valida y consolida los programas extraídos por los subagents.

Los agentes escriben `data/catalogo/programas/ext_NN.txt` con una línea por
programa. Esto los junta, **rechaza lo que no se puede cargar** y produce el
CSV que después alimenta el catálogo.

    python scripts/validar_programas.py

Rechaza —no corrige en silencio— porque un programa mal formado que se cuela es
un dato que un asesor le va a leer a una familia. Es preferible perder la fila y
que quede contada en el informe.

Salidas en `data/catalogo/`:
  · programas_consolidados.csv
  · programas_rechazados.csv   · con el motivo de cada rechazo
"""
from __future__ import annotations

import csv
import glob
import os
import re
from collections import Counter

RAIZ = os.path.join(os.path.dirname(__file__), "..", "data", "catalogo")
DIR = os.path.join(RAIZ, "programas")

CAMPOS = ["institucion", "nombre", "nivel", "area", "duracion",
          "codigo_oficial", "url_fuente"]

# El mismo vocabulario que `VALID_PROGRAM_TYPES` · si divergen, el dato no carga.
NIVELES = {
    "secundaria", "pregrado", "bachelor", "maestria", "mba", "doctorado",
    "posgrado", "especializacion", "diplomado", "curso_corto", "vacacional",
    "intercambio", "bootcamp",
}

# Lo que NO puede aparecer en una fila · si un agente coló un precio, se rechaza.
_PRECIO = re.compile(
    r"(?:\b(?:AUD|USD|EUR|GBP|CAD|NZD|COP)\s*[\d.,]+|[$£€]\s*\d|\b\d[\d.,]*\s*(?:AUD|USD|EUR|GBP|CAD|NZD)\b)",
    re.I,
)


def main() -> int:
    ok, malas = [], []
    archivos = sorted(glob.glob(os.path.join(DIR, "ext_*.txt")))
    if not archivos:
        print("No hay extracciones todavía.")
        return 1

    for ruta in archivos:
        lote = re.search(r"ext_(\d+)", ruta).group(1)
        for n, linea in enumerate(open(ruta, encoding="utf-8"), 1):
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            # La fila de cabecera que algunos agentes repiten · no es un dato.
            if linea.lower().startswith("institucion |"):
                continue
            partes = [x.strip() for x in linea.split("|")]

            def rechazar(motivo):
                malas.append({"lote": lote, "linea": n, "motivo": motivo,
                              "contenido": linea[:180]})

            if len(partes) != len(CAMPOS):
                rechazar(f"tiene {len(partes)} columnas y deben ser {len(CAMPOS)}")
                continue
            f = dict(zip(CAMPOS, partes))
            f["lote"] = lote

            if f["nivel"].lower() not in NIVELES:
                rechazar(f"nivel '{f['nivel']}' fuera del vocabulario")
                continue
            if not f["nombre"] or len(f["nombre"]) < 3:
                rechazar("sin nombre de programa")
                continue
            if not f["institucion"]:
                rechazar("sin institución")
                continue
            if _PRECIO.search(linea):
                rechazar("contiene un precio · no se extraen precios")
                continue
            if f["url_fuente"] and not f["url_fuente"].lower().startswith("http"):
                rechazar(f"url_fuente no es una URL: {f['url_fuente'][:40]}")
                continue

            f["nivel"] = f["nivel"].lower()
            ok.append(f)

    # Duplicados exactos · misma institución y mismo nombre de programa
    vistos, unicos, dups = set(), [], 0
    for f in ok:
        clave = (f["institucion"].lower(), f["nombre"].lower())
        if clave in vistos:
            dups += 1
            malas.append({"lote": f["lote"], "linea": "-",
                          "motivo": "duplicado (misma institución y nombre)",
                          "contenido": f"{f['institucion']} | {f['nombre']}"[:180]})
            continue
        vistos.add(clave)
        unicos.append(f)

    with open(os.path.join(RAIZ, "programas_consolidados.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["lote"] + CAMPOS)
        w.writeheader()
        w.writerows(unicos)
    with open(os.path.join(RAIZ, "programas_rechazados.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["lote", "linea", "motivo", "contenido"])
        w.writeheader()
        w.writerows(malas)

    print(f"archivos: {len(archivos)}")
    print(f"programas validos : {len(unicos)}")
    print(f"rechazados        : {len(malas)}  (incluye {dups} duplicados)")
    if malas:
        print("\n  motivos de rechazo:")
        for m, n in Counter(x["motivo"] for x in malas).most_common(8):
            print(f"    {n:>5}  {m}")
    print(f"\ninstituciones con programas: {len(set(f['institucion'] for f in unicos))}")
    print("\n  por nivel:")
    for k, n in Counter(f["nivel"] for f in unicos).most_common():
        print(f"    {n:>5}  {k}")
    con_codigo = sum(1 for f in unicos if f["codigo_oficial"] not in ("-", "", "?"))
    print(f"\n  con codigo oficial verificable: {con_codigo} ({round(100*con_codigo/len(unicos))}%)")
    sin_area = sum(1 for f in unicos if f["area"] in ("-", "", "?"))
    print(f"  SIN area de estudio           : {sin_area}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
