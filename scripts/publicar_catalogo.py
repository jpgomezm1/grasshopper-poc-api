"""Publica el catálogo de la base local a producción.

Por qué hace falta un script y no un `pg_dump`
----------------------------------------------
Las dos bases tienen las mismas tablas y **UUIDs distintos**. `programs` se
pobló en cada una por separado desde el Excel del cliente, y `Program.id` se
genera con `uuid4()`, así que la ficha `4life-college` es `d8177f07…` en
producción y `3af244e3…` en local.

`programas_investigados.program_id` apunta a esos UUIDs. Un volcado directo
llevaría los ids locales a producción, donde no existen: la carga fallaría por
la llave foránea, y si alguien la desactivara para que pasara, **cada programa
quedaría colgando de la institución equivocada o de ninguna**. Ese enlace es lo
que permite que el estudiante salte de un programa a la página de su institución.

La solución es remapear por la **llave de negocio** (`programs.program_id`, el
slug estable del Excel), que sí es igual en las dos bases.

Por qué `COPY` y no `INSERT`
----------------------------
El primer intento usaba `executemany` en lotes de 500. Contra Neon desde una
conexión doméstica son 98 ida-y-vuelta con toda la fila serializada en cada uno,
y se quedó **17 minutos en `idle in transaction` sin avanzar**: la base esperando
al cliente. `COPY` manda todo por un solo flujo.

Se usa el formato CSV de `COPY` y no el TSV por defecto. El TSV obliga a escapar
a mano tabuladores, saltos de línea y contrabarras, y la columna `raw` trae el
JSON crudo del Excel: una contrabarra mal escapada corre la fila entera y los
datos entran en la columna de al lado **sin que nada falle**.

Qué NO se transfiere
--------------------
**Los embeddings.** Son 1.536 floats por fila y 48.768 filas. Regenerarlos en
producción cuesta USD 0,04 y veinte minutos, y el resultado es idéntico porque el
texto que se embebe viaja completo, glosa incluida.

Qué se reemplaza
----------------
`programas_investigados` entero. Producción tiene 15.483 filas del catálogo
anterior y la copia local las supersede: las mismas instituciones reconciliadas,
con el país normalizado, las fusiones aplicadas y las bajas marcadas. **Nada
referencia `programas_investigados.id`** —comprobado en el esquema— así que
reemplazarlas no arrastra datos de ningún estudiante. Aun así se respalda antes:
es el único paso del despliegue que no se deshace solo.

Uso
---
    python scripts/publicar_catalogo.py                    # simulacro
    python scripts/publicar_catalogo.py --commit
"""
from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import os
import subprocess
import sys
import uuid
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402

APP = "grasshopper-api"

COLUMNAS_PROGRAMAS = (
    "id", "institucion", "nombre", "pais", "ciudad", "nivel", "area",
    "area_cruda", "duracion", "codigo_oficial", "url_fuente", "dominio", "lote",
    "activo", "confianza", "glosa", "program_id",
)

COLUMNAS_FICHAS = (
    "id", "name", "category", "country", "country_raw", "city", "partner_group",
    "programs_offered", "niveles_autorizados", "prioridad", "agreement_status",
    "starting_date", "end_date", "contact_name", "contact_email", "website",
    "territories", "commissions", "source_sheet", "active", "raw",
    "sin_oferta_vendible", "created_at", "updated_at",
)

#: Columnas `json` en el modelo · hay que serializarlas al escribir el CSV.
JSON_FICHAS = {"programs_offered", "niveles_autorizados", "commissions", "raw"}


def _url_de_produccion() -> str:
    url = os.getenv("DATABASE_URL_PRODUCCION")
    if not url:
        r = subprocess.run(
            ["heroku", "config:get", "DATABASE_URL", "--app", APP],
            capture_output=True, text=True, shell=True,
        )
        url = (r.stdout or "").strip()
    if not url:
        raise SystemExit("no se pudo leer DATABASE_URL de Heroku · ¿heroku login?")
    # SQLAlchemy 2 no acepta el esquema `postgres://` que devuelve Heroku.
    return url.replace("postgres://", "postgresql://", 1)


def _copiar(conexion, tabla: str, columnas, filas: List[dict],
            json_cols=frozenset()) -> int:
    """Carga masiva con `COPY ... FORMAT csv`.

    El `csv.writer` se encarga de comillas y escapes, que es justo lo que no
    conviene hacer a mano: el `raw` del Excel trae JSON con contrabarras y
    comillas, y un escape mal puesto corre la fila y mete cada valor en la
    columna de al lado **sin que nada falle**.
    """
    buffer = io.StringIO()
    w = csv.writer(buffer, lineterminator="\n")
    for f in filas:
        fila = []
        for c in columnas:
            v = f.get(c)
            if v is None:
                fila.append("")           # con FORCE_NULL se lee como NULL
            elif c in json_cols:
                fila.append(json.dumps(v))
            elif isinstance(v, bool):
                fila.append("true" if v else "false")
            else:
                fila.append(str(v))
        w.writerow(fila)
    buffer.seek(0)

    cols = ", ".join(columnas)
    # `FORCE_NULL` sobre todas: sin él una cadena vacía entra como '' y no como
    # NULL, y columnas como `ciudad` pasarían de "no sabemos" a "es vacío".
    crudo = conexion.connection.cursor()
    crudo.copy_expert(
        f"COPY {tabla} ({cols}) FROM STDIN "
        f"WITH (FORMAT csv, FORCE_NULL ({cols}))",
        buffer,
    )
    return len(filas)


