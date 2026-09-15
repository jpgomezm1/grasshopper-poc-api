"""Aplica la auditoría de fichas · corrige dominios, marca las muertas, detecta duplicados.

Qué hace con cada veredicto
---------------------------
El agente auditor devuelve, por ficha, un `estado` y —cuando corresponde— el
dominio y el nombre reales. Aquí eso se convierte en cambios concretos:

  `ok`            · el dominio vive y lista programas. Nada que corregir; pasa a extracción.
  `dominio_nuevo` · redirección o rebrand verificado. **Se corrige el `website`**
                    de la ficha. Es lo que en el piloto costó 15 filas buenas:
                    `ahts.sa.edu.au` hace 301 permanente a `alliancecollege.edu.au`,
                    el validador las rechazó con razón, y no había forma de honrar
                    una corrección verificada sin ablandar la regla. Ahora la hay.
  `sin_catalogo`  · el sitio vive pero no publica programas. No se extrae: se
                    reporta al cliente para que lo consiga por su canal.
  `dominio_muerto`· NXDOMAIN o bloqueo total. Se marca y **no se gasta la pasada cara**.
  `otra_institucion` · el dominio es de otra entidad (el caso `alg.edu.au` en tres
                    fichas). NO se corrige solo: se reporta, porque adivinar aquí
                    es exactamente lo que produce catálogos con datos de un competidor.

Y por encima de eso, busca **fichas duplicadas**: si dos fichas activas terminan
apuntando al mismo dominio real, es la misma institución dos veces. En el piloto
aparecieron `Ahts Training & Education` y `Alliance College` — la vieja con
dominio viejo, la nueva vacía, las dos visibles para el estudiante.

Nada se borra. Los duplicados se reportan para que los revise un humano: fusionar
mal dos instituciones es peor que tenerlas dos veces.

Formato que escriben los agentes · `data/catalogo/auditoria_agentes/aud_NN.csv`

    institucion,estado,dominio_real,nombre_real,url_programas,cantidad_aprox,niveles_vistos,nota

Uso
---
    python scripts/aplicar_auditoria.py            # simulacro
    python scripts/aplicar_auditoria.py --commit
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from scripts.import_catalogo_autorizado import clave_nombre  # noqa: E402
from scripts.cargar_investigacion_agentes import _host  # noqa: E402

# `rglob` y no `glob`: los lotes se renumeran desde 01 cada vez que se regeneran
# contra un catalogo que cambio, asi que `aud_05.csv` de una ronda pisa el de la
# anterior. Las rondas viejas se archivan en subcarpetas (`ronda1/`) y tienen que
# seguir contando — lo detectaron dos agentes que respaldaron el archivo por su
# cuenta antes de sobrescribirlo.
ENTRADA = Path("data/catalogo/auditoria_agentes")
SALIDA = Path("data/catalogo/revision")

ESTADOS = ("ok", "dominio_nuevo", "sin_catalogo", "dominio_muerto", "otra_institucion")


def _escribir_csv(ruta: Path, columnas: List[str], filas: List[Dict[str, Any]]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas)
        w.writeheader()
        for f in filas:
            w.writerow({c: f.get(c) for c in columnas})


def main() -> int:
    ap = argparse.ArgumentParser(description="Aplica los veredictos de la auditoría")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--entrada", default=str(ENTRADA))
    args = ap.parse_args()

    archivos = sorted(Path(args.entrada).rglob("*.csv"))
    if not archivos:
        print(f"No hay CSV en {Path(args.entrada).resolve()}")
        return 0

    db = SessionLocal()
    catalogo: Dict[str, dict] = {}
    for r in db.execute(
        text("select id, name, website, country from institutions_catalog where active")
    ):
        catalogo[clave_nombre(r[1])] = {
            "id": r[0],
            "nombre": r[1],
            "dominio": _host(r[2]),
            "pais": r[3],
        }

    veredictos: Dict[str, dict] = {}
    descartes: Counter = Counter()
    for archivo in archivos:
        with open(archivo, encoding="utf-8-sig", newline="") as fh:
            for fila in csv.DictReader(fh):
                k = clave_nombre((fila.get("institucion") or "").strip())
                if k not in catalogo:
                    descartes[f"ficha desconocida: {(fila.get('institucion') or '')[:40]}"] += 1
                    continue
                estado = (fila.get("estado") or "").strip().lower()
                if estado not in ESTADOS:
                    descartes[f"estado invalido: {estado or '(vacio)'}"] += 1
                    continue
                veredictos[k] = {
                    "estado": estado,
                    "dominio_real": _host(fila.get("dominio_real")),
                    "nombre_real": (fila.get("nombre_real") or "").strip() or None,
                    "url_programas": (fila.get("url_programas") or "").strip() or None,
                    "cantidad_aprox": (fila.get("cantidad_aprox") or "").strip() or None,
                    "niveles_vistos": (fila.get("niveles_vistos") or "").strip() or None,
                    "nota": (fila.get("nota") or "").strip() or None,
                }

    conteo = Counter(v["estado"] for v in veredictos.values())

    # Correcciones de dominio · solo las verificadas por el agente y distintas
    # de lo que ya tiene la ficha.
    correcciones = []
    for k, v in veredictos.items():
        if v["estado"] != "dominio_nuevo" or not v["dominio_real"]:
            continue
        actual = catalogo[k]["dominio"]
        if v["dominio_real"] == actual:
            continue
        correcciones.append(
            {
                "institucion": catalogo[k]["nombre"],
                "dominio_anterior": actual,
                "dominio_nuevo": v["dominio_real"],
                "nombre_real": v["nombre_real"],
                "nota": v["nota"],
                "_id": catalogo[k]["id"],
            }
        )

    # Duplicados · dos fichas activas que terminan en el mismo dominio real.
    por_dominio: Dict[str, List[str]] = defaultdict(list)
    for k, info in catalogo.items():
        v = veredictos.get(k)
        d = (v or {}).get("dominio_real") or info["dominio"]
        if d:
            por_dominio[d].append(info["nombre"])
    duplicados = [
        {"dominio": d, "fichas": " · ".join(sorted(n)), "cuantas": len(n)}
        for d, n in sorted(por_dominio.items())
        if len(n) > 1
    ]

    print("=" * 72)
    print("AUDITORIA DE FICHAS ·", "APLICA" if args.commit else "SIMULACRO")
    print("=" * 72)
    print(f"Veredictos leidos : {len(veredictos)}  (de {len(archivos)} archivos)")
    for e in ESTADOS:
        print(f"    {conteo.get(e, 0):5}  {e}")
    if descartes:
        print("\n  descartados:")
        for m, n in descartes.most_common(8):
            print(f"    {n:5}  {m}")
    print()
    print(f"Dominios a corregir       : {len(correcciones)}")
    print(f"Dominios en >1 ficha      : {len(duplicados)}  <- posibles duplicados")
    listas_para_extraer = conteo.get("ok", 0) + conteo.get("dominio_nuevo", 0)
    print(f"Fichas listas para extraer: {listas_para_extraer}")
    ahorro = conteo.get("dominio_muerto", 0) + conteo.get("sin_catalogo", 0) + conteo.get(
        "otra_institucion", 0
    )
    print(f"Fichas que NO se extraen  : {ahorro}  <- la pasada cara que se ahorra")
    print()

    _escribir_csv(
        SALIDA / "auditoria_correcciones_dominio.csv",
        ["institucion", "dominio_anterior", "dominio_nuevo", "nombre_real", "nota"],
        correcciones,
    )
    _escribir_csv(
        SALIDA / "auditoria_fichas_rotas.csv",
        ["institucion", "pais", "estado", "dominio_en_la_ficha", "nota"],
        [
            {
                "institucion": catalogo[k]["nombre"],
                "pais": catalogo[k]["pais"],
                "estado": v["estado"],
                "dominio_en_la_ficha": catalogo[k]["dominio"],
                "nota": v["nota"],
            }
            for k, v in sorted(veredictos.items())
            if v["estado"] in ("dominio_muerto", "sin_catalogo", "otra_institucion")
        ],
    )
    _escribir_csv(
        SALIDA / "auditoria_posibles_duplicados.csv",
        ["dominio", "cuantas", "fichas"],
        duplicados,
    )
    print(f"CSV en {SALIDA.resolve()}")
    print("   auditoria_correcciones_dominio.csv · auditoria_fichas_rotas.csv")
    print("   auditoria_posibles_duplicados.csv  <- para el cliente, y para revisar a mano")
    print()

    if not args.commit:
        print("SIMULACRO · no se escribio nada. Repetir con --commit.")
        db.close()
        return 0

    # Lo unico que se escribe automaticamente es la correccion de dominio, y solo
    # la que el agente verifico con una redireccion. Los duplicados y las fichas
    # rotas se reportan: fusionar mal dos instituciones, o apagar una que solo
    # estaba caida ese dia, es peor que dejarlas como estan.
    for c in correcciones:
        db.execute(
            text(
                "update institutions_catalog "
                "set website = :w, updated_at = now() where id = :id"
            ),
            {"w": "https://" + c["dominio_nuevo"], "id": c["_id"]},
        )
    db.commit()
    print(f"APLICADO · {len(correcciones)} dominios corregidos.")
    print(f"  {len(duplicados)} posibles duplicados y "
          f"{ahorro} fichas rotas quedan REPORTADOS, sin tocar.")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
