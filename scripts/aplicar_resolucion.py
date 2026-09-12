"""Aplica la resolución · corrige, fusiona y desactiva fichas, con evidencia.

Es la única pasada que MODIFICA la identidad de una ficha, así que cada cambio
exige una razón escrita y ninguno borra nada.

Acciones que entiende
---------------------
  `corregir_dominio` · el sitio real es otro. Se actualiza `website`, y de paso
                       `name`/`city`/`category` si el agente los verificó. Es lo
                       que arregla `FIC - Simon Fraser University` (apuntaba a la
                       universidad y no a su pathway college) y `Whitecliffe`
                       (que la ficha ponía en Belfast y está en Berlín).
  `fusionar`         · dos fichas son la misma institución. La secundaria se
                       desactiva y sus `niveles_autorizados` se UNEN a los de la
                       principal — nunca se pierden: son el contrato de la agencia.
  `desactivar`       · no es una institución educativa, o cerró. `Coracle` vende
                       seguros, `Casa Toronto` es una residencia, `Ability - MEGT`
                       incumplió con sus estudiantes internacionales en 2021.
  `sin_cambio`       · el agente miró y no hay nada que corregir.

Lo que NUNCA hace
-----------------
**Tocar `niveles_autorizados` para ampliarlos.** Es el contrato de la agencia, no
un dato del sitio: que una universidad tenga pregrado no significa que la agencia
pueda venderlo. Sólo se unen al fusionar, que es conservar lo que ya estaba
autorizado en las dos fichas.

**Borrar filas.** Todo es `active=False`, reversible con un UPDATE.

Formato · `data/catalogo/resolucion_agentes/res_NN.csv`

    institucion,accion,dominio_real,nombre_real,ciudad_real,fusionar_con,evidencia

Uso
---
    python scripts/aplicar_resolucion.py            # simulacro
    python scripts/aplicar_resolucion.py --commit
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from scripts.import_catalogo_autorizado import clave_nombre  # noqa: E402
from scripts.cargar_investigacion_agentes import _host  # noqa: E402

ENTRADA = Path("data/catalogo/resolucion_agentes")
SALIDA = Path("data/catalogo/revision")

ACCIONES = ("corregir_dominio", "fusionar", "desactivar", "sin_cambio")
# `corregir_datos` no lo escribe el agente: lo deriva el aplicador cuando una
# fila `sin_cambio` trae ademas un nombre o una ciudad corregidos.
ACCIONES_APLICABLES = ("corregir_dominio", "corregir_datos", "fusionar", "desactivar")

# Sin una razón escrita no se aplica nada. Un cambio de identidad de una ficha
# que nadie puede explicar seis meses después es peor que la ficha rota.
MIN_EVIDENCIA = 20


def main() -> int:
    ap = argparse.ArgumentParser(description="Aplica la resolución de fichas")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--entrada", default=str(ENTRADA))
    args = ap.parse_args()

    archivos = sorted(Path(args.entrada).glob("*.csv"))
    if not archivos:
        print(f"No hay CSV en {Path(args.entrada).resolve()}")
        return 0

    db = SessionLocal()
    fichas: Dict[str, dict] = {}
    for r in db.execute(
        text(
            "select id, name, website, city, country, niveles_autorizados, raw "
            "from institutions_catalog where active"
        )
    ):
        fichas[clave_nombre(r[1])] = {
            "id": r[0],
            "nombre": r[1],
            "dominio": _host(r[2]),
            "ciudad": r[3],
            "pais": r[4],
            "niveles": list(r[5] or []),
            "raw": r[6] if isinstance(r[6], dict) else {},
        }

    planeadas: List[dict] = []
    descartes: Counter = Counter()

    for archivo in archivos:
        with open(archivo, encoding="utf-8-sig", newline="") as fh:
            for fila in csv.DictReader(fh):
                k = clave_nombre((fila.get("institucion") or "").strip())
                if k not in fichas:
                    descartes[f"ficha desconocida: {(fila.get('institucion') or '')[:36]}"] += 1
                    continue
                accion = (fila.get("accion") or "").strip().lower()
                if accion not in ACCIONES:
                    descartes[f"accion invalida: {accion or '(vacia)'}"] += 1
                    continue
                evidencia = (fila.get("evidencia") or "").strip()
                nombre_real = (fila.get("nombre_real") or "").strip() or None
                ciudad_real = (fila.get("ciudad_real") or "").strip() or None

                # `sin_cambio` significa "el dominio esta bien", no "no hay nada
                # que corregir": un agente puede confirmar el sitio y de paso
                # arreglar un nombre o una ciudad mal escritos ("Totonto"). Sin
                # esto se descartaba la fila entera y la correccion se perdia
                # — lo detecto el propio agente del lote 03.
                if accion == "sin_cambio":
                    if (nombre_real or ciudad_real) and len(evidencia) >= MIN_EVIDENCIA:
                        planeadas.append(
                            {
                                "clave": k,
                                "ficha": fichas[k],
                                "accion": "corregir_datos",
                                "dominio": None,
                                "nombre_real": nombre_real,
                                "ciudad_real": ciudad_real,
                                "destino": None,
                                "evidencia": evidencia,
                            }
                        )
                    else:
                        descartes["sin cambio"] += 1
                    continue
                if len(evidencia) < MIN_EVIDENCIA:
                    descartes[f"sin evidencia suficiente ({accion})"] += 1
                    continue

                destino_k = None
                if accion == "fusionar":
                    destino_k = clave_nombre((fila.get("fusionar_con") or "").strip())
                    if destino_k not in fichas:
                        descartes["fusionar_con apunta a una ficha que no existe"] += 1
                        continue
                    if destino_k == k:
                        descartes["fusionar consigo misma"] += 1
                        continue

                dominio = _host(fila.get("dominio_real"))
                if accion == "corregir_dominio" and not dominio:
                    descartes["corregir_dominio sin dominio"] += 1
                    continue

                # La ruta importa y hay que guardarla, no solo el host. Dos fichas
                # legitimas pueden compartir dominio y vivir en rutas distintas
                # (`lokmani.com/courses/law-programme/` y `/postgraduate-programmes/`).
                # Si solo guardaramos el host, la proxima auditoria las volveria a
                # marcar como duplicadas y la extraccion se llevaria el sitio entero
                # a las dos · lo detecto el agente del lote 04.
                ruta = (fila.get("ruta_catalogo") or "").strip()
                if ruta and not ruta.startswith("/"):
                    ruta = "/" + ruta

                planeadas.append(
                    {
                        "clave": k,
                        "ficha": fichas[k],
                        "accion": accion,
                        "dominio": dominio,
                        "ruta": ruta,
                        "nombre_real": nombre_real,
                        "ciudad_real": ciudad_real,
                        "destino": fichas[destino_k] if destino_k else None,
                        "evidencia": evidencia,
                    }
                )

    # ── Coherencia entre lotes ──────────────────────────────────────────────
    # Cada lote lo resuelve un agente distinto que NO ve los demas. Una fusion
    # apunta a una ficha que puede estar en otro lote, y si alla la desactivan o
    # la fusionan a su vez, el resultado es una cadena que deja programas
    # colgando de una ficha apagada. Se detecta aqui porque es el unico punto que
    # ve todos los veredictos juntos.
    accion_por_clave = {p["clave"]: p["accion"] for p in planeadas}
    coherentes: List[dict] = []
    for p in planeadas:
        if p["accion"] == "fusionar":
            destino_k = clave_nombre(p["destino"]["nombre"])
            destino_accion = accion_por_clave.get(destino_k)
            if destino_accion == "desactivar":
                descartes["fusionar hacia una ficha que otro lote desactiva"] += 1
                continue
            if destino_accion == "fusionar":
                descartes["cadena de fusiones (A->B->C)"] += 1
                continue
        coherentes.append(p)
    planeadas = coherentes

    conteo = Counter(p["accion"] for p in planeadas)
    print("=" * 72)
    print("RESOLUCION DE FICHAS ·", "APLICA" if args.commit else "SIMULACRO")
    print("=" * 72)
    print(f"Archivos leidos : {len(archivos)}")
    print(f"Cambios a aplicar: {len(planeadas)}")
    for a in ACCIONES_APLICABLES:
        if conteo.get(a):
            print(f"    {conteo[a]:5}  {a}")
    if descartes:
        print("\n  no se aplican:")
        for m, n in descartes.most_common(10):
            print(f"    {n:5}  {m}")
    print()

    for p in planeadas:
        origen = p["ficha"]["nombre"][:36]
        if p["accion"] == "fusionar":
            print(f"  FUSIONAR   {origen:38} -> {p['destino']['nombre'][:34]}")
        elif p["accion"] == "desactivar":
            print(f"  DESACTIVAR {origen:38}    {p['evidencia'][:44]}")
        elif p["accion"] == "corregir_datos":
            print(f"  DATOS      {origen:38} -> {p['nombre_real'] or p['ciudad_real']}")
        else:
            print(f"  DOMINIO    {origen:38} -> {p['dominio']}{p.get('ruta') or ''}")

    # Bitácora · qué se cambió y por qué. Es el documento que hace revisable un
    # cambio automático de identidad seis meses después.
    SALIDA.mkdir(parents=True, exist_ok=True)
    with open(SALIDA / "resolucion_aplicada.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "institucion", "accion", "dominio_anterior", "dominio_nuevo",
                "nombre_nuevo", "fusionada_con", "evidencia",
            ],
        )
        w.writeheader()
        for p in planeadas:
            w.writerow(
                {
                    "institucion": p["ficha"]["nombre"],
                    "accion": p["accion"],
                    "dominio_anterior": p["ficha"]["dominio"],
                    "dominio_nuevo": p["dominio"],
                    "nombre_nuevo": p["nombre_real"],
                    "fusionada_con": (p["destino"] or {}).get("nombre"),
                    "evidencia": p["evidencia"],
                }
            )
    print(f"\nBitacora: {(SALIDA / 'resolucion_aplicada.csv').resolve()}")

    if not args.commit:
        print("\nSIMULACRO · no se escribio nada. Repetir con --commit.")
        db.close()
        return 0

    for p in planeadas:
        f = p["ficha"]
        raw = dict(f["raw"] or {})
        historial = list(raw.get("_correcciones") or [])
        historial.append(
            {
                "accion": p["accion"],
                "evidencia": p["evidencia"],
                "dominio_anterior": f["dominio"],
                "dominio_nuevo": p["dominio"],
            }
        )
        raw["_correcciones"] = historial

        if p["accion"] == "corregir_datos":
            db.execute(
                text(
                    "update institutions_catalog set name = coalesce(:n, name), "
                    "city = coalesce(:c, city), raw = cast(:raw as jsonb), "
                    "updated_at = now() where id = :id"
                ),
                {
                    "n": p["nombre_real"],
                    "c": p["ciudad_real"],
                    "raw": json.dumps(raw, ensure_ascii=False, default=str),
                    "id": f["id"],
                },
            )
        elif p["accion"] == "corregir_dominio":
            db.execute(
                text(
                    "update institutions_catalog set website = :w, "
                    "name = coalesce(:n, name), city = coalesce(:c, city), "
                    "raw = cast(:raw as jsonb), updated_at = now() where id = :id"
                ),
                {
                    "w": "https://" + p["dominio"] + (p.get("ruta") or ""),
                    "n": p["nombre_real"],
                    "c": p["ciudad_real"],
                    "raw": json.dumps(raw, ensure_ascii=False, default=str),
                    "id": f["id"],
                },
            )
        elif p["accion"] == "desactivar":
            db.execute(
                text(
                    "update institutions_catalog set active = false, "
                    "raw = cast(:raw as jsonb), updated_at = now() where id = :id"
                ),
                {"raw": json.dumps(raw, ensure_ascii=False, default=str), "id": f["id"]},
            )
        elif p["accion"] == "fusionar":
            destino = p["destino"]
            # Los niveles se UNEN, no se pisan: son lo que la agencia tiene
            # autorizado, y perder uno al fusionar sería recortar su contrato.
            unidos = list(destino["niveles"])
            for n in f["niveles"]:
                if n not in unidos:
                    unidos.append(n)
            db.execute(
                text(
                    "update institutions_catalog set niveles_autorizados = cast(:n as jsonb), "
                    "updated_at = now() where id = :id"
                ),
                {"n": json.dumps(unidos), "id": destino["id"]},
            )
            db.execute(
                text(
                    "update institutions_catalog set active = false, "
                    "raw = cast(:raw as jsonb), updated_at = now() where id = :id"
                ),
                {"raw": json.dumps(raw, ensure_ascii=False, default=str), "id": f["id"]},
            )

    db.commit()
    print(f"\nAPLICADO · {len(planeadas)} fichas. Nada se borro: todo es active=false.")

    # ── Lo que quedo sin resolver ───────────────────────────────────────────
    # Un duplicado solo se deshace si UNA de las dos fichas marca `fusionar`. Si
    # los dos agentes que las vieron dijeron `sin_cambio` —cada uno creyendo que
    # el otro lo haria— el duplicado sobrevive y nadie se entera hasta la proxima
    # auditoria. Lo detecto el agente del lote 07, y solo se ve aqui: es el unico
    # punto que mira la base DESPUES de aplicar todos los lotes.
    restantes: Dict[str, List[str]] = {}
    for r in db.execute(
        text(
            "select name, website from institutions_catalog "
            "where active and coalesce(website,'') <> ''"
        )
    ):
        restantes.setdefault((r[1] or "").strip().lower(), []).append(r[0])
    pendientes = {d: n for d, n in restantes.items() if len(n) > 1}
    if pendientes:
        print(f"\nOJO · {len(pendientes)} dominios siguen compartidos por mas de una ficha")
        print("   (ninguna de sus fichas marco `fusionar` ni `corregir_dominio`)")
        for d, nombres in sorted(pendientes.items())[:10]:
            print(f"   {d[:44]:46} {' · '.join(x[:24] for x in nombres)}")
        print("   -> entran solos al proximo `preparar_lotes_resolucion.py`")
    else:
        print("\nCero dominios compartidos entre fichas activas.")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
