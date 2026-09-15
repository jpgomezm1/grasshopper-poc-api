"""Genera la glosa de cada programa · el puente entre el catálogo y el estudiante.

Qué problema resuelve
---------------------
El vector de un programa se construye con `título + área + nivel + institución`.
Son ~15 palabras y representan un **rótulo**, no un programa. Funciona mientras
el estudiante escriba en el vocabulario del catálogo, y se rompe en cuanto habla
como habla de verdad. Medido:

    consulta: "me interesa cómo piensa la gente"
    Psychology BSc, sólo título+área+nivel ....... 0.256
    Psychology BSc + glosa ....................... 0.350   (+37%)
    (lo que gana hoy esa consulta: Social and Political Theory, 0.324)

Sin glosa, la búsqueda le ofrece teoría política a quien pregunta por psicología.

Por qué esto NO es alucinar
---------------------------
Se le pide al modelo que describa **el campo de estudio**, no el programa. No
sabe cuánto dura este máster ni qué piden para entrar, y no se le pregunta. Sabe
qué es la psicología. El prompt prohíbe explícitamente duración, requisitos,
costo, ciudad y empleabilidad, y ordena responder `(sin glosa)` cuando el título
no permite saber de qué campo es — que es lo correcto para "Foundation
Programme" o un código suelto.

Por qué `gpt-4.1-nano`
----------------------
Es el más barato de los probados **y el que mejor funciona**, que no es lo
habitual. `gpt-4o-mini` escribía "En psicología se estudia cómo piensan las
personas" (+25%) y `nano` "cómo piensan, sienten y se comportan las personas"
(+37%). La diferencia es que el primero **renombra la disciplina** —palabra que
ya está en el título, así que no aporta señal— y el segundo la traduce. Eso está
escrito como la regla principal del prompt.

Coste medido en tokens reales, en lotes de 50: ~10 de entrada y ~23 de salida por
programa. Para 33.552 programas, del orden de USD 0,40.

Uso
---
    python scripts/generar_glosas.py --limit 50    # prueba
    python scripts/generar_glosas.py               # todos los que falten

Es **reanudable**: sólo toca las filas con `glosa IS NULL`. Después hay que
regenerar los embeddings de lo que cambió — el script lo recuerda al terminar.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from openai import AsyncOpenAI  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402

MODELO = "gpt-4.1-nano"
POR_LOTE = 50
#: Cuántos lotes se piden a la vez · ver el comentario en el bucle principal.
CONCURRENCIA = 8
#: Lo que el modelo devuelve cuando el título no permite saber el campo. Se
#: guarda tal cual —y no como NULL— para que el script sea reanudable: un NULL
#: se volvería a intentar en cada corrida y costaría lo mismo cada vez.
SIN_GLOSA = "(sin glosa)"

_PROMPT = None


def _prompt() -> str:
    global _PROMPT
    if _PROMPT is None:
        ruta = os.path.join(os.path.dirname(__file__), "..", "app", "prompts",
                            "glosa_programa.txt")
        with open(ruta, encoding="utf-8") as fh:
            _PROMPT = fh.read()
    return _PROMPT


def _limpiar(linea: str) -> Optional[str]:
    """Quita la numeración y descarta lo que no sirve como glosa."""
    t = re.sub(r"^\s*\d+[\.\)]\s*", "", linea).strip().strip('"').strip()
    if not t:
        return None
    # Una glosa larguísima suele ser el modelo explicándose en vez de glosar;
    # y una de dos palabras no tiende ningún puente.
    if len(t) > 400 or len(t.split()) < 4:
        return SIN_GLOSA if SIN_GLOSA in t.lower() or "sin glosa" in t.lower() else None
    return t


async def _glosar(cli: AsyncOpenAI, filas: List[tuple]) -> List[Optional[str]]:
    listado = "\n".join(
        f"{i}. {nombre} · {area or 'sin área'} · {nivel}"
        for i, (_, nombre, area, nivel) in enumerate(filas, start=1)
    )
    r = await cli.chat.completions.create(
        model=MODELO, temperature=0.2, max_tokens=POR_LOTE * 45,
        messages=[{"role": "user", "content": _prompt().format(programas=listado)}],
    )
    # Se empareja por el NÚMERO de cada línea, no por su posición.
    #
    # Exigir "una línea por programa" descartaba el lote entero cuando el modelo
    # partía una glosa larga en dos renglones — y eso pasaba en el **14,6% de
    # los lotes**, o sea 4.901 programas sin glosa en la primera pasada. Emparejar
    # por posición una lista desalineada sería peor todavía: le pondría a cada
    # programa la glosa de otro.
    #
    # Con el número, una línea de continuación (sin número) se pega a la
    # anterior y un programa que el modelo se saltó simplemente se queda sin
    # glosa, sin arrastrar a los 49 restantes.
    por_indice: dict = {}
    actual = None
    for linea in (r.choices[0].message.content or "").splitlines():
        if not linea.strip():
            continue
        m = re.match(r"\s*(\d+)[\.\)]\s*(.*)", linea)
        if m:
            actual = int(m.group(1))
            por_indice[actual] = m.group(2).strip()
        elif actual is not None:
            por_indice[actual] = (por_indice[actual] + " " + linea.strip()).strip()
    return [_limpiar(por_indice.get(i, "")) for i in range(1, len(filas) + 1)]


async def main() -> int:
    ap = argparse.ArgumentParser(description="Genera las glosas de los programas")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--solo-activos", action="store_true",
                    help="sólo los que se muestran hoy · ahorra las filas ocultas")
    args = ap.parse_args()

    s = get_settings()
    if not s.openai_api_key:
        print("falta OPENAI_API_KEY")
        return 1
    cli = AsyncOpenAI(api_key=s.openai_api_key)
    db = SessionLocal()
    filtro_activo = "AND activo" if args.solo_activos else ""
    try:
        pendientes = db.execute(text(
            f"SELECT count(*) FROM programas_investigados "
            f"WHERE glosa IS NULL {filtro_activo}"
        )).scalar()
        print(f"sin glosa: {pendientes}")
        if not pendientes:
            return 0

        hechos = descartados = 0
        objetivo = args.limit or pendientes
        while hechos < objetivo:
            # Se traen varios lotes y se piden **a la vez**.
            #
            # Secuencial, cada lote tarda lo que tarda el modelo en escribir 50
            # líneas (~15 s) y el catálogo entero son 671 lotes: de dos a cuatro
            # horas esperando a un servidor. Es la misma lección del backfill de
            # embeddings, donde ir de uno en uno multiplicaba por siete el total.
            # `gpt-4.1-nano` aguanta de sobra esta concurrencia.
            cuantos = min(CONCURRENCIA * POR_LOTE, objetivo - hechos)
            filas = list(db.execute(text(
                f"SELECT id, nombre, area, nivel FROM programas_investigados "
                f"WHERE glosa IS NULL {filtro_activo} "
                f"ORDER BY institucion, nombre LIMIT :n"
            ), {"n": cuantos}))
            if not filas:
                break

            lotes = [filas[i:i + POR_LOTE] for i in range(0, len(filas), POR_LOTE)]
            resultados = await asyncio.gather(
                *(_glosar(cli, lote) for lote in lotes), return_exceptions=True
            )
            ids, textos = [], []
            for lote, glosas in zip(lotes, resultados):
                if isinstance(glosas, Exception):
                    # Un lote que falla no tumba la corrida: sus filas quedan con
                    # `glosa IS NULL` y las recoge la siguiente pasada.
                    descartados += len(lote)
                    continue
                for (pid, *_), g in zip(lote, glosas):
                    if g is None:
                        descartados += 1
                        continue
                    ids.append(str(pid))
                    textos.append(g)
            if ids:
                # Un viaje por lote, no uno por fila · la misma lección que el
                # backfill de embeddings, donde escribir fila a fila multiplicaba
                # por siete el tiempo total.
                db.execute(text(
                    "UPDATE programas_investigados AS pi SET glosa = v.g "
                    "  FROM (SELECT unnest(CAST(:ids AS uuid[])) AS id, "
                    "               unnest(CAST(:gs AS text[])) AS g) AS v "
                    " WHERE pi.id = v.id"
                ), {"ids": ids, "gs": textos})
                db.commit()
            hechos += len(filas)
            if hechos % (POR_LOTE * CONCURRENCIA) == 0 or hechos >= objetivo:
                print(f"  {hechos}/{objetivo}")

        sin = db.execute(text(
            "SELECT count(*) FROM programas_investigados WHERE glosa = :s"
        ), {"s": SIN_GLOSA}).scalar()
        print(f"\nlisto · {hechos} procesados · {descartados} lotes/filas descartados")
        print(f"con '(sin glosa)' porque el titulo no dice el campo: {sin}")
        print("\nAhora hay que regenerar los embeddings de lo que cambio:")
        print("  UPDATE programas_investigados SET embedding = NULL WHERE glosa IS NOT NULL;")
        print("  python scripts/generar_embeddings.py")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
