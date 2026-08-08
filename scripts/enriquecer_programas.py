"""Cuarta pasada · le devuelve a cada programa el país de su institución.

La extracción sacó `institucion | nombre | nivel | area | duracion |
codigo_oficial | url_fuente`. **No sacó país**, y sin país no existe el primer
filtro del recomendador ("¿a dónde te quieres ir?"). El país sí está en el
catálogo de origen (`lotes_extraccion/ext_NN.json`), así que esto es un join.

    python scripts/enriquecer_programas.py

Lee  `programas_final.csv`
Deja `programas_con_pais.csv` + `programas_sin_pais.csv`

**El join se hace dentro del lote, no contra las 337 instituciones.** Cada
programa recuerda de qué lote salió y cada lote trae ~10 fichas, así que el
espacio de búsqueda pasa de 337 candidatos a 10. Emparejar por nombre contra
337 daba 221 de 306 y obligaba a fuzzy matching agresivo —justo el tipo de
"acierta el 90%" que mete a un estudiante en el país equivocado—; dentro del
lote, el nombre más parecido casi siempre es el correcto y se puede exigir un
umbral alto sin perder cobertura.

Lo que no empareje con confianza **no se inventa**: sale a `programas_sin_pais.csv`
para revisarlo a mano. Un país adivinado es peor que un país vacío.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import unicodedata
from collections import Counter

RAIZ = os.path.join(os.path.dirname(__file__), "..", "data", "catalogo")

# Torrens se reextrajo aparte (lote 35) y no tiene su propio ext_35.json · su
# ficha vive en el lote que la extrajo primero.
LOTE_HUERFANO = {"35": "11"}

# ---------------------------------------------------------------------------
# Las 12 fichas del cliente que no traen país
# ---------------------------------------------------------------------------
# De las 337, doce tienen el campo `pais` vacío. No es un problema de
# emparejamiento —la ficha se encuentra perfecta— sino un hueco del catálogo
# original, y se lleva por delante 690 programas si se deja así (510 solo de
# Queen's University Belfast).
#
# Se rellenan a mano y con la evidencia escrita al lado, no con una regla sobre
# el dominio: un `.edu.au` es señal fuerte pero no prueba, y este es justo el
# campo que decide a qué país viaja un estudiante. Diez de las doce dicen el
# país en su propio nombre ya verificado contra el sitio.
PAIS_FALTANTE = {
    # El nombre verificado empieza por "Australian" / "Australia" + RTO o CRICOS,
    # que son registros australianos.
    "Australia Institute of Business and Technology": "Australia",
    "Australian Health and Management Institute": "Australia",
    "Australian College of IT & Institute of Film and Television": "Australia",
    "Australian College of Agriculture & Horticulture": "Australia",
    "Academy of Interactive Technology": "Australia",
    "Australian International College Of Language": "Australia",
    "Australian Learning Group": "Australia",
    # Universidad de Tasmania · Tasmania es un estado australiano.
    "University of Tasmania International Pathway College": "Australia",
    # "Atlantic Canada" en el nombre · dominio studyatlantic.com.
    "Atlantic Canada Language Academy": "Canada",
    # Belfast · dominio qub.ac.uk (`.ac.uk` es el registro académico británico).
    "Queen's University Belfast": "UK",
    # La ficha original la llamaba "Speos, Paris Photographic Institute" y sus
    # programas publican códigos RNCP, el registro nacional francés.
    "Speos International Photography School": "France",
}


def _norm(s: str) -> str:
    """Sin tildes, sin puntuación, en minúsculas · para comparar nombres.

    Los apóstrofos se **borran**, no se convierten en espacio, y esa línea vale
    510 programas: el CSV trae `Queen's` con apóstrofo tipográfico (U+2019), que
    al pasar a ASCII se pierde y deja `queens`; la ficha lo trae recto y dejaba
    `queen s`. Dos tokens distintos para la misma palabra, y Queen's University
    Belfast entera se quedaba sin país.
    """
    s = (s or "").replace("’", "'").replace("ʼ", "'")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.replace("'", "")
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


# Palabras que aparecen en casi todos los nombres y no distinguen nada: si se
# cuentan, "Australian College of X" y "Australian Institute of Y" se parecen
# mucho más de lo que son.
_RUIDO = {
    "the", "of", "and", "for", "de", "la", "el", "los", "las", "y",
    "university", "college", "school", "institute", "academy", "centre",
    "center", "campus", "international", "australia", "australian", "pty",
    "ltd", "inc", "limited", "group", "education", "training", "studies",
    "trading", "as", "t", "a",
}


def _tokens(s: str) -> set:
    return {t for t in _norm(s).split() if t and t not in _RUIDO}


def _parecido(a: str, b: str) -> float:
    """Cuánto se parecen dos nombres de institución · 1.0 es idéntico.

    Se toma el mayor entre Jaccard y **contención** (intersección sobre el lado
    corto). Jaccard solo no sirve aquí porque media docena de fichas se
    referencian por sigla: `UniSQ` contra "University of Southern Queensland
    (UniSQ)" da 0.33 y se caía, aunque la sigla esté literalmente dentro del
    nombre largo. La contención da 1.0, que es la respuesta correcta.

    La contención es más laxa y por sí sola sería peligrosa —cualquier nombre de
    una palabra pescaría fichas ajenas—, pero aquí solo compite contra las ~10
    fichas de su propio lote, no contra las 337.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        # Nombres que son puras siglas o puro ruido · cae a comparación cruda.
        return 1.0 if _norm(a) == _norm(b) else 0.0
    comun = len(ta & tb)
    return max(comun / len(ta | tb), comun / min(len(ta), len(tb)))


