"""Carga el catálogo investigado a la tabla `programas_investigados`.

    python scripts/cargar_programas_investigados.py            # simulacro
    python scripts/cargar_programas_investigados.py --confirm  # escribe

**Corre en seco por defecto.** El `.env` local apunta al mismo Neon que
producción, así que un script de carga que escriba sin pedirlo es un accidente
esperando ocurrir.

Lee `data/catalogo/programas_con_pais.csv`, normaliza país y área al vocabulario
del producto, y descarta lo que no pueda normalizar en vez de meterlo con un
valor inventado.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import uuid
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import ProgramaInvestigado  # noqa: E402
from app.services import areas as areas_mod  # noqa: E402
from app.services import paises as paises_mod  # noqa: E402

RAIZ = os.path.join(os.path.dirname(__file__), "..", "data", "catalogo")

# ---------------------------------------------------------------------------
# Redes que operan en varios países
# ---------------------------------------------------------------------------
# Cinco instituciones traen `pais: "International"` porque colocan estudiantes en
# varios destinos. Dos de ellas **sí dicen el país, en el nombre del programa**, y
# ahí sí se puede resolver sin inventar nada:
#
#   Sprachcaffe        "Curso estándar · Adultos Frankfurt (Alemania)"
#   Worldwide Internships  "Hospitalidad - AUSTRALIA"
#
# Las otras tres no: LSI y Educatius venden el mismo producto en muchos países y
# el nombre no lo dice ("General 20", "Classic High School Program"). Esas quedan
# como `Varios destinos`. Alpadia se resuelve por la ciudad de su ficha, que es
# una sola.
_PAIS_EN_PARENTESIS = re.compile(r"\(([^)]+)\)\s*$")
_PAIS_TRAS_GUION = re.compile(r"-\s*([A-ZÁÉÍÓÚÑ&\s]{3,})\s*$")

CIUDAD_A_PAIS = {"montreux": "Suiza"}


def _pais_del_nombre(nombre: str) -> str | None:
    """El país cuando el propio nombre del programa lo dice."""
    for patron in (_PAIS_EN_PARENTESIS, _PAIS_TRAS_GUION):
        m = patron.search(nombre or "")
        if m:
            p = paises_mod.normalizar(m.group(1))
            if p and p != paises_mod.VARIOS:
                return p
    return None


def _resolver_pais(fila: dict) -> str | None:
    p = paises_mod.normalizar(fila.get("pais"))
    if p and p != paises_mod.VARIOS:
        return p
    # Multi-destino · se intenta el nombre, luego la ciudad, y si no, se admite
    # como `Varios destinos`: es un dato honesto, no un hueco.
    return (
        _pais_del_nombre(fila.get("nombre", ""))
        or CIUDAD_A_PAIS.get((fila.get("ciudad") or "").strip().lower())
        or paises_mod.VARIOS
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true",
                    help="escribe en la base · sin esto sólo simula")
    ap.add_argument("--csv", default=os.path.join(RAIZ, "programas_con_pais.csv"))
    args = ap.parse_args()

    with open(args.csv, encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))

    listos, descartes = [], Counter()
    for f in filas:
        area = areas_mod.normalizar(f.get("area"))
        if not area:
            descartes[f"area sin mapear: {f.get('area')}"] += 1
            continue
        if not (f.get("nombre") or "").strip():
            descartes["sin nombre"] += 1
            continue
        listos.append(
            dict(
                id=uuid.uuid4(),
                institucion=f["institucion"][:255],
                nombre=f["nombre"][:500],
                pais=_resolver_pais(f),
                ciudad=(f.get("ciudad") or "")[:160] or None,
                nivel=f["nivel"],
                area=area,
                area_cruda=(f.get("area") or "")[:160] or None,
                duracion=(f.get("duracion") or "")[:120] or None,
                codigo_oficial=(
                    None if (f.get("codigo_oficial") or "-").strip() in ("-", "", "?")
                    else f["codigo_oficial"][:80]
                ),
                url_fuente=f.get("url_fuente") or None,
                dominio=(f.get("dominio") or "")[:160] or None,
                lote=(f.get("lote") or "")[:8] or None,
            )
        )

    print(f"filas en el CSV : {len(filas)}")
    print(f"listas para cargar: {len(listos)}")
    if descartes:
        print("descartadas:")
        for m, n in descartes.most_common(10):
            print(f"    {n:>5}  {m}")
    print("\npor pais:")
    for k, n in Counter(x["pais"] for x in listos).most_common():
        print(f"    {n:>5}  {k}")
    print("\npor area:")
    for k, n in Counter(x["area"] for x in listos).most_common():
        print(f"    {n:>5}  {k}")
    con_codigo = sum(1 for x in listos if x["codigo_oficial"])
    print(f"\ncon codigo oficial: {con_codigo} ({round(100*con_codigo/len(listos))}%)")

    if not args.confirm:
        print("\n--- SIMULACRO · nada se escribio. Repite con --confirm ---")
        return 0

    db = SessionLocal()
    try:
        previas = db.query(ProgramaInvestigado).count()
        if previas:
            print(f"\nla tabla ya tiene {previas} filas · se reemplazan")
            db.query(ProgramaInvestigado).delete()
        db.bulk_insert_mappings(ProgramaInvestigado, listos)
        db.commit()
        print(f"\ncargadas: {db.query(ProgramaInvestigado).count()}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
