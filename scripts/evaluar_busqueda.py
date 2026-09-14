"""Set de referencia de la búsqueda semántica · lo que no existía y hacía falta.

Por qué
-------
`busqueda_programas.py` está lleno de constantes calibradas contra el catálogo
real —`PESO_AFINIDAD = 0.10`, `PROBES = 10`, `CANDIDATOS = 120`— y sus propios
comentarios avisan de dos cosas:

  * *"Si cambian los textos que se embeben, hay que recalibrarlo: el número
    depende del rango de similitudes que produzcan."*
  * *"No hay un set de evaluación."*

El catálogo pasó de 15.483 a 33.907 programas, o sea que el corpus contra el que
se calibró ya no existe. Y el modo en que un índice vectorial se degrada es el
peor posible para detectarlo a ojo: **sigue devolviendo resultados, sólo que
peores**. Sin un set de referencia, cambiar el índice o el peso es apostar.

Este script no juzga si un resultado es "bueno" —eso es subjetivo— sino si
cumple una expectativa **escrita de antemano**: que cierto tipo de programa
aparezca arriba, o que cierto error conocido NO aparezca. Los casos salen de los
propios comentarios de calibración, que documentan qué devolvía mal cada valor.

Uso
---
    python scripts/evaluar_busqueda.py                 # corre y muestra
    python scripts/evaluar_busqueda.py --guardar antes.json
    python scripts/evaluar_busqueda.py --comparar antes.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.database import SessionLocal  # noqa: E402
from app.services import busqueda_programas as bp, embeddings as emb  # noqa: E402


class Caso:
    """Una consulta con lo que se espera y lo que se sabe que estuvo mal.

    `espera` y `rechaza` son expresiones regulares sobre el nombre del programa.
    No se exige un programa concreto —el catálogo cambia— sino una *forma* de
    resultado, que es lo que de verdad se quiere sostener.
    """

    def __init__(self, consulta: str, espera: str, rechaza: Optional[str] = None,
                 nota: str = "", en_top: int = 5):
        self.consulta = consulta
        self.espera = espera
        self.rechaza = rechaza
        self.nota = nota
        self.en_top = en_top


# Los cinco primeros salen literalmente de los comentarios de calibración de
# `busqueda_programas.py`; el resto cubre las formas de consulta que un
# estudiante escribe de verdad y los errores que ya se cometieron una vez.
CASOS: List[Caso] = [
    # ⚠️ Este caso FALLA a propósito desde 2026-09-14, y se deja fallando.
    #
    # Con el catálogo completo (33.552 embebidos), los 10 primeros son todos
    # dibujo, ilustración y animación: **la mitad "animales" de la consulta se
    # pierde entera**. Antes salía primero "MA Children's Book Illustration",
    # que al menos rozaba las dos; ahora es el octavo.
    #
    # No es el índice ni el peso —probado con PESO_AFINIDAD de 0.00 a 0.40, el
    # top-3 no se mueve—: es el límite de representar con UN vector una consulta
    # con dos intereses. El promedio de "animales" y "dibujar" cae entre los dos
    # y no se parece del todo a ninguno (similitud 0.347, baja para este
    # corpus). Es exactamente lo que el intérprete de consulta por LLM viene a
    # resolver, separando los dos conceptos.
    #
    # Se deja rojo en vez de ablandar la expectativa: una brecha medida que se
    # ve en cada corrida vale más que una suite verde que no dice nada.
    #
    # Detalle curioso y real: "Grado Oficial en Animación" sale segundo. En
    # español "animación" y "animales" comparten raíz, así que una consulta
    # sobre animales empuja programas de animación.
    Caso("me gustan los animales pero también dibujar",
         espera=r"(animal|veterinar|zoo|wildlife|equine)",
         rechaza=r"(plant maintenance|mantenimiento de planta)",
         nota="BRECHA CONOCIDA · la consulta tiene dos intereses y un solo "
              "vector sólo representa uno. Lo resuelve el intérprete por LLM."),
    Caso("me apasiona la cocina",
         espera=r"(culinar|cocina|chef|gastronom|cookery|patisser)",
         rechaza=r"(dise[ñn]o de cocina|kitchen design)",
         nota="sin refuerzo RIASEC devolvia 'Diseño de Cocinas' (muebles)"),
    Caso("quiero ser enfermera",
         espera=r"(nursing|enfermer)",
         nota="consulta en espanol contra catalogo en ingles"),
    Caso("programación y videojuegos",
         espera=r"(game|videojueg|computer scien|software|program)"),
    Caso("emprendimiento para interioristas",
         espera=r"(interior)",
         nota="PESO_AFINIDAD alto lo adelantaba a 'Diploma de Cocina'"),
    Caso("derecho internacional",
         espera=r"(law|derecho|legal|juris)"),
    Caso("me interesa el medio ambiente y la sostenibilidad",
         espera=r"(environment|sustainab|ambient|sostenib|ecolog|climate)"),
    Caso("diseño gráfico",
         espera=r"(graphic|gr[aá]fic|design|dise[ñn]o)"),
    Caso("psicología clínica",
         espera=r"(psycholog|psicolog)"),
    Caso("aprender inglés antes de la universidad",
         espera=r"(english|ingl[eé]s|pathway|foundation|pre-?sessional|eap)"),
    Caso("arquitectura",
         espera=r"(architect|arquitect)"),
    Caso("negocios internacionales",
         espera=r"(business|negocio|management|administrac|commerce)"),
    Caso("quiero trabajar con niños",
         espera=r"(education|teach|child|early years|primary|docen|educac|pedagog)"),
    Caso("ingeniería mecánica",
         espera=r"(mechanical|mec[aá]nic|engineering|ingenier)"),
    Caso("cine y producción audiovisual",
         espera=r"(film|cinema|media production|audiovisual|cine|screen)"),
    Caso("marketing digital",
         espera=r"(marketing|digital|publicid|advertis)"),
    Caso("me gusta la música",
         espera=r"(music|m[uú]sic|sound|audio)"),
    Caso("finanzas y contabilidad",
         espera=r"(financ|account|contab|banking)"),
    Caso("turismo y hotelería",
         espera=r"(tourism|hospitality|hotel|turism|hoteler)"),
    Caso("inteligencia artificial",
         espera=r"(artificial intelligence|\bai\b|machine learning|data scien|inteligencia)"),
]


async def correr(limite: int = 10) -> dict:
    db = SessionLocal()
    salida = {"casos": [], "resumen": {}}
    aciertos = fallos = rechazos_violados = 0
    try:
        for c in CASOS:
            v = await emb.embeber_uno(c.consulta)
            res = bp.buscar(db, vector_perfil=v, codigos_riasec=(),
                            filtros=bp.Filtros(), limite=limite)
            nombres = [r.nombre for r in res]
            top = nombres[: c.en_top]

            ok = any(re.search(c.espera, n, re.I) for n in top)
            violado = bool(c.rechaza) and any(
                re.search(c.rechaza, n, re.I) for n in top)
            aciertos += ok
            fallos += not ok
            rechazos_violados += violado

            salida["casos"].append({
                "consulta": c.consulta, "cumple": ok, "rechazo_violado": violado,
                "nota": c.nota, "top": top,
                "similitud_1": res[0].similitud if res else None,
                "similitud_n": res[-1].similitud if res else None,
            })
            marca = "ok " if ok and not violado else "MAL"
            print(f"  {marca}  {c.consulta[:44]:<44} -> {top[0][:40] if top else '(vacio)'}")
            if not ok or violado:
                for n in top:
                    print(f"          {n[:66]}")
    finally:
        db.close()

    sims = [c["similitud_1"] for c in salida["casos"] if c["similitud_1"]]
    salida["resumen"] = {
        "casos": len(CASOS), "aciertos": aciertos, "fallos": fallos,
        "rechazos_violados": rechazos_violados,
        "similitud_top1_media": round(sum(sims) / len(sims), 4) if sims else None,
        "similitud_top1_min": round(min(sims), 4) if sims else None,
        "similitud_top1_max": round(max(sims), 4) if sims else None,
    }
    return salida


def main() -> int:
    ap = argparse.ArgumentParser(description="Evalua la busqueda semantica")
    ap.add_argument("--guardar", help="escribe el resultado a un JSON")
    ap.add_argument("--comparar", help="compara contra un JSON anterior")
    ap.add_argument("--limite", type=int, default=10)
    args = ap.parse_args()

    print("=" * 72)
    print("EVALUACION DE LA BUSQUEDA SEMANTICA")
    print("=" * 72)
    r = asyncio.run(correr(args.limite))
    s = r["resumen"]
    print()
    print(f"cumplen: {s['aciertos']}/{s['casos']} · fallan: {s['fallos']} · "
          f"rechazos violados: {s['rechazos_violados']}")
    print(f"similitud del primero · media {s['similitud_top1_media']} "
          f"(min {s['similitud_top1_min']} · max {s['similitud_top1_max']})")

    if args.comparar and os.path.exists(args.comparar):
        with open(args.comparar, encoding="utf-8") as fh:
            antes = json.load(fh)
        print()
        print("=" * 72)
        print("COMPARACION CON", args.comparar)
        print("=" * 72)
        a = {c["consulta"]: c for c in antes["casos"]}
        for c in r["casos"]:
            v = a.get(c["consulta"])
            if not v:
                continue
            if v["cumple"] != c["cumple"]:
                flecha = "MEJORA " if c["cumple"] else "REGRESION"
                print(f"  {flecha}  {c['consulta'][:44]}")
                print(f"      antes: {v['top'][0][:56] if v['top'] else '(vacio)'}")
                print(f"      ahora: {c['top'][0][:56] if c['top'] else '(vacio)'}")
        sa, sn = antes["resumen"], r["resumen"]
        print(f"\n  cumplen  {sa['aciertos']}/{sa['casos']}  ->  "
              f"{sn['aciertos']}/{sn['casos']}")
        print(f"  similitud media  {sa['similitud_top1_media']}  ->  "
              f"{sn['similitud_top1_media']}")

    if args.guardar:
        with open(args.guardar, "w", encoding="utf-8") as fh:
            json.dump(r, fh, ensure_ascii=False, indent=2)
        print(f"\nguardado en {args.guardar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
