"""Mapeo de Habilidades Blandas · banco de retos situacionales (ruta grado 10).

Lineamiento de grado 10: *"Mapeo de Habilidades Blandas. Retos situacionales
interactivos para medir liderazgo, resiliencia y trabajo en equipo"*.

**Esto NO es un test psicométrico y el copy no puede sugerir que lo sea.** Es un
instrumento propio, sin norma poblacional, sin validación ni confiabilidad medida.
Por eso:

  - se llama "Mapeo de Habilidades Blandas" (mapeo, no test ni evaluación),
  - `academicBasis` dice explícitamente que no está estandarizado — ese campo se
    imprime en la tarjeta del estudiante, así que es el sitio donde la honestidad
    tiene que estar escrita, no en un comentario de código,
  - el resultado se lee como TENDENCIA, nunca como puntaje ni etiqueta (ver
    `app/services/habilidades_blandas_service.py`).

Forma del banco: `forced_choice`, idéntica a VARK y Motivadores, para que el front
lo renderice con los componentes que ya tiene (`ForcedChoiceQuestion` +
`ForcedChoiceBars`) sin lógica nueva.

Cada reto ofrece exactamente 3 opciones, una por habilidad. Es una medida
**ipsativa**: el estudiante no dice "cuánto" tiene de cada una, dice cuál elige
cuando las tres son posibles. Consecuencia que el copy respeta: un perfil parejo
NO significa "flojo en las tres".

El ORDEN de las opciones rota deliberadamente entre retos (LID/EQU/RES, luego
RES/LID/EQU, luego EQU/RES/LID…). Si la opción de liderazgo fuera siempre la
primera, a los tres retos el estudiante ya sabría qué está eligiendo y el mapeo
mediría su idea de lo que "queda bien", no su reacción.
"""

from __future__ import annotations

# Códigos de las tres habilidades. El ORDEN es canónico: se usa para desempatar
# de forma determinista en el servicio, así que no se reordena por estética.
LIDERAZGO = "LID"
RESILIENCIA = "RES"
EQUIPO = "EQU"

HABILIDADES_ORDEN = [LIDERAZGO, RESILIENCIA, EQUIPO]

# Ruta de la malla a la que pertenece este instrumento. Sale como `gradeRoutes`
# en la definición del test y lo lee `vocational_tests.disponible_para_grado`.
GRADO_OBJETIVO = 10


HABILIDAD_INFO = {
    LIDERAZGO: {
        "name": "Liderazgo",
        "description": (
            "Tomas la iniciativa cuando algo está detenido: organizas, decides y "
            "te haces cargo de que las cosas pasen."
        ),
        "tendencia": "sueles tomar la iniciativa y poner orden cuando nadie más lo hace",
        "tip": (
            "Busca espacios donde te toque coordinar de verdad: un proyecto del "
            "colegio, un club, el consejo estudiantil. Y practica lo que menos se "
            "practica al liderar: preguntar antes de decidir."
        ),
    },
    RESILIENCIA: {
        "name": "Resiliencia",
        "description": (
            "Cuando algo sale mal o se pone cuesta arriba, te sostienes: ajustas, "
            "vuelves a intentar y no te quedas en el golpe."
        ),
        "tendencia": "te sostienes cuando algo sale mal y vuelves a intentarlo con otra estrategia",
        "tip": (
            "Tu fuerza es aguantar; el riesgo es aguantar solo. Cuando algo se te "
            "esté haciendo pesado, cuéntalo antes de que se vuelva demasiado."
        ),
    },
    EQUIPO: {
        "name": "Trabajo en equipo",
        "description": (
            "Lees lo que le pasa al grupo: repartes, incluyes al que quedó por "
            "fuera y buscas que la solución sirva para todos."
        ),
        "tendencia": "resuelves con el grupo y no por encima del grupo",
        "tip": (
            "Aprovecha esto en trabajos donde haya que coordinar gente distinta. "
            "Y cuida que ceder no se te vuelva la única salida: tu idea también cuenta."
        ),
    },
}


def _reto(id_: str, texto: str, opciones: list[tuple[str, str]]) -> dict:
    """Arma un reto en la forma que espera el front (`forced_choice`).

    `opciones` llega como lista de (habilidad, texto) EN EL ORDEN EN QUE SE
    MUESTRAN, que rota a propósito entre retos.
    """
    return {
        "id": id_,
        "text": texto,
        "type": "forced_choice",
        "options": [{"value": hab, "label": label} for hab, label in opciones],
    }


