"""Reconecta programas huérfanos con la ficha que les corresponde.

El problema
-----------
`programas_investigados.institucion` guarda el NOMBRE, no el id de la ficha.
Cuando el Excel del cliente reemplazó el catálogo, muchas instituciones llegaron
escritas apenas distinto —`University of East Anglia (UEA)` pasó a `University
of East Anglia`, `Florida Atlantic University` a `FAU - Florida Atlantic
University`— y sus programas quedaron sin ficha: invisibles, y además fuera de
la cola de investigación, así que los agentes los volvieron a extraer desde cero
y con el tope de 150 se entregó menos de lo que ya había en la base.

UEA es el caso claro: 750 programas de agosto colgando de un nombre viejo, y una
re-extracción de 150 colgando del nuevo.

Qué hace
--------
Reescribe `institucion` al nombre exacto de la ficha activa, y recalcula
`activo` con los niveles que esa ficha autoriza. Sólo cuando la clave relajada
apunta a **una sola** institución; los ambiguos se listan y no se tocan.

No inventa fichas ni fusiona por parecido: `clave_relajada` son cuatro reglas
deterministas y exige que la sigla vaya en mayúsculas, justamente para no
confundir `(UEA)` con `(Sydney)`.

Uso
---
    python scripts/reconectar_huerfanos.py            # simulacro
    python scripts/reconectar_huerfanos.py --commit
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from scripts.import_catalogo_autorizado import (  # noqa: E402
    NIVEL_AUTORIZADO_A_INVESTIGADO,
    clave_nombre,
    clave_relajada,
)

SALIDA = Path("data/catalogo/revision")

# ── Alias verificados a mano ────────────────────────────────────────────────
#
# Pares que SON la misma institución y que `clave_relajada` se niega a cruzar,
# con razón: la regla es determinista a propósito y aflojarla hasta que cruzaran
# estos casos también cruzaría cosas distintas.
#
# Clave y valor van por `clave_nombre`. Se agrega sólo lo comprobado.
ALIAS_VERIFICADOS = {
    # El Excel del cliente reemplazó la ficha vieja por una con la sigla
    # delante; la vieja quedó inactiva y sus 509 programas siguieron activos
    # apuntando a una ficha muerta. Resultado: la misma universidad dos veces
    # en el catálogo, con dos listas de programas distintas. Se diferencian en
    # un "of" (`...University Belfast` vs `...University Of Belfast`).
    clave_nombre("Queen's University Belfast"):
        "QUB - The Queen’s University Of Belfast",
}


def _permitidos(autorizados) -> set:
    """Mismo criterio que el cargador: vacío = falta el dato = no se muestra."""
    autorizados = list(autorizados or [])
    if "todos" in autorizados:
        return set()
    out: set = set()
    for n in autorizados:
        out.update(NIVEL_AUTORIZADO_A_INVESTIGADO.get(n, ()))
    return out or {"__ninguno__"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconecta programas huérfanos con su ficha")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()

    exactas = set()
    por_relajada: Dict[str, List[tuple]] = defaultdict(list)
    for r in db.execute(
        text("select name, niveles_autorizados from institutions_catalog where active")
    ):
        exactas.add(clave_nombre(r[0]))
        por_relajada[clave_relajada(r[0])].append((r[0], r[1]))

    huerfanos = list(
        db.execute(
            text(
                """
                select pi.institucion, count(*)
                  from programas_investigados pi
                  left join institutions_catalog ic
                         on lower(ic.name) = lower(pi.institucion) and ic.active
                 where ic.id is null
                 group by 1 order by 2 desc
                """
            )
        )
    )

    reconectar, ambiguos, sin_ficha = [], [], []
    for nombre, n in huerfanos:
        # Un alias verificado manda sobre la clave relajada. La clave es
        # deliberadamente estricta y hace bien en no cruzar
        # `Queen's University Belfast` con `QUB - The Queen's University Of
        # Belfast` —se diferencian en un "of", y ablandarla hasta que cruzaran
        # metería `Loyola University` con `Lynn University`—. Lo que se afloja
        # es el caso concreto, revisado, no la regla.
        alias = ALIAS_VERIFICADOS.get(clave_nombre(nombre))
        if alias:
            hit = [c for c in por_relajada.get(clave_relajada(alias), [])
                   if clave_nombre(c[0]) == clave_nombre(alias)]
            if hit:
                reconectar.append((nombre, n, hit[0][0], hit[0][1]))
                continue
        cand = por_relajada.get(clave_relajada(nombre), [])
        if len(cand) == 1:
            reconectar.append((nombre, n, cand[0][0], cand[0][1]))
        elif cand:
            ambiguos.append((nombre, n, [c[0] for c in cand]))
        else:
            sin_ficha.append((nombre, n))

    tot = lambda L: sum(x[1] for x in L)  # noqa: E731
    print("=" * 72)
    print("RECONEXION DE HUERFANOS ·", "APLICA" if args.commit else "SIMULACRO")
    print("=" * 72)
    print(f"Se reconectan   : {len(reconectar):3} instituciones · {tot(reconectar):6} programas")
    print(f"Ambiguos        : {len(ambiguos):3} instituciones · {tot(ambiguos):6} programas  <- sin tocar")
    print(f"Sin ficha alguna: {len(sin_ficha):3} instituciones · {tot(sin_ficha):6} programas  <- sin tocar")
    print()
    for nombre, n, real, _ in reconectar[:20]:
        print(f"  {n:5}  '{nombre[:42]}'  ->  '{real[:42]}'")
    if len(reconectar) > 20:
        print(f"  ... y {len(reconectar) - 20} mas")

    SALIDA.mkdir(parents=True, exist_ok=True)
    with open(SALIDA / "huerfanos_sin_ficha.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["institucion_en_los_programas", "programas", "estado"])
        for nombre, n in sin_ficha:
            w.writerow([nombre, n, "no esta en el Excel del cliente"])
        for nombre, n, cands in ambiguos:
            w.writerow([nombre, n, "ambiguo: " + " | ".join(cands)])
    print(f"\nCSV: {(SALIDA / 'huerfanos_sin_ficha.csv').resolve()}")

    if not args.commit:
        print("\nSIMULACRO · no se escribio nada. Repetir con --commit.")
        db.close()
        return 0

    # Hay un indice unico `ux_prog_inv_institucion_nombre` sobre
    # (institucion, nombre) — un CREATE UNIQUE INDEX, que no figura en
    # pg_constraint. Por eso el choque hay que resolverlo ANTES del update: al
    # reconectar, los 750 de UEA de agosto se juntan con los 150 re-extraidos
    # esta semana y 145 nombres coinciden.
    #
    # Gana la fila que YA cuelga de la ficha buena: es la extraccion nueva, con
    # el filtro de elegibilidad internacional aplicado, que la de agosto no
    # tenia. Se borra la huerfana que chocaria.
    movidos = borrados = 0
    for nombre, _, real, niveles in reconectar:
        borrados += db.execute(
            text(
                """
                delete from programas_investigados v
                 where v.institucion = :viejo
                   and exists (
                         select 1 from programas_investigados n
                          where n.institucion = :real
                            and lower(n.nombre) = lower(v.nombre)
                   )
                """
            ),
            {"viejo": nombre, "real": real},
        ).rowcount or 0

        p = _permitidos(niveles)
        if not p:
            sql = ("update programas_investigados set institucion = :real, activo = true "
                   "where institucion = :viejo")
            params = {"real": real, "viejo": nombre}
        else:
            sql = ("update programas_investigados set institucion = :real, "
                   "activo = (nivel = any(:niv)) where institucion = :viejo")
            params = {"real": real, "viejo": nombre, "niv": list(p)}
        movidos += db.execute(text(sql), params).rowcount or 0
    db.commit()

    visibles = db.execute(
        text("select count(*) from programas_investigados where activo")
    ).scalar()
    print("")
    print(f"APLICADO · {movidos} programas reconectados.")
    print(f"Duplicados descartados  : {borrados}  (gana la extraccion nueva)")
    print(f"Programas visibles ahora: {visibles}")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