def _fichas_por_lote() -> dict:
    out = {}
    for ruta in sorted(glob.glob(os.path.join(RAIZ, "lotes_extraccion", "ext_*.json"))):
        lote = re.search(r"ext_(\d+)", ruta).group(1)
        out[lote] = json.load(open(ruta, encoding="utf-8"))
    for huerfano, origen in LOTE_HUERFANO.items():
        if origen in out:
            out[huerfano] = out[origen]
    return out


# Por debajo de esto no se acepta el emparejamiento. 0.5 significa que la mitad
# de las palabras significativas coinciden; con 10 candidatos por lote, un falso
# positivo a ese nivel es muy improbable, y lo que quede fuera se revisa a mano.
UMBRAL = 0.5


def main() -> int:
    fichas = _fichas_por_lote()
    entrada = os.path.join(RAIZ, "programas_final.csv")
    with open(entrada, encoding="utf-8") as fh:
        progs = list(csv.DictReader(fh))

    # Se resuelve una vez por (lote, institución), no por programa: son 306
    # instituciones contra 15.483 filas.
    cache: dict = {}
    for p in progs:
        clave = (p["lote"], p["institucion"])
        if clave in cache:
            continue
        mejor, punto = None, 0.0
        for f in fichas.get(p["lote"], []):
            for campo in ("nombre_real", "institucion_ficha"):
                s = _parecido(p["institucion"], f.get(campo) or "")
                if s > punto:
                    mejor, punto = f, s
        cache[clave] = (mejor, punto)

    # El país faltante se busca por el nombre de la ficha y por el que usó el
    # agente: los dos aparecen en PAIS_FALTANTE según el caso.
    relleno = {_norm(k): v for k, v in PAIS_FALTANTE.items()}

    def _pais_de(ficha: dict, usado: str) -> str:
        p = (ficha.get("pais") or "").strip()
        if p:
            return p
        for cand in (ficha.get("nombre_real"), ficha.get("institucion_ficha"), usado):
            n = _norm(cand or "")
            for clave, valor in relleno.items():
                if n.startswith(clave) or clave.startswith(n):
                    return valor
        return ""

    con, sin, rellenados = [], [], 0
    for p in progs:
        ficha, punto = cache[(p["lote"], p["institucion"])]
        if not (ficha and punto >= UMBRAL):
            p["motivo_sin_pais"] = "no se encontró la ficha de la institución"
            sin.append(p)
            continue
        traia = bool((ficha.get("pais") or "").strip())
        p["pais"] = _pais_de(ficha, p["institucion"])
        p["ciudad"] = ficha.get("ciudad") or ""
        p["dominio"] = ficha.get("dominio") or ""
        if p["pais"]:
            rellenados += 0 if traia else 1
            con.append(p)
        else:
            p["motivo_sin_pais"] = "la ficha del cliente no trae país"
            sin.append(p)

    campos = list(progs[0].keys())
    for extra in ("pais", "ciudad", "dominio", "motivo_sin_pais"):
        if extra not in campos:
            campos.append(extra)

    with open(os.path.join(RAIZ, "programas_con_pais.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(con)
    with open(os.path.join(RAIZ, "programas_sin_pais.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(sin)

    print(f"programas          : {len(progs)}")
    print(f"con pais           : {len(con)}  ({round(100*len(con)/len(progs))}%)")
    print(f"  de esos, rellenados a mano: {rellenados}")
    print(f"sin pais           : {len(sin)}")
    print(f"\npaises distintos   : {len(set(p['pais'] for p in con))}")
    for k, n in Counter(p["pais"] for p in con).most_common(20):
        print(f"    {n:>5}  {k}")
    if sin:
        # Los dos motivos se cuentan aparte porque se arreglan distinto: uno es
        # un problema de emparejamiento nuestro, el otro un hueco del cliente.
        print("\nsin pais, por motivo:")
        for k, n in Counter(p["motivo_sin_pais"] for p in sin).most_common():
            print(f"    {n:>5}  {k}")
        print("\ninstituciones sin resolver:")
        for k, n in Counter(p["institucion"] for p in sin).most_common(15):
            print(f"    {n:>5}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