# Situaciones reales de un chico de 15-16 en Colombia. Se evita el escenario
# heroico (el incendio, la catástrofe): lo que discrimina a esta edad es el
# trabajo en grupo trancado, el partido perdido y el amigo excluido.
RETOS_SITUACIONALES = [
    _reto(
        "hb-1",
        "Faltan tres días para entregar un trabajo en grupo y nadie ha hecho nada. "
        "El chat del grupo está mudo desde la semana pasada. ¿Qué haces?",
        [
            (LIDERAZGO, "Armo yo el plan: parto el trabajo, le asigno una parte a cada uno y pongo fechas."),
            (EQUIPO, "Propongo una llamada corta para que cada quien diga qué puede hacer y repartimos entre todos."),
            (RESILIENCIA, "Arranco hoy mismo por mi parte y sigo avanzando aunque el grupo no despegue; después veo cómo cubro lo que falte."),
        ],
    ),
    _reto(
        "hb-2",
        "Vas perdiendo 3-0 en el entretiempo de un partido (o de una competencia) "
        "que querías ganar. El equipo está caído. ¿Qué haces?",
        [
            (RESILIENCIA, "Me concentro en jugar bien los minutos que quedan, aunque el marcador ya casi no se pueda dar vuelta."),
            (LIDERAZGO, "Reúno al equipo y propongo cambiar algo concreto para el segundo tiempo."),
            (EQUIPO, "Me acerco a los que están más quemados y les levanto el ánimo antes de volver a salir."),
        ],
    ),
    _reto(
        "hb-3",
        "Se armó un plan del grupo el fin de semana y te enteras por redes de que "
        "a ti no te invitaron. ¿Qué haces?",
        [
            (EQUIPO, "Hablo con el grupo y propongo que los planes se abran, para que no le pase a nadie más."),
            (RESILIENCIA, "Me da rabia un rato, pero no dejo que me tumbe la semana."),
            (LIDERAZGO, "Le escribo directo a quien organizó y le pregunto qué pasó."),
        ],
    ),
    _reto(
        "hb-4",
        "Te fue mal en un examen importante de una materia que creías tener "
        "dominada. ¿Qué haces primero?",
        [
            (LIDERAZGO, "Busco al profesor, le pregunto qué esperaba y qué puedo hacer para recuperar."),
            (EQUIPO, "Armo un grupo de estudio con compañeros a los que también les fue mal."),
            (RESILIENCIA, "Reviso qué falló en mi forma de estudiar y la cambio para el siguiente."),
        ],
    ),
    _reto(
        "hb-5",
        "El profesor pide un voluntario para presentar el proyecto del grupo "
        "frente a todo el curso. Nadie levanta la mano. ¿Qué haces?",
        [
            (EQUIPO, "Propongo que presentemos entre todos, cada uno con una parte."),
            (RESILIENCIA, "Me ofrezco aunque hablar en público me ponga nervioso: la última vez no me salió bien y quiero volver a intentarlo."),
            (LIDERAZGO, "Me ofrezco yo: prefiero presentarlo y que quede como lo trabajamos."),
        ],
    ),
    _reto(
        "hb-6",
        "Dos personas de tu grupo se pelearon y el trabajo quedó trancado por eso. "
        "¿Qué haces?",
        [
            (RESILIENCIA, "Sigo avanzando en lo que puedo mientras eso se enfría, sin engancharme en la pelea."),
            (LIDERAZGO, "Tomo yo la decisión que estaba trancada y seguimos; después se hablará."),
            (EQUIPO, "Hablo con cada uno por aparte y busco un punto medio para que el grupo vuelva a funcionar."),
        ],
    ),
    _reto(
        "hb-7",
        "Un amigo tuyo quedó por fuera de un plan al que sí invitaron al resto del "
        "grupo. Te lo cuenta a ti. ¿Qué haces?",
        [
            (LIDERAZGO, "Hablo con quien organizó y me encargo de que lo inviten."),
            (EQUIPO, "Le propongo al grupo que abramos el plan y le escribo a mi amigo para que sepa que va."),
            (RESILIENCIA, "Le propongo a él otro plan para ese día; se le va a pasar y no vale quedarse ahí."),
        ],
    ),
    _reto(
        "hb-8",
        "Te comprometiste con demasiadas cosas al tiempo (colegio, entrenamiento, "
        "un proyecto) y no te está dando el tiempo. ¿Qué haces?",
        [
            (EQUIPO, "Le cuento al grupo cómo voy y entre todos redistribuimos lo que se pueda."),
            (RESILIENCIA, "Reorganizo mis días, priorizo y aviso a tiempo lo que no voy a alcanzar."),
            (LIDERAZGO, "Decido qué es lo importante y suelto el resto, aunque a alguien no le guste."),
        ],
    ),
    _reto(
        "hb-9",
        "Propusiste una idea en clase y la rechazaron delante de todos. ¿Qué haces?",
        [
            (RESILIENCIA, "Me aguanto el momento, la reviso y la vuelvo a proponer mejor armada."),
            (LIDERAZGO, "La defiendo ahí mismo con argumentos."),
            (EQUIPO, "Escucho las ideas de los demás y busco mezclarlas con la mía."),
        ],
    ),
]


# Definición del test en la forma exacta que consume el front (misma que el resto
# del banco: id/slug/name/shortName/description/academicBasis/…/questions).
TEST_HABILIDADES_BLANDAS = {
    "id": "habilidades-blandas",
    "slug": "habilidades-blandas",
    "name": "Mapeo de Habilidades Blandas",
    "shortName": "Habilidades blandas",
    "description": (
        "Nueve situaciones reales de colegio para ver cómo respondes cuando hay "
        "que liderar, cuando algo sale mal y cuando dependes de otros. No hay "
        "respuestas correctas ni nota: el resultado son tendencias, no etiquetas."
    ),
    # Este campo se imprime en la tarjeta del test. Es el sitio donde tiene que
    # quedar dicho, en el idioma del estudiante, que esto no es un instrumento
    # clínico ni estandarizado.
    "academicBasis": (
        "Instrumento propio de Mentoring, inspirado en el formato de los retos "
        "situacionales (situational judgment). NO es un test psicométrico "
        "estandarizado: no tiene norma poblacional ni puntaje validado, y no "
        "sirve para diagnosticar nada. Describe la tendencia de tus respuestas "
        "de hoy y sirve para conversarla con tu orientador."
    ),
    "estimatedMinutes": 6,
    "questionCount": len(RETOS_SITUACIONALES),
    # Ícono ya mapeado en el front (`TestCard.iconMap`); uno nuevo caería al
    # hexágono por defecto.
    "icon": "target",
    # Ruta de la malla: sólo grado 10. Lo lee `vocational_tests.disponible_para_grado`.
    "gradeRoutes": [GRADO_OBJETIVO],
    "questions": RETOS_SITUACIONALES,
}
