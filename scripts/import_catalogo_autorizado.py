"""Catálogo autorizado · el xlsx "INSTITUCIONES AI para mentoring platform".

Qué es este archivo y por qué merece su propio importador
---------------------------------------------------------
`import_institutions.py` importa el maestro comercial del cliente: 34 columnas
con contratos, comisiones, fechas y contactos. Este otro archivo es distinto en
naturaleza: son 10 columnas y **es una curaduría**. El 93% de sus instituciones
ya está en `institutions_catalog`; lo que aporta no es data nueva sino DOS cosas
que no existían:

  1. **Cuáles** de las ~2.500 instituciones se le muestran de verdad al
     estudiante (632 de 694 filas · el resto son repetidas).
  2. **Qué niveles** puede vender la agencia en cada una — las columnas
     "Programa 1/2/3". Es la mitad del pedido de Verónica que no se podía
     cumplir: el Excel dice que de FIU Miami solo se pueden vender los
     pregrados, y le toca al sistema ir a buscar cuáles son.

Qué hace y qué NO hace
----------------------
- **Corre en seco por defecto.** No porque local sea producción —no lo es, son
  dos ramas distintas de Neon— sino porque este script apaga miles de filas de
  golpe y el reporte previo es lo que deja ver si el cruce salió bien ANTES de
  aplicarlo. Los conteos que imprime dependen de contra qué base corra: los de
  producción sólo se ven corriéndolo allá.
- **Nunca borra una fila.** El reemplazo se aplica con `active=False`. El efecto
  para el estudiante es el mismo que borrar; el costo de equivocarse, no:
  revertir es un UPDATE en vez de volver a investigar 9.426 programas.
- **No adivina nombres.** El cruce es por nombre normalizado EXACTO. Todo lo que
  no cruce sale a un CSV con sus tres candidatos más parecidos, para que un
  humano decida. "Monash College" y "Monash University" son instituciones
  distintas y un matcher entusiasta las funde en una.
- **No inventa niveles.** El archivo escribe el mismo concepto de 72 maneras, en
  dos idiomas. Lo que no se pueda mapear al vocabulario cerrado sale reportado,
  no se descarta en silencio ni se mete con un valor cualquiera.

Uso
---
    python scripts/import_catalogo_autorizado.py <ruta.xlsx>              # seco
    python scripts/import_catalogo_autorizado.py <ruta.xlsx> --commit     # escribe
    python scripts/import_catalogo_autorizado.py <ruta.xlsx> --salida <dir>

En producción se corre donde viven las credenciales, no desde local:
    heroku run "python scripts/import_catalogo_autorizado.py <ruta> --commit" -a <app>
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover
    raise SystemExit("openpyxl no instalado · pip install openpyxl")

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402

# El catálogo guarda los países ya normalizados y en inglés ("Canada", "Spain",
# "Germany"); este Excel los escribe en español ("Canadá", "España", "Alemania").
# Se reusa el mismo mapa del importador maestro en vez de escribir un segundo:
# dos tablas de países que se separan es un filtro de país que empieza a mentir.
from scripts.import_institutions import COUNTRY_MAP  # noqa: E402


# ---------------------------------------------------------------------------
# Vocabulario cerrado de niveles
# ---------------------------------------------------------------------------
#
# Es cerrado a propósito: sirve para FILTRAR los programas investigados, y un
# filtro contra texto libre no filtra nada. `programs_offered` sigue guardando
# el texto crudo para mostrar; esto es lo que se compara.

NIVELES = (
    "idiomas",
    "vocacional",
    "high_school",
    "pathway",
    "pregrado",
    "posgrado",
    "doctorado",
    "intercambio",
    "vacacional",
    "pasantias",
    "todos",
)

# "Programa" en este archivo no siempre es un nivel académico: hay filas que
# dicen "Alojamiento" o "Seguro", que son servicios de la agencia. No se mapean
# a un nivel · se reportan, porque meterlos como si lo fueran ensucia el filtro.
NO_ES_NIVEL = ("alojamiento", "seguro", "full time", "de acuerdo a la institucion")

# Frase exacta (normalizada) -> niveles. Se consulta antes que las palabras
# clave porque algunas frases dicen más que sus palabras sueltas.
FRASES: Dict[str, Tuple[str, ...]] = {
    "todos los programas": ("todos",),
    "idiomas": ("idiomas",),
    "cursos de espanol": ("idiomas",),
    "vocacionales cert dip adv dip": ("vocacional",),
    "vet": ("vocacional",),
    "high school": ("high_school",),
    "high school aged 14": ("high_school",),
    "pregrado": ("pregrado",),
    "pregado": ("pregrado",),  # está así en el archivo
    "undergraduate": ("pregrado",),
    "undergraduate degree": ("pregrado",),
    "pregrado community college": ("pregrado",),
    "grado postgrado": ("pregrado", "posgrado"),
    "pregrado postgrado": ("pregrado", "posgrado"),
    "undergraduate graduate": ("pregrado", "posgrado"),
    "undergraduate and graduate programs": ("pregrado", "posgrado"),
    "postgraduate undergraduate": ("pregrado", "posgrado"),
    "master y grado": ("pregrado", "posgrado"),
    "postgrado": ("posgrado",),
    "postgrados": ("posgrado",),
    "solo postgrado": ("posgrado",),
    "portafolio posgrados": ("posgrado",),
    "graduate": ("posgrado",),
    "graduate degrees": ("posgrado",),
    "graduate programs business school": ("posgrado",),
    "master": ("posgrado",),
    "pre masters": ("pathway",),
    "foundation certificate": ("pathway",),
    "pathway": ("pathway",),
    "acceso directo": ("pregrado",),
    "admision directa": ("pregrado",),
    "study abroad": ("intercambio",),
    "study abroad por 1 ano": ("intercambio",),
    "internships": ("pasantias",),
    "camps": ("vacacional",),
    "campamentos": ("vacacional",),
    "summer programs": ("vacacional",),
}

# Palabra clave -> nivel. Para la cola larga (una fila cada una) que combina
# varios niveles en una frase libre.
CLAVES: Tuple[Tuple[str, str], ...] = (
    ("foundation", "pathway"),
    ("pathway", "pathway"),
    ("pre master", "pathway"),
    ("premaster", "pathway"),
    ("international year one", "pathway"),
    ("year 1", "pathway"),
    ("utp", "pathway"),
    ("preparation", "pathway"),
    ("preparacion", "pathway"),
    ("bridge", "pathway"),
    ("professional year", "pathway"),
    ("honors program", "pathway"),
    ("success program", "pathway"),
    ("idiomas", "idiomas"),
    ("ingles", "idiomas"),
    ("english", "idiomas"),
    ("polish", "idiomas"),
    ("espanol", "idiomas"),
    ("courses and trainings", "idiomas"),
    ("bachelor", "pregrado"),
    ("undergraduate", "pregrado"),
    ("pregrado", "pregrado"),
    ("grado medio", "vocacional"),
    ("grado superior", "vocacional"),
    ("ciclo formativo", "vocacional"),
    ("formacion profesional", "vocacional"),
    ("certificado de profesionalidad", "vocacional"),
    ("diploma", "vocacional"),
    ("certificate", "vocacional"),
    ("cerficate", "vocacional"),  # está así en el archivo
    ("master", "posgrado"),
    ("msc", "posgrado"),
    ("mge", "posgrado"),
    ("postgrad", "posgrado"),
    ("posgrado", "posgrado"),
    ("graduate", "posgrado"),
    ("phd", "doctorado"),
    ("doctorado", "doctorado"),
    ("study abroad", "intercambio"),
    ("semestre internacional", "intercambio"),
    ("semesstre internacional", "intercambio"),  # está así en el archivo
    ("intercambio", "intercambio"),
    ("summer", "vacacional"),
    ("verano", "vacacional"),
    ("camp", "vacacional"),
    ("pasantia", "pasantias"),
    ("internship", "pasantias"),
    ("high school", "high_school"),
    ("secundaria", "high_school"),
)

# Qué `programas_investigados.nivel` habilita cada nivel autorizado. El
# vocabulario de esa tabla nació aparte, así que el puente vive aquí y no se
# reimplementa en cada consulta.
NIVEL_AUTORIZADO_A_INVESTIGADO: Dict[str, Tuple[str, ...]] = {
    "idiomas": ("curso_corto",),
    "vocacional": ("diplomado", "especializacion", "curso_corto"),
    "high_school": ("secundaria",),
    "pathway": ("curso_corto", "diplomado"),
    "pregrado": ("pregrado", "bachelor"),
    # "Postgrado" en español es el paraguas: incluye especialización, maestría y
    # DOCTORADO. Dejar el doctorado afuera apagaba 63 programas de instituciones
    # que el Excel sí autoriza para postgrado · era un criterio nuestro, no del
    # cliente. Si alguna vez hay que separarlos, el archivo tendrá que decirlo.
    "posgrado": ("posgrado", "maestria", "mba", "especializacion", "doctorado"),
    "doctorado": ("doctorado",),
    "intercambio": ("intercambio",),
    "vacacional": ("vacacional",),
    "pasantias": ("curso_corto",),
}


def _norm_pais(raw: Any) -> Any:
    """País del Excel -> el mismo vocabulario que ya usa el catálogo."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return COUNTRY_MAP.get(s.lower(), s)


