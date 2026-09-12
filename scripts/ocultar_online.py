"""Oculta los programas 100% online · no habilitan visa de estudiante.

Por qué
-------
El producto le recomienda programas a un estudiante colombiano que va a viajar.
Un programa 100% online se matricula sin problema, pero **no emite I-20 ni CAS**,
así que no da visa de estudio y la agencia no lo coloca. Recomendarlo es el mismo
error que recomendar un curso cerrado a internacionales.

Los agentes lo venían aplicando de forma desigual: unos lotes excluían el online
en la extracción y otros lo dejaban entrar. Esto empareja lo que ya está cargado;
la regla para lo que falta está en `PROMPT_AGENTES.md`.

La trampa que evita
-------------------
`(Online and On Campus)` y `(Online or On Campus)` son el MISMO programa ofrecido
de las dos formas: se cursan presencialmente y son perfectamente vendibles. Un
regex sobre "online" a secas los escondería. Por eso la condición exige que NO
aparezca una modalidad presencial en el nombre.

No borra: pone `activo = false`. Si la agencia decide vender online, se revierte
con un update y el dato sigue ahí.

Idempotente, y hay que re-correrlo después de cada `import_catalogo_autorizado`,
porque ese script recalcula `activo` solo a partir de los niveles autorizados.

Uso
---
    python scripts/ocultar_online.py            # simulacro
    python scripts/ocultar_online.py --commit
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402

# La segunda rama es la que cierra el hueco que encontro el agente del comp_09:
# 17 programas de York viven en `online.york.ac.uk`, un SUBDOMINIO del dominio
# oficial, asi que la comprobacion de dominio del cargador los acepta — y son
# 100% online. Lo mismo con `online.utoledo.edu` y `online.txst.edu`. Mirar solo
# el nombre no los veia: se llaman "MSc Computer Science", sin mas.
#
# Sigue exigiendo que el nombre no mencione una modalidad presencial, por la
# trampa de siempre: `(Online and On Campus)` es el mismo programa de las dos
# formas y SI se vende.
ES_ONLINE = r"""
        (nombre ~* '(^|[^a-z])(online|en linea)([^a-z]|$)'
         or nombre ~* 'distance (learning|education)'
         or nombre ~* '(a distancia|semipresencial)'
         or url_fuente ~* '://(www\.)?(online|onlinedegrees|onlinelearning|ecampus|distance)\.'
         or url_fuente ~* '/(study-online|online-degrees|online-programs)/')
    and nombre !~* '(on.?campus|presencial|blended|hybrid|hyflex)'
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Oculta los programas 100% online")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    a_ocultar = db.execute(
        text(f"select count(*) from programas_investigados where activo and {ES_ONLINE}")
    ).scalar()
    conservados = db.execute(
        text(
            "select count(*) from programas_investigados where activo "
            "and nombre ~* '(^|[^a-z])online([^a-z]|$)' "
            "and nombre ~* '(on.?campus|presencial|blended|hybrid|hyflex)'"
        )
    ).scalar()

    print("=" * 64)
    print("OCULTAR ONLINE ·", "APLICA" if args.commit else "SIMULACRO")
    print("=" * 64)
    print(f"Online sin alternativa presencial : {a_ocultar}  <- se ocultan")
    print(f"Online CON alternativa presencial : {conservados}  <- se conservan")

    for r in db.execute(
        text(
            f"select institucion, count(*) c from programas_investigados "
            f"where activo and {ES_ONLINE} group by 1 order by 2 desc limit 10"
        )
    ):
        print(f"    {r[1]:4}  {r[0][:52]}")

    if not args.commit:
        print("\nSIMULACRO · no se escribio nada. Repetir con --commit.")
        db.close()
        return 0

    n = db.execute(
        text(f"update programas_investigados set activo = false where activo and {ES_ONLINE}")
    ).rowcount
    db.commit()
    visibles = db.execute(
        text("select count(*) from programas_investigados where activo")
    ).scalar()
    print(f"\nAPLICADO · {n} ocultados. Programas visibles ahora: {visibles}")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
