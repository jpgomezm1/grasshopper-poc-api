"""Mide la calidad de las recomendaciones · el arnés que hoy no existía.

    python scripts/evaluar_recomendaciones.py

Hasta ahora no había forma de saber si una recomendación era buena. El peso de la
afinidad RIASEC se calibró mirando cuatro consultas a ojo. Para el corazón del
producto eso no alcanza: cada cambio posterior sería una corazonada, y no se
podría responder "¿el buscador de hoy es mejor que el de la semana pasada?".

Esto evalúa en **dos niveles, y la diferencia importa**:

## 1 · Reglas duras · no necesitan a nadie

Son cosas que están mal sin discusión y que se pueden comprobar solas: ofrecerle
una maestría a alguien que está en el colegio, devolver un programa de otro país
del que pidió, mostrar una institución que la agencia dio de baja. Aquí no hay
gusto, hay error. **Cualquier fallo de esta sección es un bug**, y estas reglas
corren en cada cambio sin que nadie tenga que etiquetar nada.

## 2 · Relevancia · sí necesita a alguien que sepa

"¿Es buena esta recomendación para esta persona?" no lo decide una regla. Se
compara contra `data/evaluacion/casos.json`, donde alguien de la agencia marca
qué programas esperaría ver para un perfil dado. Mientras ese archivo esté vacío,
esta sección lo dice en vez de inventar una nota.

**No se rellenan los casos con lo que el sistema devuelve hoy.** Sería medirse
contra uno mismo: cualquier resultado daría 100% y no detectaría ninguna regresión
real.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.services import academic_level, busqueda_programas as bp  # noqa: E402

CASOS = os.path.join(os.path.dirname(__file__), "..", "data", "evaluacion",
                     "casos.json")


@dataclass
class Fallo:
    regla: str
    detalle: str


# ---------------------------------------------------------------------------
# 1 · Reglas duras
# ---------------------------------------------------------------------------


def regla_nivel_imposible(db, perfil, filtros, resultados) -> List[Fallo]:
    """Nadie debe recibir un programa que todavía no puede cursar.

    Es el error que A8 vino a arreglar y que ya reapareció una vez por una vía
    distinta (`normalizar_etapa` no reconocía sus propios valores). Que esté
    aquí significa que si vuelve a colarse, se sabe el mismo día.
    """
    fuera = set(academic_level.niveles_fuera_de_alcance(filtros.etapa_de_vida))
    return [
        Fallo("nivel imposible para su etapa",
              f"{r.nombre} ({r.nivel}) a alguien en '{filtros.etapa_de_vida}'")
        for r in resultados if r.nivel in fuera
    ]


def regla_pais_pedido(db, perfil, filtros, resultados) -> List[Fallo]:
    """Si pidió un país, no puede recibir otro.

    `Varios destinos` sí pasa: son redes que operan en muchos países, entran
    marcadas y el asesor confirma cuál aplica.
    """
    if not filtros.paises:
        return []
    permitidos = set(filtros.paises) | {"Varios destinos"}
    return [
        Fallo("pais distinto al pedido", f"{r.nombre} esta en {r.pais}")
        for r in resultados if r.pais and r.pais not in permitidos
    ]


def regla_ficha_de_baja(db, perfil, filtros, resultados) -> List[Fallo]:
    """Ningún programa puede colgar de una ficha que la agencia dio de baja.

    Se desactivaron 3 fichas porque el producto que describían no existe (el
    campus de Sydney de Swinburne, entre otras). Si sus programas siguen
    apareciendo, la desactivación no sirvió de nada.
    """
    ids = [r.program_id for r in resultados if r.program_id]
    if not ids:
        return []
    bajas = {
        str(x[0]) for x in db.execute(text(
            "SELECT id FROM programs WHERE id = ANY(CAST(:ids AS uuid[])) "
            "AND NOT active"
        ), {"ids": ids})
    }
    return [
        Fallo("cuelga de una ficha dada de baja", r.nombre)
        for r in resultados if r.program_id in bajas
    ]


def regla_sin_area(db, perfil, filtros, resultados) -> List[Fallo]:
    """El área es lo que cruza con el test · una fila sin área no se puede
    recomendar por afinidad, sólo por parecido de texto."""
    return [Fallo("sin area de estudio", r.nombre)
            for r in resultados if not r.area]


def regla_area_pedida(db, perfil, filtros, resultados) -> List[Fallo]:
    if not filtros.areas:
        return []
    return [
        Fallo("area distinta a la pedida", f"{r.nombre} es de {r.area}")
        for r in resultados if r.area and r.area not in set(filtros.areas)
    ]


REGLAS = [regla_nivel_imposible, regla_pais_pedido, regla_ficha_de_baja,
          regla_sin_area, regla_area_pedida]


# Perfiles de prueba para las reglas duras. No miden relevancia —eso necesita a
# alguien de la agencia— sino que ninguna combinación razonable rompa una regla.
ESCENARIOS = [
    ("estudiante de 11° que quiere Canadá",
     bp.Filtros(paises=["Canadá"], etapa_de_vida="high_school"), ["I", "S"]),
    ("estudiante en el colegio, sin país",
     bp.Filtros(etapa_de_vida="high_school_early"), ["A"]),
    ("universitario que quiere Australia",
     bp.Filtros(paises=["Australia"], etapa_de_vida="university"), ["R", "I"]),
    ("egresado buscando posgrado en Reino Unido",
     bp.Filtros(paises=["Reino Unido"], etapa_de_vida="recent_grad"), ["E", "C"]),
    ("area concreta · Artes en España",
     bp.Filtros(paises=["España"], areas=["Artes"]), ["A"]),
    ("sin ningun filtro",
     bp.Filtros(), []),
]


def correr_reglas(db) -> int:
    print("=" * 68)
    print("1 · REGLAS DURAS · un fallo aqui es un bug, no una opinion")
    print("=" * 68)
    total = 0
    for nombre, filtros, codigos in ESCENARIOS:
        resultados = bp.buscar(db, codigos_riasec=codigos, filtros=filtros,
                               limite=40)
        fallos: List[Fallo] = []
        for regla in REGLAS:
            fallos.extend(regla(db, None, filtros, resultados))
        estado = "OK  " if not fallos else "FALLA"
        print(f"  {estado} {nombre:<44} {len(resultados):>3} resultados")
        for f in fallos[:4]:
            print(f"          - {f.regla}: {f.detalle[:70]}")
        if len(fallos) > 4:
            print(f"          ... y {len(fallos) - 4} mas")
        total += len(fallos)
    print(f"\n  fallos totales: {total}")
    return total


# ---------------------------------------------------------------------------
# 2 · Relevancia
# ---------------------------------------------------------------------------


def correr_relevancia(db) -> Optional[float]:
    print()
    print("=" * 68)
    print("2 · RELEVANCIA · necesita casos etiquetados por la agencia")
    print("=" * 68)

    if not os.path.exists(CASOS):
        print(f"  No hay casos todavia ({os.path.relpath(CASOS)}).")
        print("  Sin esto, cualquier cambio al buscador es una corazonada:")
        print("  no se puede responder si mejoro o empeoro.")
        return None

    casos = json.load(open(CASOS, encoding="utf-8")).get("casos", [])
    if not casos:
        print("  El archivo existe pero esta vacio.")
        return None

    aciertos, evaluados = 0, 0
    for caso in casos:
        f = bp.Filtros(
            paises=caso.get("paises", ()), areas=caso.get("areas", ()),
            etapa_de_vida=caso.get("etapa_de_vida"),
        )
        r = bp.buscar(db, codigos_riasec=caso.get("riasec", []), filtros=f,
                      limite=caso.get("limite", 10))
        nombres = {x.nombre.lower() for x in r}
        esperados = [e.lower() for e in caso.get("esperados", [])]
        if not esperados:
            continue
        encontrados = sum(1 for e in esperados if e in nombres)
        evaluados += len(esperados)
        aciertos += encontrados
        marca = "OK  " if encontrados == len(esperados) else "PARCIAL"
        print(f"  {marca} {caso.get('nombre', '(sin nombre)')[:44]:<44} "
              f"{encontrados}/{len(esperados)}")

    if not evaluados:
        print("  Los casos no traen `esperados`.")
        return None
    pct = 100 * aciertos / evaluados
    print(f"\n  aciertos: {aciertos}/{evaluados}  ({pct:.0f}%)")
    return pct


def main() -> int:
    db = SessionLocal()
    try:
        fallos = correr_reglas(db)
        correr_relevancia(db)
    finally:
        db.close()
    # Exit code distinto de 0 si alguna regla dura falla · así esto puede correr
    # en CI y romper el build, que es el punto de tenerlo.
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
