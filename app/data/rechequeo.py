"""Re-chequeo de 12° · "¿qué tan listo estás para decidir?" · E-4, Sprint 4.

La malla de Verónica dejaba a 12° sin tests ("Plan de vuelo · ejecución"), y su
propia decisión #4 lo cerró así: **"re-chequeo corto: motivadores + confianza en
la decisión"**. Motivadores ya existía; esto es la segunda mitad.

## Qué mide y qué no

Cuatro dimensiones de la preparación para decidir, dos afirmaciones cada una
(con una sola, una respuesta distraída movería toda la dimensión):

- **Claridad** · ¿sabe qué quiere?
- **Información** · ¿conoce sus opciones y sus requisitos?
- **Respaldo** · ¿su familia está alineada y la decisión es suya?
- **Plan** · ¿tiene fechas y financiación claras?

NO es un instrumento validado ni da una "confianza" global en número: muestra las
cuatro dimensiones y la lectura dice dónde está firme y qué le falta. Las
afirmaciones las aprobó JP el 2026-10-30.

Escala 1-5 como Holland y Big 5: lo califica `calculate_vocational_scores` sin
código nuevo (0-100 por dimensión).
"""

TEST_ID = "recheck"

# Ruta de la malla a la que pertenece · lo lee `vocational_tests.disponible_para_grado`.
GRADO_OBJETIVO = 12

CLARIDAD = "CLA"
INFORMACION = "INF"
RESPALDO = "RES"
PLAN = "PLA"

RECHEQUEO_INFO = {
    CLARIDAD: {
        "name": "Claridad",
        "description": "Qué tan claro tienes qué quieres estudiar.",
    },
    INFORMACION: {
        "name": "Información",
        "description": "Qué tanto conoces tus opciones y lo que te piden para entrar.",
    },
    RESPALDO: {
        "name": "Respaldo",
        "description": "Qué tan alineados están tu familia y tú, y qué tan tuya es la decisión.",
    },
    PLAN: {
        "name": "Plan",
        "description": "Qué tan claras tienes las fechas y cómo se van a pagar tus estudios.",
    },
}

PREGUNTAS = [
    {"id": "rc-cla-1", "text": "Tengo claro qué quiero estudiar el próximo año.", "type": "likert", "category": CLARIDAD},
    {"id": "rc-cla-2", "text": "Si hoy tuviera que elegir carrera, sabría cuál escoger.", "type": "likert", "category": CLARIDAD},
    {"id": "rc-inf-1", "text": "Conozco los requisitos de admisión de los programas que me interesan.", "type": "likert", "category": INFORMACION},
    {"id": "rc-inf-2", "text": "Sé en qué se diferencian las opciones que estoy considerando.", "type": "likert", "category": INFORMACION},
    {"id": "rc-res-1", "text": "Mi familia y yo estamos de acuerdo con el camino que quiero tomar.", "type": "likert", "category": RESPALDO},
    {"id": "rc-res-2", "text": "Siento que la decisión es mía y no de otras personas.", "type": "likert", "category": RESPALDO},
    {"id": "rc-pla-1", "text": "Tengo claras las fechas límite de lo que tengo que entregar o presentar.", "type": "likert", "category": PLAN},
    {"id": "rc-pla-2", "text": "Sé cómo vamos a pagar mis estudios (ahorro, beca, crédito o apoyo familiar).", "type": "likert", "category": PLAN},
]

TEST_RECHEQUEO = {
    "id": TEST_ID,
    "slug": TEST_ID,
    "question": "¿Qué tan listo estás para decidir?",
    "group": "Qué tan listo estás",
    "name": "Re-chequeo: ¿qué tan listo estás para decidir?",
    "shortName": "Re-chequeo",
    "description": (
        "Ocho afirmaciones para ver dónde estás firme y qué te falta antes de "
        "decidir: claridad, información, respaldo de tu familia y plan."
    ),
    # Se imprime en la tarjeta del test · tiene que decir lo que es.
    "academicBasis": (
        "Chequeo propio de Mentoring para 12°, no un test psicométrico: no da "
        "una nota, muestra en qué parte de la decisión estás más firme."
    ),
    "estimatedMinutes": 3,
    "questionCount": len(PREGUNTAS),
    # Ícono ya mapeado en el front (`TestCard.iconMap`).
    "icon": "compass",
    "gradeRoutes": [GRADO_OBJETIVO],
    "questions": PREGUNTAS,
}


# Por encima de esto, la dimensión está "firme"; por debajo de FALTA, es lo que
# le falta para decidir. Entre los dos, "a medio camino". Cortes simples a
# propósito: el chequeo no está normado y no se puede fingir precisión.
FIRME = 70
FALTA = 50


def calcular_rechequeo(scores: dict) -> dict:
    """La lectura estructurada: dónde está firme y qué le falta, de lo más flojo
    a lo más firme. `scores` son los 0-100 por dimensión del cálculo genérico."""
    orden = sorted(
        (k for k in RECHEQUEO_INFO if isinstance(scores.get(k), (int, float))),
        key=lambda k: scores[k],
    )
    firme = [k for k in orden if scores[k] >= FIRME]
    falta = [k for k in orden if scores[k] < FALTA]
    if not orden:
        label = None
    elif not falta and len(firme) == len(orden):
        label = "Listo para decidir"
    elif falta:
        label = "Te falta: " + " y ".join(RECHEQUEO_INFO[k]["name"] for k in falta[:2])
    else:
        label = "A medio camino"
    return {
        "kind": TEST_ID,
        "orden": orden,
        "firme": firme,
        "falta": falta,
        "label": label,
    }