def main() -> int:
    ap = argparse.ArgumentParser(description="Publica el catalogo a produccion")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    local = SessionLocal()
    motor = create_engine(_url_de_produccion(), pool_pre_ping=True)

    with motor.connect() as prod:
        # ── El mapa de ids · lo que evita colgar cada programa de la
        #    institución equivocada ──────────────────────────────────────────
        ids_locales = {str(r[0]): r[1] for r in local.execute(
            text("select id, program_id from programs"))}
        ids_prod = {r[1]: str(r[0]) for r in prod.execute(
            text("select id, program_id from programs"))}

        prog_prod = prod.execute(text(
            "select count(*) from programas_investigados")).scalar()
        fichas_prod = prod.execute(text(
            "select count(*) from institutions_catalog")).scalar()

        campos = [c for c in COLUMNAS_PROGRAMAS if c not in ("id", "program_id")]
        remapeados = huerfanos = sin_ficha = 0
        programas: List[dict] = []
        for r in local.execute(text(
                f"select program_id, {', '.join(campos)} "
                f"from programas_investigados")):
            d = dict(zip(campos, r[1:]))
            d["id"] = str(uuid.uuid4())
            pid_local = str(r[0]) if r[0] else None
            if pid_local is None:
                sin_ficha += 1
                d["program_id"] = None
            else:
                clave = ids_locales.get(pid_local)
                destino = ids_prod.get(clave) if clave else None
                if destino:
                    remapeados += 1
                    d["program_id"] = destino
                else:
                    # La ficha existe en local y no en producción. No se
                    # inventa: entra sin enlace, como los 708 de instituciones
                    # que nunca tuvieron ficha.
                    huerfanos += 1
                    d["program_id"] = None
            programas.append(d)

        campos_f = [c for c in COLUMNAS_FICHAS if c != "id"]
        fichas = []
        for r in local.execute(text(
                f"select {', '.join(campos_f)} from institutions_catalog")):
            d = dict(zip(campos_f, r))
            d["id"] = str(uuid.uuid4())
            fichas.append(d)

        print("=" * 72)
        print("PUBLICAR CATALOGO ·", "APLICA" if args.commit else "SIMULACRO")
        print("=" * 72)
        print(f"institutions_catalog  : produccion {fichas_prod:6} -> {len(fichas)}")
        print(f"programas_investigados: produccion {prog_prod:6} -> {len(programas)}")
        print()
        print(f"  enlaces remapeados por llave de negocio : {remapeados}")
        print(f"  sin ficha ya en local (se conservan)    : {sin_ficha}")
        print(f"  ficha ausente en produccion             : {huerfanos}"
              f"{'  <- REVISAR' if huerfanos else ''}")

        if not args.commit:
            print("\nSIMULACRO · no se escribio nada. Repetir con --commit.")
            return 0

        # ── Respaldo · el unico paso que no se deshace solo ──────────────────
        destino = os.path.join(
            os.path.dirname(__file__), "..", "data", "catalogo", "revision",
            f"respaldo_produccion_{datetime.date.today()}.json")
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        previas = [dict(r) for r in prod.execute(text(
            "select institucion, nombre, pais, ciudad, nivel, area, area_cruda, "
            "duracion, codigo_oficial, url_fuente, dominio, lote, activo, "
            "confianza, program_id::text from programas_investigados"
        )).mappings()]
        with open(destino, "w", encoding="utf-8") as fh:
            json.dump(previas, fh, ensure_ascii=False, default=str)
        print(f"\n  respaldo de las {len(previas)} filas previas: "
              f"{os.path.basename(destino)}")

        try:
            prod.execute(text("delete from programas_investigados"))
            prod.execute(text("delete from institutions_catalog"))
            n = _copiar(prod, "institutions_catalog", COLUMNAS_FICHAS, fichas,
                        JSON_FICHAS)
            print(f"  fichas copiadas   : {n}")
            n = _copiar(prod, "programas_investigados", COLUMNAS_PROGRAMAS,
                        programas)
            print(f"  programas copiados: {n}")
            prod.commit()
        except Exception:
            prod.rollback()
            raise

        print(f"\nPUBLICADO · {len(fichas)} fichas · {len(programas)} programas.")
        print("\nFalta lo que NO viaja por la red:")
        print("  heroku run --app grasshopper-api python scripts/generar_embeddings.py")
        print("  (~20 min · USD 0,04 · reconstruye tambien el indice HNSW parcial)")
    local.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
