"""Carga a `programas_investigados` lo que devolvieron los subagents.

Este es el punto donde se desconfía
-----------------------------------
Un agente puede escribir programas sin haber abierto el sitio. Ya pasó en la
versión por API: el modelo devolvió 38 programas de tres instituciones con CERO
búsquedas, de memoria. Ahí se detectó con el contador de búsquedas de la API;
aquí no hay contador, así que la verificación es sobre el dato mismo:

  1. **`url_fuente` obligatoria y en el dominio oficial de la institución.** Una
     fila sin URL, o con una URL de otro dominio, no entra. Es la comprobación
     mecánica de que el agente estuvo en el sitio correcto — no prueba que leyó
     bien, pero sí descarta lo escrito de memoria y lo tomado de un competidor.
  2. **`nivel` y `area` contra el vocabulario cerrado.** Lo que no mapea se
     descarta y se reporta; nunca va a un cajón "Otros", porque un área mal
     clasificada desaparece del filtro sin que nadie note que faltaba.
  3. **Nada de precios.** Si el CSV trae una columna de precio, el archivo entero
     se rechaza: significa que el agente no siguió las reglas y el resto de su
     salida tampoco es confiable.
  4. **Sólo instituciones del catálogo autorizado.** Un nombre que no está en
     `institutions_catalog` activo no entra: o el agente lo inventó, o investigó
     algo que no se puede vender.

Formato que deben escribir los agentes · `data/catalogo/programas_agentes/lote_NN.csv`

    institucion,nombre,nivel,area,duracion,codigo_oficial,url_fuente

Uso
---
    python scripts/cargar_investigacion_agentes.py            # simulacro
    python scripts/cargar_investigacion_agentes.py --commit
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import ProgramaInvestigado  # noqa: E402
from app.services import areas as areas_mod  # noqa: E402
from scripts.import_catalogo_autorizado import (  # noqa: E402
    NIVEL_AUTORIZADO_A_INVESTIGADO,
    clave_nombre,
)
from scripts.investigar_programas import NIVELES_VALIDOS, _confianza  # noqa: E402

ENTRADA = Path("data/catalogo/programas_agentes")

COLUMNAS = ("institucion", "nombre", "nivel", "area", "duracion", "codigo_oficial", "url_fuente")

# Si aparece cualquiera de estas, el archivo se rechaza entero.
COLUMNAS_PROHIBIDAS = ("precio", "costo", "cost", "price", "fee", "tuition", "beca", "scholarship")


def _host(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    s = url.strip()
    if not s:
        return None
    if "//" not in s:
        s = "https://" + s
    h = (urlparse(s).netloc or "").lower().split("@")[-1].split(":")[0]
    return h[4:] if h.startswith("www.") else h or None


# Dominios distintos que son la MISMA institución, verificados uno a uno contra
# el `<link rel="canonical">` del sitio. Existe porque varias universidades se
# renombraron el dominio y dejaron el catálogo en el viejo: la ficha trae el
# nuevo (`txst.edu`) y las fichas de programa viven en el legado
# (`mycatalog.txstate.edu`), así que la comprobación de dominio las rechazaba.
#
# Sólo se añade aquí lo que se pudo comprobar: `www.txstate.edu` declara
# `canonical = https://www.txst.edu/` y `mycatalog.txstate.edu` se titula "Texas
# State University". Sin esa evidencia NO se agrega — esta tabla es la única
# puerta por la que puede entrar el catálogo de otra entidad.
ALIAS_DOMINIO = {
    "txstate.edu": "txst.edu",
}


def _mismo_sitio(host: Optional[str], dominio: Optional[str]) -> bool:
    """Acepta subdominios (`courses.acu.edu.au` vale para `acu.edu.au`)."""
    if not host or not dominio:
        return False
    for h in (host, ALIAS_DOMINIO.get(host)):
        if not h:
            continue
        if h == dominio or h.endswith("." + dominio):
            return True
    # El alias también aplica al dominio raíz del host: `mycatalog.txstate.edu`
    # no está en la tabla, pero `txstate.edu` sí.
    partes = host.split(".")
    for i in range(1, len(partes) - 1):
        raiz = ".".join(partes[i:])
        alias = ALIAS_DOMINIO.get(raiz)
        if alias and (alias == dominio or alias.endswith("." + dominio)):
            return True
    return False


def _niveles_permitidos(autorizados: List[str]) -> set:
    """Niveles que se pueden MOSTRAR. Vacío = sin restricción.

    Las tres entradas son distintas y hay que separarlas, porque dos de ellas
    se parecen y significan lo contrario:

      ``["todos"]``  el archivo del cliente dice "Todos los programas" → se
                     muestra todo. Devuelve un conjunto vacío, que aguas abajo
                     se lee como "sin restricción".
      ``["pregrado"]`` autorización concreta → se muestra lo que mapee.
      ``[]``         el archivo **no dice nada**. No es permiso: es un dato que
                     falta. Se guarda todo y no se muestra nada, que es el lado
                     seguro del error — mostrar de menos molesta, prometerle a
                     una familia un producto que la agencia no puede tramitar
                     revienta después.

    El centinela ``__ninguno__`` es lo que distingue el tercer caso del primero:
    sin él, un conjunto vacío por falta de dato se lee igual que "todos".
    Esta función decía ``if not autorizados or "todos" in autorizados`` y los
    confundía, así que la misma ficha salía visible al cargar e invisible al
    reimportar el Excel, según cuál de los dos scripts la hubiera tocado
    último. `import_catalogo_autorizado.py` ya lo hacía bien; esto lo alinea.
    """
    if "todos" in (autorizados or []):
        return set()
    out: set = set()
    for n in autorizados or []:
        out.update(NIVEL_AUTORIZADO_A_INVESTIGADO.get(n, ()))
    return out or {"__ninguno__"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Carga lo investigado por los agentes")
    ap.add_argument("--commit", action="store_true", help="Escribe en la DB")
    ap.add_argument("--entrada", default=str(ENTRADA), help="Carpeta con los CSV")
    args = ap.parse_args()

    carpeta = Path(args.entrada)
    archivos = sorted(carpeta.glob("*.csv"))
    if not archivos:
        print(f"No hay CSV en {carpeta.resolve()}")
        return 0

    db = SessionLocal()

    # El catálogo autorizado, indexado por nombre normalizado.
    catalogo: Dict[str, dict] = {}
    for r in db.execute(
        text(
            "select name, country, city, website, niveles_autorizados "
            "from institutions_catalog where active"
        )
    ):
        catalogo[clave_nombre(r[0])] = {
            "nombre": r[0],
            "pais": r[1],
            "ciudad": r[2],
            "dominio": _host(r[3]),
            "niveles": list(r[4] or []),
        }

    # OJO · aqui NO se filtra por "institucion que ya tiene programas".
    #
    # Esa regla existia para no recargar lo ya investigado, y con los agentes
    # escribiendo su CSV de forma incremental se volvio destructiva: si se carga
    # mientras el agente sigue escribiendo, la institucion queda marcada como
    # "ya tiene" y el RESTO de su catalogo se descarta en silencio. Costo 218
    # programas del lote 04 antes de detectarse.
    #
    # La proteccion real es la deduplicacion por (institucion, nombre) de abajo,
    # que es ademas la misma llave del UNIQUE de la tabla: deja pasar lo nuevo y
    # rechaza lo repetido, sin importar en cuantas tandas llegue.

    # Para colgar la ficha del programa (`program_id`) cuando existe.
    fichas: Dict[str, Any] = {}
    for r in db.execute(text("select id, institution from programs where active")):
        fichas.setdefault(clave_nombre(r[1] or ""), r[0])

    # La tabla tiene UNIQUE (institucion, nombre). Hay que respetarlo ANTES de
    # insertar: un solo choque aborta el lote entero de 855 filas y no se carga
    # nada. Se choca de tres formas — el mismo programa con dos niveles dentro de
    # un archivo, la misma institucion repartida en dos lotes, y un reintento
    # sobre algo ya cargado — asi que la clave se lleva global y sembrada con lo
    # que ya esta en la base.
    ya_en_base = {
        (clave_nombre(r[0]), (r[1] or "").strip().lower())
        for r in db.execute(text("select institucion, nombre from programas_investigados"))
    }

    descartes: Counter = Counter()
    rechazados: List[str] = []
    listos: List[dict] = []
    por_institucion: Counter = Counter()

    for archivo in archivos:
        with open(archivo, encoding="utf-8-sig", newline="") as fh:
            lector = csv.DictReader(fh)
            cabeceras = [(c or "").strip().lower() for c in (lector.fieldnames or [])]
            prohibida = next(
                (c for c in cabeceras if any(p in c for p in COLUMNAS_PROHIBIDAS)), None
            )
            if prohibida:
                # No es un descarte de fila: es el archivo entero. Si trajo precios,
                # ignoró la regla que más importa y su criterio no es confiable.
                rechazados.append(f"{archivo.name} · trae columna prohibida '{prohibida}'")
                continue
            faltan = [c for c in ("institucion", "nombre", "nivel", "area") if c not in cabeceras]
            if faltan:
                rechazados.append(f"{archivo.name} · le faltan columnas: {', '.join(faltan)}")
                continue

            # Prefijo `ag` para no chocar con los lotes del pipeline manual, que
            # usaban 01..42: sin esto, 428 filas nuevas quedaron indistinguibles
            # de 1.182 viejas y no habria forma de revertir solo lo de los agentes.
            lote = ("ag" + archivo.stem.replace("lote_", ""))[:8]
            for fila in lector:
                inst_cruda = (fila.get("institucion") or "").strip()
                k = clave_nombre(inst_cruda)
                info = catalogo.get(k)
                if not info:
                    descartes[f"institucion fuera del catalogo autorizado: {inst_cruda[:40]}"] += 1
                    continue
                nombre = (fila.get("nombre") or "").strip()
                if not nombre:
                    descartes["sin nombre"] += 1
                    continue

                nivel = (fila.get("nivel") or "").strip().lower()
                if nivel not in NIVELES_VALIDOS:
                    descartes[f"nivel fuera del vocabulario: {nivel or '(vacio)'}"] += 1
                    continue

                area = areas_mod.normalizar(fila.get("area"))
                if not area:
                    descartes[f"area sin mapear: {fila.get('area')}"] += 1
                    continue

                url = (fila.get("url_fuente") or "").strip() or None
                host = _host(url)
                if not _mismo_sitio(host, info["dominio"]):
                    # La comprobación que reemplaza al contador de búsquedas.
                    descartes[
                        f"url fuera del dominio oficial ({host or 'sin url'} != {info['dominio']})"
                    ] += 1
                    continue

                codigo = (fila.get("codigo_oficial") or "").strip()
                codigo = None if codigo in ("", "-", "?", "null", "N/A", "n/a") else codigo[:80]

                clave_unica = (k, nombre.lower())
                if clave_unica in ya_en_base:
                    descartes["programa repetido (misma institucion y nombre)"] += 1
                    continue
                ya_en_base.add(clave_unica)

                permitidos = _niveles_permitidos(info["niveles"])
                listos.append(
                    dict(
                        id=uuid.uuid4(),
                        institucion=info["nombre"][:255],
                        nombre=nombre[:500],
                        pais=info["pais"],
                        ciudad=(info["ciudad"] or "")[:160] or None,
                        nivel=nivel,
                        area=area,
                        area_cruda=(fila.get("area") or "")[:160] or None,
                        duracion=(fila.get("duracion") or "")[:120] or None,
                        codigo_oficial=codigo,
                        url_fuente=url,
                        dominio=(info["dominio"] or "")[:160] or None,
                        confianza=_confianza(codigo, url, info["dominio"] or ""),
                        # El nivel autorizado decide si se MUESTRA, no si se guarda:
                        # si la clienta amplía lo que puede vender, el dato ya está.
                        activo=(not permitidos) or (nivel in permitidos),
                        program_id=fichas.get(k),
                        lote=lote,
                    )
                )
                por_institucion[info["nombre"]] += 1

    print("=" * 72)
    print("CARGA DE LO INVESTIGADO ·", "ESCRIBE" if args.commit else "SIMULACRO")
    print("=" * 72)
    print(f"Archivos leidos      : {len(archivos)}")
    if rechazados:
        print(f"Archivos RECHAZADOS  : {len(rechazados)}")
        for r in rechazados:
            print(f"    {r}")
    print(f"Programas validos    : {len(listos)}")
    print(f"Instituciones nuevas : {len(por_institucion)}")
    if listos:
        conf = Counter(x["confianza"] for x in listos)
        print(f"  confianza          : {dict(conf)}")
        print(f"  visibles ahora     : {sum(1 for x in listos if x['activo'])}")
        print(f"  guardados pero ocultos por nivel no autorizado: "
              f"{sum(1 for x in listos if not x['activo'])}")
    if descartes:
        print("\nDescartados:")
        for m, n in descartes.most_common(12):
            print(f"    {n:5}  {m}")

    if por_institucion:
        print("\nPor institucion:")
        for nombre, n in por_institucion.most_common(15):
            print(f"    {n:5}  {nombre[:52]}")

    if not args.commit:
        print("\nSIMULACRO · no se escribio nada. Repetir con --commit.")
        db.close()
        return 0

    for f in listos:
        db.add(ProgramaInvestigado(**f))
    db.commit()
    print(f"\nESCRITO · {len(listos)} programas de {len(por_institucion)} instituciones.")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
