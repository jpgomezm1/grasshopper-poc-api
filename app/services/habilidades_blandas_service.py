"""Lectura del Mapeo de Habilidades Blandas (ruta grado 10).

Qué se calcula y, sobre todo, **qué NO**:

  - No hay puntaje ni nota. Se cuenta en cuántos de los 9 retos el estudiante
    eligió cada manera de responder. Eso es un conteo, no una medición.
  - No hay etiqueta. El resultado es una TENDENCIA ("te inclinas por…"), nunca
    un rasgo atribuido ("eres un líder"). El instrumento no está normado y no
    puede sostener una afirmación de ese tipo.
  - No hay déficit. Al ser una medida ipsativa (elegir una de tres), elegir poco
    "trabajo en equipo" NO significa que el estudiante trabaje mal en equipo:
    significa que, cuando las tres eran posibles, eligió otra. El copy lo dice.

Tres reglas de lectura, deterministas y probadas:

1. **Margen de un reto.** Si la diferencia entre la habilidad más elegida y la
   siguiente es de 0 ó 1, se nombran las dos. Una elección de diferencia sobre
   9 retos no distingue nada. Es la misma "Regla de Oro" que ya usa VARK
   (`scoring_service.calculate_vark`), y se reusa a propósito: dos criterios
   distintos para el mismo problema es lo que después nadie sabe explicarle a
   una familia.
2. **Perfil parejo.** Si las tres entran en ese margen, no se nombra ninguna
   como dominante. Parejo no es flojo.
3. **Respuestas incompletas.** Con menos de `MINIMO_RETOS_PARA_LEER` retos
   respondidos no se emite tendencia: se dice cuántos faltan. Antes se prefería
   inventar una lectura sobre dos respuestas; eso es exactamente lo que hace que
   un instrumento propio parezca un oráculo.

Desempate determinista por el orden canónico LID, RES, EQU (`HABILIDADES_ORDEN`):
dos estudiantes con las mismas respuestas ven siempre el mismo resultado.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.data.habilidades_blandas import (
    EQUIPO,
    HABILIDAD_INFO,
    HABILIDADES_ORDEN,
    LIDERAZGO,
    RESILIENCIA,
    TEST_HABILIDADES_BLANDAS,
)

TEST_ID = TEST_HABILIDADES_BLANDAS["id"]

# Diferencia (en número de retos) por debajo de la cual dos habilidades se
# consideran empatadas. Ver regla 1 del docstring.
MARGEN_DE_EMPATE = 1

# Mínimo de retos respondidos para emitir una tendencia. 5 de 9 = más de la
# mitad. Por debajo de eso el resultado diría más del abandono que del chico.
MINIMO_RETOS_PARA_LEER = 5

# Se guarda en los extras para que el front y el PDF lo impriman junto al
# resultado sin volver a redactarlo (y sin poder olvidarlo).
NOTA_NO_ES_TEST = (
    "Este mapeo no es un test psicométrico ni un diagnóstico: describe cómo "
    "respondiste hoy a nueve situaciones, para conversarlo con tu orientador."
)

QUE_MIDE_EL_PORCENTAJE = (
    "Cada porcentaje es en cuántos de los nueve retos elegiste esa manera de "
    "responder. No es una calificación ni una comparación con otras personas."
)

# Valores posibles de `perfil`, para que quien lea el JSON no tenga que adivinar.
PERFIL_INSUFICIENTE = "insuficiente"
PERFIL_DEFINIDO = "definido"
PERFIL_MIXTO = "mixto"
PERFIL_PAREJO = "parejo"


def _contar(answers: Dict[str, Any]) -> tuple[Dict[str, int], int]:
    """Cuenta elecciones válidas por habilidad y cuántos retos se respondieron.

    Una respuesta a un reto inexistente, vacía o con un código que no es una de
    las tres habilidades NO cuenta como respondida: si contara, un test enviado
    con basura parecería completo.
    """
    counts = {h: 0 for h in HABILIDADES_ORDEN}
    respondidas = 0
    for reto in TEST_HABILIDADES_BLANDAS["questions"]:
        elegida = (answers or {}).get(reto["id"])
        if elegida in counts:
            counts[elegida] += 1
            respondidas += 1
    return counts, respondidas


def _nombres(codigos: List[str]) -> List[str]:
    return [HABILIDAD_INFO[c]["name"] for c in codigos]


def _a_minuscula(nombre: str) -> str:
    """"Trabajo en equipo" -> "trabajo en equipo" (sólo la inicial)."""
    return nombre[:1].lower() + nombre[1:]


def _enumerar(nombres: List[str]) -> str:
    """"a, b y c" · en minúscula, porque va dentro de una frase."""
    minusculas = [_a_minuscula(n) for n in nombres]
    if len(minusculas) <= 1:
        return "".join(minusculas)
    return ", ".join(minusculas[:-1]) + " y " + minusculas[-1]


def calcular_habilidades_blandas(answers: Dict[str, Any]) -> Dict[str, Any]:
    """Lee el mapeo. Nunca lanza: con respuestas vacías devuelve el caso incompleto."""
    counts, respondidas = _contar(answers)
    total = len(TEST_HABILIDADES_BLANDAS["questions"])

    base: Dict[str, Any] = {
        "kind": TEST_ID,
        "counts": counts,
        "respondidas": respondidas,
        "total_retos": total,
        "completo": respondidas == total,
        "medida": QUE_MIDE_EL_PORCENTAJE,
        "nota": NOTA_NO_ES_TEST,
    }

    if respondidas < MINIMO_RETOS_PARA_LEER:
        faltan = MINIMO_RETOS_PARA_LEER - respondidas
        return {
            **base,
            "perfil": PERFIL_INSUFICIENTE,
            "tendencias": [],
            "label": "Mapeo incompleto",
            "headline": (
                f"Respondiste {respondidas} de {total} retos. Con eso todavía no "
                f"se alcanza a ver una tendencia: te faltan al menos {faltan} para "
                "poder leerlo."
            ),
            "skill_info": [],
        }

    # Orden por conteo descendente; a igual conteo manda el orden canónico.
    ranking = sorted(
        HABILIDADES_ORDEN, key=lambda h: (-counts[h], HABILIDADES_ORDEN.index(h))
    )
    tope = counts[ranking[0]]
    tendencias = [h for h in ranking if tope - counts[h] <= MARGEN_DE_EMPATE]

    nombres = _nombres(tendencias)

    if len(tendencias) >= len(HABILIDADES_ORDEN):
        perfil = PERFIL_PAREJO
        label = "Perfil parejo"
        headline = (
            "Respondiste parejo en las tres: ninguna se impone sobre las otras. "
            "Eso no quiere decir que estés flojo en todas — quiere decir que tu "
            "manera de responder cambia según la situación, y eso también es un "
            "dato para conversar."
        )
    elif len(tendencias) == 2:
        perfil = PERFIL_MIXTO
        label = f"{nombres[0]} y {_a_minuscula(nombres[1])}"
        headline = (
            f"Te mueves entre {_enumerar(nombres)}: elegiste casi lo mismo en las "
            "dos, así que ninguna manda sobre la otra. Es una tendencia de cómo "
            "respondiste hoy, no una etiqueta."
        )
    else:
        perfil = PERFIL_DEFINIDO
        codigo = tendencias[0]
        label = nombres[0]
        headline = (
            f"En estas situaciones te inclinas por {_enumerar(nombres)}: "
            f"{HABILIDAD_INFO[codigo]['tendencia']}. Es una tendencia de cómo "
            "respondiste hoy, no una etiqueta."
        )

    if not base["completo"]:
        # Se lee igual, pero se dice que está a medias: la familia tiene derecho
        # a saber sobre cuántas respuestas se está leyendo.
        headline += (
            f" Ojo: respondiste {respondidas} de {total} retos, así que la lectura "
            "es parcial."
        )

    return {
        **base,
        "perfil": perfil,
        "tendencias": tendencias,
        "label": label,
        "headline": headline,
        # Misma forma que `style_info` (VARK) y `motivator_info` (Motivadores):
        # el front pinta name + description + tip sin lógica propia.
        "skill_info": [{"code": h, **HABILIDAD_INFO[h]} for h in tendencias],
    }


__all__ = [
    "TEST_ID",
    "EQUIPO",
    "LIDERAZGO",
    "RESILIENCIA",
    "MARGEN_DE_EMPATE",
    "MINIMO_RETOS_PARA_LEER",
    "PERFIL_DEFINIDO",
    "PERFIL_INSUFICIENTE",
    "PERFIL_MIXTO",
    "PERFIL_PAREJO",
    "calcular_habilidades_blandas",
]
