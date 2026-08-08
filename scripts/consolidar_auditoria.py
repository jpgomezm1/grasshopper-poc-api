"""Consolida los lotes de auditoría del catálogo en un veredicto por institución.

Los agentes escriben `data/catalogo/auditoria/lote_NN.txt` (una línea por
institución, campos separados por ` | `). Esto los junta, clasifica cada ficha
por gravedad y produce el archivo que se le lleva a la clienta.

    python scripts/consolidar_auditoria.py

Salidas en `data/catalogo/`:
  · auditoria_consolidada.csv   · una fila por institución, con veredicto
  · AUDITORIA_CATALOGO.md       · el informe legible

**El veredicto es lo que decide qué se puede usar.** No es una nota de calidad:
`inservible` significa que extraer programas de esa ficha produciría información
falsa —una institución que no existe en ese dominio, un sitio muerto, una
agencia que no dicta nada— y que hay que corregirla o darla de baja antes de
cualquier enriquecimiento.
"""
from __future__ import annotations

import csv
import glob
import os
import re
from collections import Counter

RAIZ = os.path.join(os.path.dirname(__file__), "..", "data", "catalogo")
AUD = os.path.join(RAIZ, "auditoria")

CAMPOS = [
    "institucion", "dominio_responde", "dominio_real", "nombre_real",
    "nombre_coincide", "url_programas", "cantidad", "niveles", "tipo", "alerta",
]


def _clasificar(f: dict) -> tuple:
    """(veredicto, motivo) · el orden de las comprobaciones es el de gravedad."""
    resp = f["dominio_responde"].lower()
    alerta = f["alerta"].lower()
    tipo = f["tipo"].lower()

    if "cerr" in alerta or "ceased" in alerta:
        return "inservible", "la institución cerró"
    if resp.startswith("no"):
        return "inservible", "dominio muerto"
    if "fantasma" in alerta or "no menciona" in alerta or "no aparece" in alerta:
        return "inservible", "el dominio es de otra institución"
    if tipo in ("agencia", "red"):
        return "inservible", f"no es una institución ({tipo})"
    if "duplicad" in alerta:
        return "inservible", "duplicado de otra ficha"
    if "holding" in alerta or "del grupo" in alerta or "paraguas" in alerta:
        return "corregir", "apunta al dominio del grupo, no al propio"
    if "convenio" in alerta and "termin" in alerta:
        return "inservible", "el convenio terminó"
    if resp.startswith("redirige"):
        return "corregir", "dominio obsoleto"
    if f["nombre_coincide"].lower() in ("no", "parcial"):
        return "corregir", "nombre distinto al real"
    if resp.startswith("bloquea") or "bloquea" in alerta:
        return "revisar_a_mano", "el sitio bloquea acceso automatizado"
    if "?" in f["cantidad"] or "buscador" in alerta or "configurador" in alerta:
        return "revisar_a_mano", "catálogo no enumerable"
    if alerta and alerta != "-":
        return "observacion", f["alerta"][:120]
    return "ok", "-"


def main() -> int:
    filas = []
    lotes = sorted(glob.glob(os.path.join(AUD, "lote_*.txt")))
    for ruta in lotes:
        lote = re.search(r"lote_(\d+)", ruta).group(1)
        for linea in open(ruta, encoding="utf-8"):
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            partes = [x.strip() for x in linea.split("|")]
            if len(partes) < len(CAMPOS):
                continue
            f = dict(zip(CAMPOS, partes[: len(CAMPOS)]))
            f["lote"] = lote
            f["veredicto"], f["motivo"] = _clasificar(f)
            filas.append(f)

    if not filas:
        print("No hay lotes auditados todavía.")
        return 1

    salida_csv = os.path.join(RAIZ, "auditoria_consolidada.csv")
    with open(salida_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["lote", "veredicto", "motivo"] + CAMPOS)
        w.writeheader()
        w.writerows(filas)

    cuenta = Counter(f["veredicto"] for f in filas)
    total = len(filas)
    orden = ["inservible", "corregir", "revisar_a_mano", "observacion", "ok"]

    def pct(n):
        return round(100 * n / total)

    lineas = [
        "# Auditoría del catálogo de instituciones",
        "",
        f"**{total} instituciones auditadas** de las 630 con sitio propio "
        f"(el catálogo completo son 2.511 filas, todas a nivel institución).",
        "",
        "Cada ficha se visitó **sólo en su dominio oficial**. Ver "
        "`README.md` para por qué eso no es opcional.",
        "",
        "## Veredicto",
        "",
        "| Veredicto | Fichas | % | Qué significa |",
        "|---|---:|---:|---|",
    ]
    QUE_SIGNIFICA = {
        "inservible": "**No se puede usar.** Extraer de aquí produce información falsa",
        "corregir": "Usable después de arreglar el dominio o el nombre",
        "revisar_a_mano": "Necesita ojos humanos: bloquea bots o su catálogo no es una lista",
        "observacion": "Usable, con un detalle que conviene mirar",
        "ok": "Sin observaciones",
    }
    for v in orden:
        if cuenta.get(v):
            lineas.append(
                f"| `{v}` | {cuenta[v]} | {pct(cuenta[v])}% | {QUE_SIGNIFICA[v]} |"
            )

    lineas += ["", "## Por qué cada una quedó inservible", ""]
    for motivo, n in Counter(
        f["motivo"] for f in filas if f["veredicto"] == "inservible"
    ).most_common():
        lineas.append(f"- **{motivo}** · {n}")

    lineas += [
        "",
        "## Las inservibles, una por una",
        "",
        "| Institución en la ficha | Motivo | Detalle |",
        "|---|---|---|",
    ]
    for f in filas:
        if f["veredicto"] == "inservible":
            lineas.append(
                f"| {f['institucion']} | {f['motivo']} | {f['alerta'][:110]} |"
            )

    lineas += [
        "",
        "---",
        "",
        "El detalle completo, institución por institución, está en "
        "`auditoria_consolidada.csv`.",
    ]

    salida_md = os.path.join(RAIZ, "AUDITORIA_CATALOGO.md")
    open(salida_md, "w", encoding="utf-8").write("\n".join(lineas) + "\n")

    # ASCII en los prints: la consola de Windows es cp1252 y revienta con
    # flechas o puntos medios · los archivos de salida sí van en UTF-8.
    print(f"{total} instituciones en {len(lotes)} lotes")
    for v in orden:
        if cuenta.get(v):
            print(f"  {v:<16} {cuenta[v]:>4}  ({pct(cuenta[v])}%)")
    print(f"\n  -> {salida_csv}\n  -> {salida_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
