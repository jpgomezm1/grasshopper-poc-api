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
que permite que el estudiante salte de un programa a la página de su
institución.

La solución es remapear por la **llave de negocio** (`programs.program_id`, el
slug estable del Excel), que sí es igual en las dos bases.

Qué NO se transfiere
--------------------
**Los embeddings.** Son 1.536 floats por fila y 48.768 filas: del orden de 300 MB
de texto por la red, desde una conexión doméstica. Regenerarlos en producción
cuesta USD 0,04 y veinte minutos, y el resultado es idéntico porque el texto que
se embebe viaja completo (incluida la glosa). El script lo recuerda al terminar.

Qué se reemplaza
----------------
`programas_investigados` entero. Producción tiene 15.483 filas del catálogo
anterior y la copia local (48.768) las supersede: incluye las mismas
instituciones ya reconciliadas, con el país normalizado, las fusiones aplicadas
y las bajas marcadas. **Nada referencia `programas_investigados.id`** —se
comprobó en el esquema— así que reemplazarlas no arrastra datos de ningún
estudiante.

`institutions_catalog` se inserta: en producción está vacía porque el Excel del
cliente nunca se importó allá.

Uso
---
    python scripts/publicar_catalogo.py                    # simulacro
    python scripts/publicar_catalogo.py --commit

La URL de producción sale de `heroku config:get DATABASE_URL`. No se imprime.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402

APP = "grasshopper-api"
LOTE = 500

#: Las columnas que se copian · `embedding` NO está (ver el docstring) y `id`
#: tampoco: se regenera en destino, porque nada lo referencia.
COLUMNAS_PROGRAMAS = (
    "institucion", "nombre", "pais", "ciudad", "nivel", "area", "area_cruda",
    "duracion", "codigo_oficial", "url_fuente", "dominio", "lote", "activo",
    "confianza", "glosa",
)

COLUMNAS_FICHAS = (
    "name", "category", "country", "country_raw", "city", "partner_group",
    "programs_offered", "niveles_autorizados", "prioridad", "agreement_status",
    "starting_date", "end_date", "contact_name", "contact_email", "website",
    "territories", "commissions", "source_sheet", "active", "raw",
    "sin_oferta_vendible",
)

#: Las que hay que serializar a JSON para que psycopg2 las acepte en un
#: `executemany` sobre columnas `json`.
JSON_FICHAS = {"programs_offered", "niveles_autorizados", "commissions", "raw"}


