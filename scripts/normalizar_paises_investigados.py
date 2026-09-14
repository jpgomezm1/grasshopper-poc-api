"""Normaliza `programas_investigados.pais` · el país es la faceta que más pesa.

El problema
-----------
La columna tiene **32 valores distintos para ~22 países**, porque cada tanda de
extracción escribió el país como lo decía el sitio: `UK` y `Reino Unido`, `USA`
y `Estados Unidos`, `Canada` y `Canadá`, `Spain` y `España`. Para un estudiante
que elige destino —que es la primera decisión que toma— eso parte cada país en
dos filtros con la mitad de los programas cada uno.

Y **4.069 programas (12%) no tienen país en absoluto**: son 22 instituciones
cuya ficha llegó con `country` vacío en el Excel del cliente.

Qué hace, y con qué evidencia
-----------------------------
1. **Normaliza** lo que ya está, con `app/services/lugares.py` — que es la
   fuente de verdad que ya cruza los dos catálogos, devuelve ISO, y distingue
   "esto no es un país" de "esto no lo conozco". No se introduce un cuarto
   vocabulario: ya existen `lugares.py`, `paises.py` y el `COUNTRY_MAP` de
   `scripts/import_institutions.py`.

2. **Rellena los nulos** con una tabla explícita institución por institución
   (abajo), revisada a mano. No es una regla: 21 de las 22 son dominios `.edu`,
   pero aplicar "`.edu` → Estados Unidos" a ciegas habría mandado los 131
   programas de Heriot-Watt al país equivocado. Es el mismo criterio que
   `areas.py:14-20` justifica para su mapa de áreas — una regla que acierta el
   90% deja un 10% mal que nadie va a revisar.

3. **Resuelve por fila** las instituciones multi-campus, donde el país no es de
   la institución sino de cada programa. Hoy sólo Heriot-Watt: su `ciudad` es
   la cadena literal `"Malaysia, Dubai, Edinburgh"` en las 131 filas, inútil
   como ciudad, pero **la ruta de la URL sí lo dice** (`/dubai/`, `/malaysia/`,
   y el resto Edimburgo). 63 Reino Unido · 62 Emiratos · 6 Malasia.

Lo que NO hace
--------------
No inventa. Lo que no reconoce lo deja como está y lo reporta, para que un valor
nuevo salte a la vista en vez de desaparecer. Y lo que quede nulo **no se
esconde**: la faceta de país debe mostrarlo como "Sin país registrado" con su
conteo. Doce por ciento del catálogo desapareciendo sin aviso es peor que una
etiqueta fea.

`International` y `Varios destinos` se conservan intactos a propósito: no son
países, y `busqueda_programas._where()` trata `Varios destinos` como caso
especial (lo incluye siempre, porque son instituciones con sedes en varios
países y excluirlas de un filtro por país sería mentir por omisión).

Uso
---
    python scripts/normalizar_paises_investigados.py            # simulacro
    python scripts/normalizar_paises_investigados.py --commit
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from typing import Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.services import lugares  # noqa: E402


# ── Los nulos · una fila por institución, revisada ──────────────────────────
#
# La evidencia de cada una es su dominio: 21 son `.edu`, que en Estados Unidos
# está restringido a instituciones acreditadas allí. Se escriben explícitas y no
# como regla para que se pueda revisar y para que la que NO cumple la regla
# (Heriot-Watt, más abajo) no pase desapercibida.
PAIS_POR_INSTITUCION: Dict[str, str] = {
    "Stony Brook University": "Estados Unidos",
    "University of Kansas": "Estados Unidos",
    "University of South Carolina": "Estados Unidos",
    "Tulane University": "Estados Unidos",
    "Louisiana State University": "Estados Unidos",
    "American University": "Estados Unidos",
    "University of Dayton": "Estados Unidos",
    "Belmont University": "Estados Unidos",
    "University at Buffalo": "Estados Unidos",
    "University of Nevada, Reno": "Estados Unidos",
    "University of Central Florida": "Estados Unidos",
    "Auburn University": "Estados Unidos",
    "Adelphi University": "Estados Unidos",
    "Cleveland State University": "Estados Unidos",
    "The University of Texas at San Antonio": "Estados Unidos",
    "University of Utah": "Estados Unidos",
    "University of Wyoming": "Estados Unidos",
    "Gonzaga University": "Estados Unidos",
    "University of the Pacific": "Estados Unidos",
    "Johns Hopkins University": "Estados Unidos",
    "Robert Morris University": "Estados Unidos",
}

# ── Multi-campus · el país es del programa, no de la institución ────────────
#
# Clave: institución → lista de (patrón en la url, país). Se evalúa en orden y
# gana el primero que coincide; el último es el campus por defecto.
POR_URL = {
    "Heriot-Watt University": [
        (r"hw\.ac\.uk/dubai/", "Emiratos Árabes Unidos"),
        (r"hw\.ac\.uk/malaysia/", "Malasia"),
        (r"", "Reino Unido"),  # Edimburgo · el resto del sitio
    ],
}


def _pais_por_url(institucion: str, url: Optional[str]) -> Optional[str]:
    reglas = POR_URL.get(institucion)
    if not reglas:
        return None
    for patron, pais in reglas:
        if not patron or re.search(patron, url or ""):
            return pais
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Normaliza el país de los programas")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()

    # ── 1 · normalizar lo que ya está ───────────────────────────────────────
    cambios: Dict[str, str] = {}
    ya_canonicos: Counter = Counter()
    no_son_paises: Counter = Counter()
    desconocidos: Counter = Counter()
    for r in db.execute(
        text("select pais, count(*) n from programas_investigados "
             "where pais is not null group by 1")
    ):
        crudo, n = r[0], r[1]
        canon = lugares.pais_canonico(crudo)
        if canon is None:
            if lugares.es_pais_desconocido(crudo):
                desconocidos[crudo] += n
            else:
                no_son_paises[crudo] += n  # `International`, `Varios destinos`
        elif canon.nombre != crudo:
            cambios[crudo] = canon.nombre
        else:
            ya_canonicos[crudo] += n

    # ── 2 · los nulos ───────────────────────────────────────────────────────
    sin_pais = list(db.execute(text(
        "select id, institucion, url_fuente from programas_investigados "
        "where activo and pais is null"
    )))
    resueltos: Counter = Counter()
    irresolubles: Counter = Counter()
    asignaciones = []
    for pid, inst, url in sin_pais:
        pais = _pais_por_url(inst, url) or PAIS_POR_INSTITUCION.get(inst)
        if pais:
            asignaciones.append((pid, pais))
            resueltos[f"{inst[:34]} -> {pais}"] += 1
        else:
            irresolubles[inst] += 1

    # ── informe ─────────────────────────────────────────────────────────────
    print("=" * 72)
    print("NORMALIZACION DE PAIS ·", "APLICA" if args.commit else "SIMULACRO")
    print("=" * 72)
    print(f"Valores a unificar : {len(cambios)}")
    for viejo, nuevo in sorted(cambios.items()):
        print(f"    {viejo:<34} -> {nuevo}")
    print()
    print(f"Ya canonicos       : {len(ya_canonicos)} valores, "
          f"{sum(ya_canonicos.values())} programas")
    print(f"No son paises      : {dict(no_son_paises) if no_son_paises else '(ninguno)'} "
          f"<- se conservan a proposito")
    if desconocidos:
        print("\n  ⚠ NO RECONOCIDOS · hay que ampliar lugares.py:")
        for v, n in desconocidos.most_common():
            print(f"    {n:6}  {v!r}")
    print()
    print(f"Programas sin pais  : {len(sin_pais)}")
    print(f"  se resuelven      : {sum(resueltos.values())}")
    for k, n in resueltos.most_common(30):
        print(f"      {n:5}  {k}")
    if irresolubles:
        print(f"  SIN RESOLVER      : {sum(irresolubles.values())}")
        for k, n in irresolubles.most_common(10):
            print(f"      {n:5}  {k}")

    if not args.commit:
        print("\nSIMULACRO · no se escribio nada. Repetir con --commit.")
        db.close()
        return 0

    n_norm = 0
    for viejo, nuevo in cambios.items():
        n_norm += db.execute(
            text("update programas_investigados set pais = :n where pais = :v"),
            {"n": nuevo, "v": viejo},
        ).rowcount or 0

    # Las asignaciones van por lote y no fila a fila: son 4.069 y una consulta
    # por fila contra Neon tarda minutos.
    n_asig = 0
    por_pais: Dict[str, list] = {}
    for pid, pais in asignaciones:
        por_pais.setdefault(pais, []).append(pid)
    for pais, ids in por_pais.items():
        for i in range(0, len(ids), 500):
            n_asig += db.execute(
                text("update programas_investigados set pais = :p "
                     "where id = any(cast(:ids as uuid[]))"),
                {"p": pais, "ids": ids[i:i + 500]},
            ).rowcount or 0
    db.commit()

    print(f"\nAPLICADO · {n_norm} filas unificadas · {n_asig} filas con pais nuevo.")
    restan = db.execute(text(
        "select count(*) from programas_investigados where activo and pais is null"
    )).scalar()
    print(f"Programas activos que siguen sin pais: {restan}")
    print(f"Valores distintos de pais ahora: "
          f"{db.execute(text('select count(distinct pais) from programas_investigados where activo')).scalar()}")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
