"""Cuelga cada programa investigado de la ficha del catálogo a la que pertenece.

    python scripts/enlazar_programas_ofertas.py            # simulacro
    python scripts/enlazar_programas_ofertas.py --confirm  # escribe

**El enlace NO se resuelve comparando nombres de institución.** Los agentes
escribieron el nombre que verificaron en el sitio real y la ficha guarda el que
tenía el cliente, así que sólo 183 de 306 coinciden. Los otros 123 son la misma
institución escrita distinta ("Ahts Training & Education" es "Alliance College",
"USQ" es "University of Southern Queensland"), y emparejarlos por parecido de
texto es justo el tipo de acierto-aproximado que mete los programas de una
institución bajo otra.

La llave buena ya existía y estaba sin usar: **cada programa recuerda su lote**, y
el archivo del lote (`lotes_extraccion/ext_NN.json`) guarda `institucion_ficha`,
que es literalmente el nombre con el que la ficha entró al catálogo. O sea que el
camino es:

    programa → lote → ficha del lote → programs.name

Dentro de un lote hay ~10 instituciones, así que emparejar el nombre del agente
con el `nombre_real` de su propia ficha es casi determinista, y de ahí se salta
al nombre original sin adivinar nada.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import unicodedata
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.services import paises as paises_mod  # noqa: E402

RAIZ = os.path.join(os.path.dirname(__file__), "..", "data", "catalogo")

# Torrens se reextrajo aparte (lote 35) y su ficha vive en el lote que la extrajo
# primero · mismo caso que en `enriquecer_programas.py`.
LOTE_HUERFANO = {"35": "11"}

_RUIDO = {
    "the", "of", "and", "for", "de", "la", "el", "los", "las", "y",
    "university", "college", "school", "institute", "academy", "centre",
    "center", "campus", "international", "australia", "australian", "pty",
    "ltd", "inc", "limited", "group", "education", "training", "studies",
    "trading", "as", "t", "a",
}


def _norm(s: str) -> str:
    s = (s or "").replace("’", "'").replace("ʼ", "'")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.replace("'", "")
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def _tokens(s: str) -> set:
    return {t for t in _norm(s).split() if t and t not in _RUIDO}


def _parecido(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 1.0 if _norm(a) == _norm(b) else 0.0
    comun = len(ta & tb)
    return max(comun / len(ta | tb), comun / min(len(ta), len(tb)))


UMBRAL = 0.5


def _renombres() -> dict:
    """Los renombres que ya aplicamos al catálogo · nombre viejo → nombre nuevo.

    El archivo del lote guarda el nombre con el que la ficha entró al catálogo,
    pero `aplicar_correcciones.py` renombró 30 fichas contra el nombre real de
    cada institución. Buscar el nombre viejo en `programs` falla, y falla en
    silencio: quince instituciones se quedaban sin enlazar por un arreglo
    nuestro. Con este mapa, el nombre viejo del lote encuentra la ficha nueva.
    """
    ruta = os.path.join(RAIZ, "CORRECCIONES.json")
    if not os.path.exists(ruta):
        return {}
    datos = json.load(open(ruta, encoding="utf-8"))
    return {
        _norm(c["valor_actual"]): c["valor_nuevo"]
        for c in datos.get("correcciones", [])
        if c.get("campo") == "name"
    }


def _fichas_por_lote() -> dict:
    out = {}
    for ruta in sorted(glob.glob(os.path.join(RAIZ, "lotes_extraccion", "ext_*.json"))):
        lote = re.search(r"ext_(\d+)", ruta).group(1)
        out[lote] = json.load(open(ruta, encoding="utf-8"))
    for huerfano, origen in LOTE_HUERFANO.items():
        if origen in out:
            out[huerfano] = out[origen]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    fichas = _fichas_por_lote()
    renombres = _renombres()
    db = SessionLocal()
    try:
        pares = db.execute(text(
            "SELECT DISTINCT lote, institucion FROM programas_investigados"
        )).all()

        # El catálogo se indexa por nombre normalizado. Si dos fichas activas
        # normalizan igual, se descarta ese nombre en vez de elegir una: colgar
        # los programas de la institución equivocada es peor que no colgarlos.
        cat = {}
        ambiguos = set()
        for pid, nombre in db.execute(text(
            "SELECT id, name FROM programs WHERE active"
        )):
            k = _norm(nombre)
            if k in cat:
                ambiguos.add(k)
            cat[k] = pid
        for k in ambiguos:
            cat.pop(k, None)

        # El pais de cada ficha, y el pais dominante de los programas de cada
        # institucion · para el guardarrail de mas abajo.
        pais_de_ficha = {i: c for i, c in db.execute(text(
            "SELECT id, country FROM programs WHERE active"))}
        pais_dominante = {}
        for l, i, pa, n in db.execute(text(
            "SELECT lote, institucion, pais, count(*) n FROM programas_investigados "
            "GROUP BY lote, institucion, pais ORDER BY n DESC")):
            pais_dominante.setdefault((l, i), pa)

        enlaces, motivos = {}, Counter()
        for lote, institucion in pares:
            # 1 · del nombre del agente a la ficha de su propio lote.
            mejor, punto = None, 0.0
            for f in fichas.get(lote, []):
                for campo in ("nombre_real", "institucion_ficha"):
                    s = _parecido(institucion, f.get(campo) or "")
                    if s > punto:
                        mejor, punto = f, s
            if not mejor or punto < UMBRAL:
                motivos["no se encontro la ficha del lote"] += 1
                continue

            # 2 · del nombre original de la ficha a la fila de `programs`, por
            # tres vías en orden de confianza: el nombre con el que entró al
            # catálogo, el nombre nuevo si nosotros la renombramos, y el nombre
            # verificado en el sitio.
            candidatos = [
                mejor.get("institucion_ficha"),
                renombres.get(_norm(mejor.get("institucion_ficha") or "")),
                mejor.get("nombre_real"),
            ]
            pid = None
            for cand in candidatos:
                if cand:
                    pid = cat.get(_norm(cand))
                    if pid is not None:
                        break
            if pid is None:
                motivos["la ficha ya no esta activa en el catalogo"] += 1
                continue

            # 3 · El país tiene que cuadrar.
            #
            # El emparejamiento por tokens acierta casi siempre, pero cuando
            # falla lo hace de forma convincente: "Kings Education" (colegios en
            # Reino Unido) se colgó de "King's College" (Estados Unidos) porque
            # comparten la palabra "kings". Son 58 programas bajo la institución
            # equivocada, y nada en el nombre lo delata.
            #
            # El país es el desempate barato: si la ficha dice un país y sus
            # supuestos programas están en otro, no son la misma institución. Se
            # excluyen las redes multi-destino, donde la discrepancia es real y
            # esperada.
            pais_ficha = paises_mod.normalizar(pais_de_ficha.get(pid))
            pais_prog = pais_dominante.get((lote, institucion))
            if (
                pais_ficha and pais_prog
                and paises_mod.VARIOS not in (pais_ficha, pais_prog)
                and pais_ficha != pais_prog
            ):
                motivos[f"el pais no cuadra ({pais_ficha} vs {pais_prog})"] += 1
                continue

            enlaces[(lote, institucion)] = pid

        total = db.execute(text(
            "SELECT count(*) FROM programas_investigados")).scalar()
        cubiertos = 0
        for (lote, institucion), pid in enlaces.items():
            n = db.execute(text(
                "SELECT count(*) FROM programas_investigados "
                "WHERE lote = :l AND institucion = :i"
            ), {"l": lote, "i": institucion}).scalar()
            cubiertos += n
            if args.confirm:
                db.execute(text(
                    "UPDATE programas_investigados SET program_id = :p "
                    "WHERE lote = :l AND institucion = :i"
                ), {"p": pid, "l": lote, "i": institucion})
        if args.confirm:
            db.commit()

        print(f"instituciones (lote+nombre) : {len(pares)}")
        print(f"  enlazadas a una ficha     : {len(enlaces)}")
        for m, n in motivos.most_common():
            print(f"    {n:>4}  {m}")
        print(f"\nprogramas cubiertos: {cubiertos} de {total} "
              f"({round(100 * cubiertos / total)}%)")
        if ambiguos:
            print(f"\n  {len(ambiguos)} nombres de ficha estaban duplicados en el "
                  f"catalogo y se descartaron para no colgar de la equivocada")
        if not args.confirm:
            print("\n--- SIMULACRO · nada se escribio. Repite con --confirm ---")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