def _url_de_produccion() -> str:
    url = os.getenv("DATABASE_URL_PRODUCCION")
    if url:
        return url
    r = subprocess.run(
        ["heroku", "config:get", "DATABASE_URL", "--app", APP],
        capture_output=True, text=True, shell=True,
    )
    url = (r.stdout or "").strip()
    if not url:
        raise SystemExit("no se pudo leer DATABASE_URL de Heroku · ¿heroku login?")
    # SQLAlchemy 2 no acepta el esquema `postgres://` que devuelve Heroku.
    return url.replace("postgres://", "postgresql://", 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Publica el catalogo a produccion")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    local = SessionLocal()
    motor = create_engine(_url_de_produccion(), pool_pre_ping=True)

    with motor.connect() as prod:
        # ── El mapa de ids · la pieza que evita colgar cada programa de la
        #    institución equivocada ──────────────────────────────────────────
        ids_locales = {str(r[0]): r[1] for r in local.execute(
            text("select id, program_id from programs"))}
        ids_prod = {r[1]: str(r[0]) for r in prod.execute(
            text("select id, program_id from programs"))}

        antes = {
            "prog_prod": prod.execute(text(
                "select count(*) from programas_investigados")).scalar(),
            "fichas_prod": prod.execute(text(
                "select count(*) from institutions_catalog")).scalar(),
            "prog_local": local.execute(text(
                "select count(*) from programas_investigados")).scalar(),
            "fichas_local": local.execute(text(
                "select count(*) from institutions_catalog")).scalar(),
        }

        filas = list(local.execute(text(
            f"select id, program_id, {', '.join(COLUMNAS_PROGRAMAS)} "
            f"from programas_investigados")))

        remapeados = huerfanos = sin_ficha = 0
        programas: List[dict] = []
        for r in filas:
            d = dict(zip(COLUMNAS_PROGRAMAS, r[2:]))
            pid_local = str(r[1]) if r[1] else None
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
                    # inventa: el programa entra sin enlace, que es lo que ya
                    # pasa con los 708 de instituciones sin ficha.
                    huerfanos += 1
                    d["program_id"] = None
            programas.append(d)

        fichas = [dict(zip(COLUMNAS_FICHAS, r)) for r in local.execute(text(
            f"select {', '.join(COLUMNAS_FICHAS)} from institutions_catalog"))]

        print("=" * 72)
        print("PUBLICAR CATALOGO ·", "APLICA" if args.commit else "SIMULACRO")
        print("=" * 72)
        print(f"institutions_catalog : produccion {antes['fichas_prod']:6} "
              f"-> {len(fichas)}")
        print(f"programas_investigados: produccion {antes['prog_prod']:6} "
              f"-> {len(programas)}")
        print()
        print(f"  enlaces remapeados por llave de negocio : {remapeados}")
        print(f"  sin ficha ya en local (se conservan)    : {sin_ficha}")
        print(f"  ficha ausente en produccion             : {huerfanos}"
              f"{'  <- REVISAR' if huerfanos else ''}")

        if not args.commit:
            print("\nSIMULACRO · no se escribio nada. Repetir con --commit.")
            return 0

        # ── Respaldo antes de borrar ────────────────────────────────────────
        #
        # Este es el único paso de todo el despliegue que no se deshace solo, y
        # hacerlo reversible cuesta unos megas: 15.483 filas sin embeddings. El
        # respaldo NO lleva `embedding` por la misma razón que no se transfiere
        # —pesa cien veces más que el resto— y se regenera si hiciera falta.
        respaldo = os.path.join(
            os.path.dirname(__file__), "..", "data", "catalogo", "revision",
            f"respaldo_produccion_{__import__('datetime').date.today()}.json",
        )
        previas = [dict(r) for r in prod.execute(text(
            "select institucion, nombre, pais, ciudad, nivel, area, area_cruda, "
            "duracion, codigo_oficial, url_fuente, dominio, lote, activo, "
            "confianza, program_id::text from programas_investigados"
        )).mappings()]
        os.makedirs(os.path.dirname(respaldo), exist_ok=True)
        with open(respaldo, "w", encoding="utf-8") as fh:
            json.dump(previas, fh, ensure_ascii=False, default=str)
        print(f"  respaldo de las {len(previas)} filas previas: "
              f"{os.path.basename(respaldo)}")

        t = prod.begin()
        try:
            prod.execute(text("delete from institutions_catalog"))
            cols = ", ".join(COLUMNAS_FICHAS)
            marcas = ", ".join(f":{c}" for c in COLUMNAS_FICHAS)
            for i in range(0, len(fichas), LOTE):
                trozo = [
                    {k: (json.dumps(v) if k in JSON_FICHAS and v is not None else v)
                     for k, v in f.items()}
                    for f in fichas[i:i + LOTE]
                ]
                prod.execute(text(
                    f"insert into institutions_catalog ({cols}) values ({marcas})"
                ), trozo)
            print(f"  fichas insertadas: {len(fichas)}")

            prod.execute(text("delete from programas_investigados"))
            cols = ", ".join((*COLUMNAS_PROGRAMAS, "program_id"))
            marcas = ", ".join(
                f"cast(:{c} as uuid)" if c == "program_id" else f":{c}"
                for c in (*COLUMNAS_PROGRAMAS, "program_id"))
            for i in range(0, len(programas), LOTE):
                prod.execute(text(
                    f"insert into programas_investigados ({cols}) "
                    f"values ({marcas})"
                ), programas[i:i + LOTE])
                if (i // LOTE) % 20 == 0:
                    print(f"    {min(i + LOTE, len(programas))}/{len(programas)}")
            t.commit()
        except Exception:
            t.rollback()
            raise

        print(f"\nPUBLICADO · {len(fichas)} fichas · {len(programas)} programas.")
        print("\nFalta lo que NO viaja por la red:")
        print("  heroku run --app grasshopper-api python scripts/generar_embeddings.py")
        print("  (~20 min · USD 0,04 · reconstruye tambien el indice HNSW parcial)")
    local.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