def _sin_tildes(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def clave_nivel(texto: str) -> str:
    """Texto de nivel -> forma comparable (sin tildes, sin puntuación)."""
    t = _sin_tildes(str(texto)).lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def normalizar_niveles(textos: List[str]) -> Tuple[List[str], List[str]]:
    """(niveles del vocabulario cerrado, textos que no se pudieron mapear)."""
    niveles: List[str] = []
    sin_mapear: List[str] = []
    for crudo in textos:
        k = clave_nivel(crudo)
        if not k:
            continue
        if any(x in k for x in NO_ES_NIVEL):
            sin_mapear.append(crudo)
            continue
        if k in FRASES:
            for n in FRASES[k]:
                if n not in niveles:
                    niveles.append(n)
            continue
        encontrados = [nivel for palabra, nivel in CLAVES if palabra in k]
        if encontrados:
            for n in encontrados:
                if n not in niveles:
                    niveles.append(n)
        else:
            sin_mapear.append(crudo)
    return niveles, sin_mapear


def clave_nombre(nombre: str) -> str:
    """Nombre de institución -> clave de cruce.

    Deliberadamente conservadora: baja a minúsculas, quita tildes y puntuación y
    colapsa espacios · NADA más. Quitar "College"/"University" haría cruzar
    `Monash College` con `Monash University`, que son instituciones distintas.

    El apóstrofo se borra en vez de volverse espacio: si no, `Queen's School` da
    "queen s school" y no cruza con `Queens School`, que es la misma.
    """
    s = _sin_tildes(str(nombre)).lower()
    s = re.sub(r"['’´`]", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# Paréntesis final con una sigla · "Florida International University (FIU)".
# Una sigla va en MAYUSCULAS; un campus va capitalizado. Es lo unico que
# distingue "(UEA)" de "(Sydney)" sin una lista de ciudades, y la diferencia
# importa: `Charles Darwin University (Sydney)` y `Niagara College - Toronto`
# son sedes con catalogo propio, no otra forma de escribir la casa matriz.
# La version anterior aceptaba [A-Za-z] y fusionaba las sedes con la matriz.
_SIGLA_FINAL = re.compile(r"\s*\(([A-Z][A-Z\.]{1,11})\)\s*$")
# La misma sigla, pegada con guion delante o detras: el Excel del cliente usa
# las dos formas ("FAU - Florida Atlantic University", "Anglia Ruskin - ARU").
_SIGLA_GUION = re.compile(r"^([A-Z][A-Z\.]{1,11})\s*[-–]\s+|\s+[-–]\s*([A-Z][A-Z\.]{1,11})\s*$")


def clave_relajada(nombre: str) -> str:
    """Segunda pasada · variantes de escritura del MISMO nombre, nada más.

    Son cuatro reglas deterministas, no un fuzzy match:
      · quitar la sigla entre paréntesis al final — "(FIU)", "(UCF)", "(UTSA)"
      · quitar la sigla pegada con guion, delante o detrás — "FAU - Florida
        Atlantic University", "Anglia Ruskin University - ARU". El Excel del
        cliente usa las dos formas para la misma institución.
      · quitar el "The" inicial
      · lo que ya hace `clave_nombre`

    Existe porque el cruce exacto dejaba fuera instituciones que sí están en el
    catálogo, escritas apenas distinto. Lo que NO hace es acercar nombres
    parecidos: `Loyola University` y `Lynn University` siguen sin cruzar, que es
    lo correcto. Un match relajado solo se acepta si apunta a UNA sola
    institución, y queda listado aparte para poder auditarlo.

    La sigla tiene que ir en MAYÚSCULAS, y eso no es cosmético: es lo que separa
    "(UEA)" de "(Sydney)". `Charles Darwin University (Sydney)` y `Niagara
    College - Toronto` son sedes con catálogo propio; fusionarlas con la casa
    matriz cuelga el catálogo de un campus del otro.
    """
    s = str(nombre).strip()
    m = _SIGLA_FINAL.search(s)
    if m:
        s = s[: m.start()]
    s = _SIGLA_GUION.sub("", s).strip()
    k = clave_nombre(s)
    return re.sub(r"^the ", "", k).strip()


def leer_excel(ruta: str) -> List[Dict[str, Any]]:
    wb = load_workbook(ruta, data_only=True)
    ws = wb[wb.sheetnames[0]]
    filas: List[Dict[str, Any]] = []
    for i, f in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        nombre = str(f[1]).strip() if f[1] else ""
        if not nombre:
            continue
        crudos = [str(x).strip() for x in (f[7], f[8], f[9]) if x and str(x).strip()]
        niveles, sin_mapear = normalizar_niveles(crudos)
        filas.append(
            {
                "fila": i,
                "nombre": nombre,
                "clave": clave_nombre(nombre),
                "categoria": str(f[2]).strip() if f[2] else None,
                "en_grupo": (str(f[3]).strip().lower() in ("si", "sí")) if f[3] else False,
                "grupo": str(f[4]).strip() if f[4] else None,
                "pais": _norm_pais(f[5]),
                "pais_crudo": str(f[5]).strip() if f[5] else None,
                "ciudad": str(f[6]).strip() if f[6] else None,
                "niveles_crudos": crudos,
                "niveles": niveles,
                "niveles_sin_mapear": sin_mapear,
            }
        )
    return filas


def _update_por_lotes(db, sql: str, ids: List[str], lote: int = 2000, **extra: Any) -> None:
    """Un UPDATE por lote de ids · no uno por fila.

    Los ids van como array de uuid en un solo parámetro: mandar 15.000 ids en un
    `IN (...)` genera una sentencia enorme y roza el techo de parámetros del
    driver. El lote de 2.000 es un punto medio cómodo.
    """
    for i in range(0, len(ids), lote):
        db.execute(text(sql), {"ids": ids[i : i + lote], **extra})


def _escribir_csv(ruta: Path, columnas: List[str], filas: List[Dict[str, Any]]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas)
        w.writeheader()
        for f in filas:
            w.writerow({c: f.get(c) for c in columnas})


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest del catálogo autorizado")
    ap.add_argument("xlsx", help="Ruta al archivo del cliente")
    ap.add_argument("--commit", action="store_true", help="Escribe en la DB")
    ap.add_argument("--salida", default="data/catalogo/revision", help="Dónde dejar los CSV")
    args = ap.parse_args()

    filas = leer_excel(args.xlsx)
    salida = Path(args.salida)

    # ── Duplicados dentro del propio archivo ────────────────────────────────
    por_clave: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for f in filas:
        por_clave[f["clave"]].append(f)
    duplicados = {k: v for k, v in por_clave.items() if len(v) > 1}

    # ── Cruce contra la base ────────────────────────────────────────────────
    db = SessionLocal()
    catalogo = {
        clave_nombre(r[0]): (r[0], r[1])
        for r in db.execute(text("select name, id from institutions_catalog"))
    }
    claves_excel = set(por_clave)
    cruzan = claves_excel & set(catalogo)
    pendientes_de_cruce = claves_excel - set(catalogo)

    # ── Segunda pasada · variantes de escritura del mismo nombre ────────────
    # Un relajado solo cuenta si apunta a UNA institución del catálogo. Si apunta
    # a varias, es ambiguo y se va a revisión manual como si no hubiera cruzado.
    relajado_catalogo: Dict[str, List[str]] = defaultdict(list)
    for k_cat in catalogo:
        relajado_catalogo[clave_relajada(k_cat)].append(k_cat)

    equivalencias: Dict[str, str] = {}  # clave del Excel -> clave del catálogo
    for k in sorted(pendientes_de_cruce):
        candidatos = relajado_catalogo.get(clave_relajada(por_clave[k][0]["nombre"]), [])
        if len(candidatos) == 1:
            equivalencias[k] = candidatos[0]
    no_cruzan = pendientes_de_cruce - set(equivalencias)

    # A partir de aquí "autorizada" se mide contra las claves del CATÁLOGO, para
    # que un nombre escrito distinto en el Excel no apague a su institución.
    claves_autorizadas = set(cruzan) | {equivalencias[k] for k in equivalencias}

    # Los niveles se acumulan contra la clave del CATÁLOGO: una institución puede
    # aparecer en varias filas del Excel (misma casa, distintas ciudades) y sus
    # autorizaciones se suman, no se pisan.
    niveles_por_clave: Dict[str, List[str]] = defaultdict(list)
    for f in filas:
        k = equivalencias.get(f["clave"], f["clave"])
        for n in f["niveles"]:
            if n not in niveles_por_clave[k]:
                niveles_por_clave[k].append(n)

    # Qué `programas_investigados.nivel` queda habilitado por institución.
    # Conjunto vacío = sin restricción ("Todos los programas").
    niveles_investigados_ok: Dict[str, set] = {}
    for k in claves_autorizadas:
        autorizados = niveles_por_clave.get(k, [])
        if "todos" in autorizados:
            niveles_investigados_ok[k] = set()
            continue
        permitidos: set = set()
        for n in autorizados:
            permitidos.update(NIVEL_AUTORIZADO_A_INVESTIGADO.get(n, ()))
        niveles_investigados_ok[k] = permitidos or {"__ninguno__"}

    def _investigado_autorizado(institucion: Any, nivel: Any) -> bool:
        k = clave_nombre(institucion or "")
        if k not in claves_autorizadas:
            return False
        permitidos = niveles_investigados_ok.get(k, set())
        return (not permitidos) or ((nivel or "") in permitidos)

    # ── Impacto del reemplazo ───────────────────────────────────────────────
    inst_total = db.execute(text("select count(*) from institutions_catalog")).scalar()
    prog_activos = db.execute(text("select count(*) from programs where active")).scalar()
    inv_activos = db.execute(
        text("select count(*) from programas_investigados where activo")
    ).scalar()

    prog_por_clave: Dict[str, int] = defaultdict(int)
    for inst, n in db.execute(
        text("select institution, count(*) from programs where active group by 1")
    ):
        prog_por_clave[clave_nombre(inst or "")] += n
    inv_por_clave: Dict[str, int] = defaultdict(int)
    inv_sobreviven = 0
    inv_cortados_por_nivel = 0
    for inst, nivel, n in db.execute(
        text(
            "select institucion, nivel, count(*) from programas_investigados "
            "group by 1, 2"
        )
    ):
        k = clave_nombre(inst or "")
        inv_por_clave[k] += n
        if _investigado_autorizado(inst, nivel):
            inv_sobreviven += n
        elif k in claves_autorizadas:
            inv_cortados_por_nivel += n

    prog_sobreviven = sum(n for k, n in prog_por_clave.items() if k in claves_autorizadas)

    # ── Reporte ─────────────────────────────────────────────────────────────
    print("=" * 72)
    print("CATALOGO AUTORIZADO ·", "APLICANDO" if args.commit else "SIMULACRO (no escribe)")
    print("=" * 72)
    print(f"Filas con institucion            : {len(filas)}")
    print(f"Instituciones unicas             : {len(por_clave)}")
    print(f"  cruzan por nombre exacto       : {len(cruzan)}")
    print(f"  cruzan por variante de nombre  : {len(equivalencias)}")
    print(f"  NO estan en el catalogo        : {len(no_cruzan)} (se crean)")
    print(f"  nombres repetidos en el archivo: {len(duplicados)}")
    print()

    sin_categoria = sum(1 for f in filas if not f["categoria"])
    sin_nivel = sum(1 for f in filas if not f["niveles"])
    print(f"Filas sin categoria              : {sin_categoria}")
    print(f"Filas sin ningun nivel mapeado   : {sin_nivel}")
    todos_sin_mapear: Counter = Counter()
    for f in filas:
        for x in f["niveles_sin_mapear"]:
            todos_sin_mapear[x] += 1
    print(f"Textos de nivel sin mapear       : {len(todos_sin_mapear)} distintos")
    for texto, n in todos_sin_mapear.most_common(10):
        print(f"    {n:3}  {texto!r}")
    print()

    conteo_niveles: Counter = Counter()
    for f in filas:
        for n in f["niveles"]:
            conteo_niveles[n] += 1
    print("Niveles autorizados detectados:")
    for n, c in conteo_niveles.most_common():
        print(f"    {c:4}  {n}")
    print()

    activas_finales = len(claves_autorizadas) + len(no_cruzan)
    print("IMPACTO DEL REEMPLAZO (nada se borra · se desactiva):")
    print(
        f"  institutions_catalog  : {inst_total} -> {activas_finales} activas "
        f"({inst_total - len(claves_autorizadas)} se desactivan · "
        f"{len(no_cruzan)} nuevas)"
    )
    print(
        f"  programs              : {prog_activos} -> {prog_sobreviven} activos "
        f"({prog_activos - prog_sobreviven} se desactivan)"
    )
    print(
        f"  programas_investigados: {inv_activos} -> {inv_sobreviven} activos "
        f"({inv_activos - inv_sobreviven} se desactivan)"
    )
    print(
        f"     de esos, {inv_cortados_por_nivel} son de instituciones SI autorizadas "
        "pero en un nivel que la agencia no vende ahi"
    )
    print()

    # Autorizadas pero sin decir QUÉ se puede vender ahí · el Excel dejó en blanco
    # la columna "Programa 1". No se rellena con "todos": eso sería autorizar por
    # nuestra cuenta niveles que la agencia quizá no puede vender. Se listan para
    # devolvérselas al cliente.
    sin_nivel = sorted(
        {por_clave[k][0]["nombre"] for k in por_clave if not por_clave[k][0]["niveles"]}
    )
    if sin_nivel:
        print(
            f"OJO · {len(sin_nivel)} instituciones autorizadas sin ningun nivel: el archivo "
            "no dice que se puede vender ahi. Quedan visibles pero sin programas."
        )
        print("      -> autorizadas_sin_nivel.csv · para pedirselo al cliente")
        print()

    con_programas = sum(1 for k in claves_autorizadas if inv_por_clave.get(k))
    print(
        f"De las {activas_finales} autorizadas, {con_programas} tienen programas "
        f"investigados · {activas_finales - con_programas} no tienen ninguno."
    )
    print()

    # ── CSV de revisión ─────────────────────────────────────────────────────
    nombres_catalogo = list(catalogo)
    pendientes = []
    for k in sorted(no_cruzan):
        f = por_clave[k][0]
        cercanos = difflib.get_close_matches(k, nombres_catalogo, n=3, cutoff=0.75)
        pendientes.append(
            {
                "fila_excel": f["fila"],
                "nombre_en_excel": f["nombre"],
                "pais": f["pais"],
                "ciudad": f["ciudad"],
                "candidato_1": catalogo[cercanos[0]][0] if len(cercanos) > 0 else "",
                "candidato_2": catalogo[cercanos[1]][0] if len(cercanos) > 1 else "",
                "candidato_3": catalogo[cercanos[2]][0] if len(cercanos) > 2 else "",
            }
        )
    _escribir_csv(
        salida / "sin_match.csv",
        [
            "fila_excel",
            "nombre_en_excel",
            "pais",
            "ciudad",
            "candidato_1",
            "candidato_2",
            "candidato_3",
        ],
        pendientes,
    )

    _escribir_csv(
        salida / "autorizadas_sin_nivel.csv",
        ["fila_excel", "institucion", "pais", "ciudad", "texto_en_el_excel"],
        [
            {
                "fila_excel": por_clave[k][0]["fila"],
                "institucion": por_clave[k][0]["nombre"],
                "pais": por_clave[k][0]["pais"],
                "ciudad": por_clave[k][0]["ciudad"],
                "texto_en_el_excel": " · ".join(por_clave[k][0]["niveles_crudos"]) or "(vacío)",
            }
            for k in sorted(por_clave)
            if not por_clave[k][0]["niveles"]
        ],
    )

    _escribir_csv(
        salida / "cruces_por_variante.csv",
        ["nombre_en_excel", "nombre_en_catalogo"],
        [
            {
                "nombre_en_excel": por_clave[k][0]["nombre"],
                "nombre_en_catalogo": catalogo[v][0],
            }
            for k, v in sorted(equivalencias.items())
        ],
    )

    _escribir_csv(
        salida / "duplicados_en_excel.csv",
        ["clave", "filas", "nombres", "ciudades"],
        [
            {
                "clave": k,
                "filas": " · ".join(str(x["fila"]) for x in v),
                "nombres": " · ".join(x["nombre"] for x in v),
                "ciudades": " · ".join(str(x["ciudad"]) for x in v),
            }
            for k, v in sorted(duplicados.items())
        ],
    )

    _escribir_csv(
        salida / "niveles_sin_mapear.csv",
        ["texto", "veces", "filas"],
        [
            {
                "texto": t,
                "veces": n,
                "filas": " · ".join(
                    str(f["fila"]) for f in filas if t in f["niveles_sin_mapear"]
                ),
            }
            for t, n in todos_sin_mapear.most_common()
        ],
    )
    print(f"CSV de revision en: {salida.resolve()}")
    print("   sin_match.csv · duplicados_en_excel.csv · niveles_sin_mapear.csv")
    print()

    if not args.commit:
        print("SIMULACRO · no se escribio nada. Repetir con --commit para aplicar.")
        db.close()
        return 0

    # ── Respaldo del estado actual ──────────────────────────────────────────
    # "Reversible" tiene que ser un archivo, no una intención. Esto guarda qué
    # estaba activo ANTES de tocar nada · con eso se puede volver exactamente al
    # estado previo, no a una aproximación.
    respaldo = []
    for tabla, col in (
        ("institutions_catalog", "active"),
        ("programs", "active"),
        ("programas_investigados", "activo"),
    ):
        for r in db.execute(text(f"select id, {col} from {tabla}")):
            respaldo.append({"tabla": tabla, "id": str(r[0]), "activo_antes": r[1]})
    _escribir_csv(salida / "backup_estado_activo.csv", ["tabla", "id", "activo_antes"], respaldo)
    print(f"Respaldo del estado previo: {(salida / 'backup_estado_activo.csv').resolve()}")
    print(f"   {len(respaldo)} filas · permite revertir al estado exacto de antes.")
    print()

    # ── Aplicar ─────────────────────────────────────────────────────────────
    # Un UPDATE por grupo, no uno por fila. La primera versión hacía ~18.000
    # UPDATEs de una fila; contra un Neon remoto cada uno es un viaje de red y el
    # script no terminaba en 10 minutos. Aquí son ~50 sentencias en total.
    filas_cat = list(db.execute(text("select id, name from institutions_catalog")))
    por_niveles: Dict[str, List[str]] = defaultdict(list)
    ids_fuera: List[str] = []
    for r in filas_cat:
        k = clave_nombre(r[1])
        if k in claves_autorizadas:
            por_niveles[json.dumps(niveles_por_clave.get(k, []))].append(str(r[0]))
        else:
            ids_fuera.append(str(r[0]))
    revisadas = len(filas_cat)

    if ids_fuera:
        _update_por_lotes(
            db,
            "update institutions_catalog set active = false, "
            "niveles_autorizados = null, updated_at = now() "
            "where id = any(cast(:ids as uuid[]))",
            ids_fuera,
        )
    for niveles_json, ids in por_niveles.items():
        _update_por_lotes(
            db,
            "update institutions_catalog set active = true, "
            "niveles_autorizados = cast(:extra as jsonb), updated_at = now() "
            "where id = any(cast(:ids as uuid[]))",
            ids,
            extra=niveles_json,
        )

    # Las que Verónica autorizó y no existían · se crean con lo que trae el Excel
    # y nada más. `source_sheet` las deja rastreables para poder fusionarlas si
    # alguna resulta ser una que ya estaba con otro nombre.
    creadas = []
    for k in sorted(no_cruzan):
        f = por_clave[k][0]
        db.execute(
            text(
                "insert into institutions_catalog "
                "(id, name, category, country, country_raw, city, partner_group, "
                " niveles_autorizados, programs_offered, source_sheet, active, "
                " created_at, updated_at) "
                "values (gen_random_uuid(), :name, :cat, :pais, :pais_crudo, :ciudad, :grupo, "
                " cast(:niveles as jsonb), cast(:crudos as jsonb), "
                " 'catalogo_autorizado', true, now(), now())"
            ),
            {
                "name": f["nombre"],
                "cat": f["categoria"],
                "pais": f["pais"],
                "pais_crudo": f["pais_crudo"],
                "ciudad": f["ciudad"],
                "grupo": f["grupo"] if f["en_grupo"] else None,
                "niveles": json.dumps(niveles_por_clave.get(k, [])),
                "crudos": json.dumps(f["niveles_crudos"]),
            },
        )
        creadas.append(f["nombre"])

    # `programs` y `programas_investigados` se apagan por INSTITUCION, no por
    # fila: la autorización es de la institución, y así un re-run es idempotente.
    # ── El filtro por NIVEL, que es la mitad nueva del archivo ──────────────
    #
    # La autorización no es solo "esta institución sí": es "de esta institución,
    # estos niveles". Si de FIU solo se pueden vender pregrados, sus maestrías no
    # deberían aparecerle al estudiante. `busqueda_programas` filtra por
    # `pi.activo`, así que la regla se aplica aquí y la consulta no cambia.
    #
    # Regla para las que no declaran nivel: se apagan sus programas. Ausencia de
    # autorización no es autorización · el riesgo de que un asesor cotice algo que
    # la agencia no puede vender pesa más que el de mostrar de menos, y las 47
    # quedan listadas para que el cliente complete la columna.
    for tabla, col_id, col_inst, col_activo in (
        ("programs", "id", "institution", "active"),
        ("programas_investigados", "id", "institucion", "activo"),
    ):
        dentro: List[str] = []
        fuera: List[str] = []
        col_nivel = ", nivel" if tabla == "programas_investigados" else ""
        for r in db.execute(text(f"select {col_id}, {col_inst}{col_nivel} from {tabla}")):
            if tabla == "programas_investigados":
                autorizada = _investigado_autorizado(r[1], r[2])
            else:
                autorizada = clave_nombre(r[1] or "") in claves_autorizadas
            (dentro if autorizada else fuera).append(str(r[0]))
        if fuera:
            _update_por_lotes(
                db,
                f"update {tabla} set {col_activo} = false "
                f"where {col_id} = any(cast(:ids as uuid[]))",
                fuera,
            )
        if dentro:
            _update_por_lotes(
                db,
                f"update {tabla} set {col_activo} = true "
                f"where {col_id} = any(cast(:ids as uuid[]))",
                dentro,
            )

    db.commit()
    print(
        f"APLICADO · {revisadas} instituciones revisadas · {len(creadas)} creadas · "
        f"{activas_finales} activas · prioridad queda NULL (sin insumo del cliente)."
    )
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
