"""Bancos de PRÁCTICA para exámenes de admisión (SAT · IELTS).

Reunión con la clienta del 2026-08-24, minuto 40:22, textual:

    *"yo lo que necesito es pasar el test, no que nadie me certifique... es
    solamente para hacer el test"*

y JP (40:17): *"pasen esas preparaciones que obviamente no van a ser, hay temas
que no van a ser certificadas"*.

O sea: **no** quiere el instrumento oficial. Quiere material de práctica que
ayude a alguien a llegar preparado. Eso cambia el problema legal por completo y
define todo lo que hay en este archivo.

## La línea que este módulo no cruza (y por qué está escrita en el código)

Las preguntas reales del SAT son de College Board y las del IELTS de sus
titulares: tienen derechos de autor, y sus nombres son marcas. Aquí **no hay ni
un ítem reproducido de ningún examen ni de ningún proveedor**. Los 65 ejercicios
son propios, escritos para este repo, y practican las **habilidades** que esos
exámenes evalúan — que es lo que sí se puede construir.

Tres reglas de copy que no son estética, son cumplimiento:

1. **Nunca se afirma que esto certifica, acredita, está avalado o predice un
   puntaje oficial.** `AVISO_NO_OFICIAL` lo dice en primera persona y viaja en
   *todas* las respuestas del router — no en letra chica, no en un modal que se
   puede cerrar. Hay un test que falla si algún endpoint lo omite.
2. **No se publican datos duros del examen** (duración, número de preguntas,
   escala de puntaje, costo, fechas). Cambian, no son nuestros, y este proyecto
   ya se cobró un reclamo de la clienta por contenido inventado por nosotros.
   `FORMATO` describe la forma del examen de manera cualitativa y remite al
   examinador para lo demás.
3. **Se dice qué NO cubre.** `no_cubierto` existe para que nadie lea "práctica
   de IELTS" y asuma que incluye Listening o Speaking. Omitirlo sería mentir por
   silencio.

La diferencia con el reclamo anterior (un test con preguntas inventadas por
nosotros presentado como si fuera un instrumento real) es exactamente ésta: aquí
el encuadre es honesto desde el nombre. Se llama práctica y se presenta como
práctica.

## Idioma: enunciados en inglés, explicaciones en español

Los dos exámenes se presentan en inglés. Practicar comprensión de lectura del
SAT en español no prepara para leerla en inglés, así que los ítems van en
inglés — el mismo criterio con el que `english_test_questions.py` mantiene el
examen de AMES sin traducir. Las **explicaciones van en español**, porque ahí
está el valor pedagógico y porque la app está en español.

## `nivel` es NUESTRO, y no es CEFR

`english_test_questions.py` deja `difficulty` en None a propósito: AMES no
declara nivel por ítem y ponérselo sería mostrarle al estudiante un dato falso.
Aquí es al revés y por eso sí se declara: **los ejercicios los escribimos
nosotros**, así que graduarlos es una afirmación sobre nuestro propio material,
no sobre un instrumento ajeno. Se usa un vocabulario propio
(`fundamentos`/`intermedio`/`avanzado`) precisamente para que nadie lo lea como
una etiqueta CEFR ni como una predicción de puntaje.

## Forma del dato

La ficha del examen sigue el contrato de `app/data/vocational_tests.py`
(`id`, `slug`, `name`, `shortName`, `description`, `academicBasis`,
`estimatedMinutes`, `questionCount`, `icon`) para que el front la pinte con la
tarjeta que ya tiene. Los ítems siguen el contrato de
`app/data/english_test_questions.py` (`id`, `question`, `options` como lista de
strings, `passage` opcional) porque es el único renderizador de opción múltiple
que ya existe. Ninguna de las dos formas se inventó aquí.

Reparto de responsabilidades: este módulo es **el banco y sus consultas puras**.
Todo lo que dependa de QUIÉN es el estudiante (a quién se le ofrece, en qué
nivel arranca, calificación de una sesión) vive en
`app/services/exam_prep_service.py`, igual que la pareja
`data/habilidades_blandas.py` + `services/habilidades_blandas_service.py`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Vocabulario propio de dificultad · ver docstring ("`nivel` es NUESTRO")
# ---------------------------------------------------------------------------
NIVEL_FUNDAMENTOS = "fundamentos"
NIVEL_INTERMEDIO = "intermedio"
NIVEL_AVANZADO = "avanzado"

# El orden es canónico: se usa para buscar en niveles vecinos cuando el nivel
# objetivo no tiene suficientes ejercicios. No se reordena.
NIVELES = (NIVEL_FUNDAMENTOS, NIVEL_INTERMEDIO, NIVEL_AVANZADO)

EXAMEN_SAT = "sat"
EXAMEN_IELTS = "ielts"
EXAMENES_IDS = (EXAMEN_SAT, EXAMEN_IELTS)

# Tamaño por defecto de una sesión de práctica. Diez ejercicios con su
# explicación se leen en un rato; cuarenta se abandonan a la mitad.
TAMANO_SESION = 10


# ---------------------------------------------------------------------------
# Los avisos · viajan en TODAS las respuestas del router (no en letra chica)
# ---------------------------------------------------------------------------

AVISO_NO_OFICIAL = (
    "Este es material de práctica propio de Mentoring. No es el examen, no lo "
    "reemplaza, no certifica ni acredita nada y no predice el puntaje que vas a "
    "sacar. Sirve para llegar practicado."
)

# Uso nominativo de las marcas + no afiliación. Es lo mínimo que hay que decir
# cuando se nombra un examen ajeno para describir qué se practica.
MARCAS = {
    EXAMEN_SAT: (
        "SAT es una marca registrada de College Board. Mentoring no está "
        "afiliado a College Board ni avalado por él, y este material no proviene "
        "de sus publicaciones."
    ),
    EXAMEN_IELTS: (
        "IELTS es una marca de sus titulares (British Council, IDP: IELTS "
        "Australia y Cambridge). Mentoring no está afiliado a ellos ni avalado "
        "por ellos, y este material no proviene de sus publicaciones."
    ),
}

# Lo que NO publicamos porque no es nuestro y cambia. Ver regla 2 del docstring.
REMISION_AL_EXAMINADOR = (
    "La duración, el número de preguntas, la escala de puntaje, el costo y las "
    "fechas los define y publica quien administra el examen, y cambian. "
    "Confírmalos en la página oficial del examen junto con tu asesor: aquí no "
    "los reproducimos para no darte un dato desactualizado."
)

# Se devuelve junto a cada calificación. Dice explícitamente lo que un porcentaje
# de aciertos en una práctica NO significa.
NOTA_DE_RESULTADO = (
    "Este resultado dice cómo te fue en estos ejercicios nuestros, hoy. No es un "
    "puntaje del examen ni una estimación de lo que sacarías en él."
)


# ---------------------------------------------------------------------------
# Habilidades · qué practica cada bloque
#
# `depende_del_ingles` decide de dónde sale el nivel de arranque: las
# habilidades de lengua arrancan en el nivel que ya midió el diagnóstico de
# inglés (AMES); las de matemáticas NO, porque no tenemos un diagnóstico de
# matemáticas y derivar la dificultad de matemáticas del nivel de inglés sería
# inventarse una relación que nadie midió. Ver `exam_prep_service`.
# ---------------------------------------------------------------------------

HABILIDADES: List[Dict[str, Any]] = [
    # --- SAT -------------------------------------------------------------
    {
        "id": "sat_gramatica",
        "exam": EXAMEN_SAT,
        "name": "Convenciones del inglés escrito",
        "description": (
            "Concordancia, pronombres, puntuación, tiempos verbales y "
            "modificadores: los errores que el examen busca a propósito."
        ),
        "dependsOnEnglish": True,
    },
    {
        "id": "sat_expresion",
        "exam": EXAMEN_SAT,
        "name": "Expresión de ideas",
        "description": (
            "Conectores, concisión y elegir la frase que cumple el objetivo que "
            "el enunciado pide. Aquí casi nunca hay una opción 'incorrecta': hay "
            "una que responde la pregunta."
        ),
        "dependsOnEnglish": True,
    },
    {
        "id": "sat_lectura",
        "exam": EXAMEN_SAT,
        "name": "Lectura y evidencia",
        "description": (
            "Idea principal, función de una frase, vocabulario en contexto e "
            "inferencias que se puedan rastrear hasta una línea del texto."
        ),
        "dependsOnEnglish": True,
    },
    {
        "id": "sat_algebra",
        "exam": EXAMEN_SAT,
        "name": "Álgebra",
        "description": (
            "Ecuaciones e inecuaciones lineales, sistemas, pendiente y "
            "traducción de un enunciado a una ecuación."
        ),
        "dependsOnEnglish": False,
    },
    {
        "id": "sat_datos",
        "exam": EXAMEN_SAT,
        "name": "Datos, razones y porcentajes",
        "description": (
            "Proporciones, tasas, variación porcentual, media contra mediana y "
            "probabilidad leída de un subgrupo."
        ),
        "dependsOnEnglish": False,
    },
    {
        "id": "sat_avanzado",
        "exam": EXAMEN_SAT,
        "name": "Álgebra avanzada y geometría",
        "description": (
            "Cuadráticas, crecimiento exponencial, circunferencia, triángulos "
            "rectángulos y razones trigonométricas básicas."
        ),
        "dependsOnEnglish": False,
    },
    # --- IELTS -----------------------------------------------------------
    {
        "id": "ielts_lectura",
        "exam": EXAMEN_IELTS,
        "name": "Comprensión de lectura académica",
        "description": (
            "Localizar información, distinguir lo que el texto contradice de lo "
            "que simplemente no dice, y leer la intención de una frase."
        ),
        "dependsOnEnglish": True,
    },
    {
        "id": "ielts_vocabulario",
        "exam": EXAMEN_IELTS,
        "name": "Vocabulario académico",
        "description": (
            "Colocaciones y palabras parecidas que no significan lo mismo, que "
            "es donde se pierde precisión al escribir."
        ),
        "dependsOnEnglish": True,
    },
    {
        "id": "ielts_gramatica",
        "exam": EXAMEN_IELTS,
        "name": "Estructuras del inglés académico",
        "description": (
            "Artículos, preposiciones, pasiva, cláusulas relativas y "
            "condicionales: lo que sostiene un párrafo formal."
        ),
        "dependsOnEnglish": True,
    },
    {
        "id": "ielts_escritura",
        "exam": EXAMEN_IELTS,
        "name": "Decisiones de escritura",
        "description": (
            "Elegir el resumen general, parafrasear el enunciado, describir un "
            "dato sin exagerarlo y fijar una postura clara. Se practica "
            "eligiendo, no escribiendo: una máquina no puede calificarte un "
            "ensayo con honestidad, un profesor sí."
        ),
        "dependsOnEnglish": True,
    },
]

_HABILIDAD_POR_ID = {h["id"]: h for h in HABILIDADES}


# ---------------------------------------------------------------------------
# Textos propios de los ejercicios de lectura
#
# Escritos para este repo. No son de ningún examen ni de ningún proveedor.
# ---------------------------------------------------------------------------

_TEXTOS: Dict[str, str] = {
    "coastlines": (
        "Drawing a Moving Line\n\n"
        "For most of the twentieth century, cartographers drew coastlines as if "
        "they were permanent. A shoreline was a line: fixed, measurable, and "
        "printed in the same place edition after edition. Satellite imagery "
        "ended that habit. Once the same beach could be photographed every few "
        "days, it became obvious that a coast is less a line than a slow event "
        "— sand arriving from one direction, leaving in another, and "
        "occasionally disappearing during a single storm. Modern maps hedge. "
        "They show a band, not a border."
    ),
    "apology": (
        "Ana had rehearsed the apology for two days, and it was a good one: "
        "specific, unhurried, free of the word “but”. She delivered it "
        "in the kitchen, to her brother’s back, while he rinsed the same "
        "clean glass for the third time. When she finished, he set the glass "
        "down, said “okay”, and left the room. Ana stood there "
        "deciding whether “okay” had been the end of something or the "
        "beginning."
    ),
    "urban_bees": (
        "Urban Bees\n\n"
        "Beekeepers once assumed that cities were hostile to bees. The opposite "
        "turned out to be true in several European capitals, where hives on "
        "rooftops produced more honey per season than hives in the surrounding "
        "countryside. Researchers offer two explanations. First, city gardens, "
        "balconies and parks flower in a staggered sequence from early spring to "
        "autumn, while a field of a single crop flowers for a few weeks and then "
        "offers nothing. Second, urban plants are rarely sprayed with the "
        "pesticides used on farmland. Cities are not paradise, however: "
        "pollution shortens the life of individual workers, and swarms in "
        "crowded neighbourhoods are difficult to relocate."
    ),
    "night_trains": (
        "Night Trains\n\n"
        "After two decades of decline, sleeper trains are returning to Europe. "
        "The reasons are partly environmental: a berth on a long overnight route "
        "produces a fraction of the emissions of the equivalent flight. But "
        "operators point to something less obvious — a night on a train "
        "removes the cost of a hotel and a working day from the trip. The "
        "obstacles are practical rather than romantic. Sleeper carriages are "
        "expensive to buy, they sit unused during the day, and a single train "
        "crossing four countries must satisfy four sets of safety rules."
    ),
}


# ---------------------------------------------------------------------------
# Constructor de ítems · valida en tiempo de import
#
# Un banco con la respuesta "correcta" fuera de las opciones, o con un ítem sin
# explicación, es exactamente el tipo de defecto que sólo se descubre cuando un
# estudiante ya lo vio. Aquí revienta al importar el módulo.
# ---------------------------------------------------------------------------

def _item(
    id_: str,
    *,
    habilidad: str,
    nivel: str,
    question: str,
    options: List[str],
    correct: str,
    explanation: str,
    passage: Optional[str] = None,
) -> Dict[str, Any]:
    if habilidad not in _HABILIDAD_POR_ID:
        raise ValueError(f"{id_}: habilidad desconocida {habilidad!r}")
    if nivel not in NIVELES:
        raise ValueError(f"{id_}: nivel desconocido {nivel!r}")
    if len(options) < 3:
        raise ValueError(f"{id_}: un ejercicio de opción múltiple necesita 3 o más opciones")
    if len(set(options)) != len(options):
        raise ValueError(f"{id_}: hay opciones repetidas")
    if correct not in options:
        raise ValueError(f"{id_}: la respuesta correcta no está entre las opciones")
    if not explanation.strip():
        raise ValueError(f"{id_}: sin explicación · es lo único que da valor al ejercicio")
    if passage is not None and passage not in _TEXTOS:
        raise ValueError(f"{id_}: texto {passage!r} inexistente")

    return {
        "id": id_,
        "exam": _HABILIDAD_POR_ID[habilidad]["exam"],
        "skill": habilidad,
        "level": nivel,
        "type": "multiple_choice",
        "question": question,
        "options": list(options),
        "correct": correct,
        "explanation": explanation,
        "passage_id": passage,
    }


# ---------------------------------------------------------------------------
# SAT · convenciones del inglés escrito
# ---------------------------------------------------------------------------

_ITEMS_SAT_GRAMATICA = [
    _item(
        "sat-gram-1",
        habilidad="sat_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "The collection of essays that the students submitted last spring "
            "______ now available in the school library."
        ),
        options=["is", "are", "were", "have been"],
        correct="is",
        explanation=(
            "El sujeto es “The collection”, que es singular. Todo lo "
            "que va entre el sujeto y el verbo (“of essays that the "
            "students submitted…”) no cambia el número del verbo. La "
            "trampa está puesta a propósito: el sustantivo plural "
            "“essays” queda pegado al espacio en blanco y el oído pide "
            "“are”. Truco para el examen: tapa con el dedo todo lo que "
            "está entre comas o después de “of” y vuelve a leer."
        ),
    ),
    _item(
        "sat-gram-2",
        habilidad="sat_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "The committee announced ______ decision on Friday morning."
        ),
        options=["its", "it's", "its'", "their"],
        correct="its",
        explanation=(
            "“Its” es el posesivo y va sin apóstrofo. “It's” "
            "siempre significa “it is” o “it has”: si "
            "reemplazas y la frase queda “the committee announced it is "
            "decision”, ya sabes que está mal. “Its'” no existe en "
            "inglés. “Their” falla porque “committee” aquí "
            "funciona como un cuerpo único que actúa junto."
        ),
    ),
    _item(
        "sat-gram-3",
        habilidad="sat_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Which option joins the two ideas correctly?\n\n"
            "The lab results arrived on Monday ______ spent the rest of the week "
            "checking them."
        ),
        options=["; the team", ", the team", " the team", ", and, the team"],
        correct="; the team",
        explanation=(
            "Son dos oraciones independientes: cada una tiene su sujeto y su "
            "verbo y podría vivir sola. Dos independientes se unen con punto y "
            "coma, o con coma más conjunción (“, and the team…”). "
            "Sólo con coma se produce un “comma splice”, que es el "
            "error de puntuación que más aparece en este examen; sin nada queda "
            "un “run-on”; y la última opción mete una coma después de "
            "la conjunción, donde nunca va."
        ),
    ),
    _item(
        "sat-gram-4",
        habilidad="sat_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "By the time the results ______ published, the team had already "
            "moved on to a new project."
        ),
        options=["were", "are", "will be", "had been"],
        correct="were",
        explanation=(
            "“had already moved” es pasado perfecto y ancla toda la "
            "frase en el pasado, así que “are” y “will be” "
            "quedan descartadas por incoherencia de tiempo. Entre las dos de "
            "pasado, el pasado perfecto marca lo que ocurrió PRIMERO; aquí lo "
            "primero fue que el equipo se moviera, no la publicación. Entonces la "
            "publicación va en pasado simple."
        ),
    ),
    _item(
        "sat-gram-5",
        habilidad="sat_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "Walking through the museum, ______"
        ),
        options=[
            "Ana was impressed by the paintings.",
            "the paintings impressed Ana.",
            "it was impressive for Ana.",
            "the impression on Ana was strong.",
        ],
        correct="Ana was impressed by the paintings.",
        explanation=(
            "Cuando una frase empieza con “-ing” y una coma, quien "
            "hace esa acción tiene que ser el sujeto que aparece justo después. "
            "Quien camina por el museo es Ana, no los cuadros ni una impresión. "
            "Las otras tres son “dangling modifiers”: gramaticalmente "
            "dicen que los cuadros iban caminando."
        ),
    ),
    _item(
        "sat-gram-6",
        habilidad="sat_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "The internship taught her to code, to write clearly, and ______."
        ),
        options=[
            "to manage her time",
            "managing her time",
            "how she managed her time",
            "time management skills",
        ],
        correct="to manage her time",
        explanation=(
            "Los elementos de una lista tienen que tener la misma forma "
            "gramatical. Los dos primeros son infinitivos (“to code”, "
            "“to write”), así que el tercero también. Esto se llama "
            "estructura paralela y el examen la revisa cada vez que ve una lista "
            "de tres."
        ),
    ),
    _item(
        "sat-gram-7",
        habilidad="sat_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "Marie Curie ______ won Nobel Prizes in two different sciences."
        ),
        options=[
            ", who was born in Warsaw,",
            ", who was born in Warsaw",
            "who was born in Warsaw,",
            "who was born in Warsaw",
        ],
        correct=", who was born in Warsaw,",
        explanation=(
            "El nombre propio ya identifica a la persona, así que dónde nació es "
            "información adicional, no esencial: va entre comas y las comas van a "
            "los DOS lados. Poner una sola parte el sujeto de su verbo, que es el "
            "error que el examen busca. Sin comas, la cláusula pasaría a ser "
            "esencial, como si hubiera varias Marie Curie y hubiera que aclarar "
            "cuál."
        ),
    ),
    _item(
        "sat-gram-8",
        habilidad="sat_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "If the city ______ more in public transport, traffic would improve "
            "within a decade."
        ),
        options=["invested", "invests", "would invest", "had invested"],
        correct="invested",
        explanation=(
            "La segunda mitad dice “would improve”, que fija el patrón: "
            "situación hipotética presente = pasado simple en la cláusula "
            "“if” + “would” en la otra. “would "
            "invest” dentro del “if” es el error más común. "
            "“had invested” pertenece a otro patrón, el de lo que ya no "
            "puede pasar, y pediría “would have improved”."
        ),
    ),
    _item(
        "sat-gram-9",
        habilidad="sat_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "The award was shared between Daniel and ______."
        ),
        options=["me", "I", "myself", "mine"],
        correct="me",
        explanation=(
            "Después de una preposición (“between”) va pronombre "
            "objeto. El truco infalible: quita “Daniel and” y lee "
            "“shared between I” — suena mal de inmediato. "
            "“Myself” sólo se usa cuando el sujeto y el objeto son la "
            "misma persona (“I hurt myself”)."
        ),
    ),
]


# ---------------------------------------------------------------------------
# SAT · expresión de ideas
# ---------------------------------------------------------------------------

_ITEMS_SAT_EXPRESION = [
    _item(
        "sat-exp-1",
        habilidad="sat_expresion",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best transition.\n\n"
            "The new bus route is faster than the old one. ______, almost nobody "
            "uses it, because the stops are hard to reach on foot."
        ),
        options=["However", "Therefore", "Similarly", "For example"],
        correct="However",
        explanation=(
            "La segunda frase dice lo contrario de lo que uno esperaría después "
            "de la primera: es más rápida, pero nadie la usa. Eso pide un "
            "conector de contraste. “Therefore” diría que nadie la usa "
            "PORQUE es más rápida. Método para el examen: tapa el conector, "
            "decide tú si las dos frases van en la misma dirección o en "
            "direcciones opuestas, y sólo entonces mira las opciones."
        ),
    ),
    _item(
        "sat-exp-2",
        habilidad="sat_expresion",
        nivel=NIVEL_FUNDAMENTOS,
        question="Which choice states the idea most concisely?",
        options=[
            "The machine stopped because a belt broke.",
            "The reason the machine stopped was because of a belt that was broken.",
            "Due to the fact that a belt broke, the machine stopped.",
            "The machine, which stopped, had a belt that was in a broken state.",
        ],
        correct="The machine stopped because a belt broke.",
        explanation=(
            "Cuando todas las opciones dicen lo mismo y son correctas, gana la "
            "más corta que no pierda información. “The reason… was "
            "because” es redundante (la razón ya es la razón) y “due to "
            "the fact that” son cinco palabras para decir "
            "“because”. Regla práctica: en este examen, la opción más "
            "larga casi nunca es la respuesta."
        ),
    ),
    _item(
        "sat-exp-3",
        habilidad="sat_expresion",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the best transition.\n\n"
            "Fewer students signed up for the trip this year. ______, the school "
            "had to cancel the second bus."
        ),
        options=["Therefore", "Nevertheless", "In contrast", "Meanwhile"],
        correct="Therefore",
        explanation=(
            "La segunda frase es la consecuencia directa de la primera: menos "
            "inscritos, un bus menos. “Nevertheless” e “In "
            "contrast” señalan oposición, que aquí no existe, y "
            "“Meanwhile” señala simultaneidad sin relación causal."
        ),
    ),
    _item(
        "sat-exp-4",
        habilidad="sat_expresion",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A student has taken these notes:\n"
            "• The library opened in 1902.\n"
            "• It holds forty thousand books.\n"
            "• It was paid for by donations from local families.\n\n"
            "The student wants to emphasise HOW THE LIBRARY WAS FUNDED. Which "
            "choice best accomplishes that goal?"
        ),
        options=[
            "Local families paid for the library, which opened in 1902 and now holds forty thousand books.",
            "The library, which opened in 1902, holds forty thousand books.",
            "Opened in 1902, the library holds forty thousand books.",
            "The library has held forty thousand books since it opened in 1902.",
        ],
        correct=(
            "Local families paid for the library, which opened in 1902 and now "
            "holds forty thousand books."
        ),
        explanation=(
            "Este tipo de pregunta no busca la frase “mejor escrita”: "
            "busca la que cumple el objetivo que el enunciado declara en "
            "mayúsculas. Las cuatro opciones son gramaticalmente correctas, pero "
            "sólo una pone la financiación como información principal; las otras "
            "tres ni siquiera la mencionan. Lee siempre el objetivo antes que las "
            "opciones."
        ),
    ),
    _item(
        "sat-exp-5",
        habilidad="sat_expresion",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the most precise word.\n\n"
            "Because the sample included only twelve people, the authors describe "
            "their conclusion as ______."
        ),
        options=["preliminary", "definitive", "exaggerated", "irrelevant"],
        correct="preliminary",
        explanation=(
            "La causa que da la frase (una muestra muy pequeña) obliga a una "
            "conclusión provisional, no a una final. “Definitive” dice "
            "lo contrario de lo que la causa permite; "
            "“exaggerated” e “irrelevant” son juicios "
            "negativos que nadie está haciendo. Un autor que reconoce una "
            "limitación matiza su conclusión, no la desprecia."
        ),
    ),
    _item(
        "sat-exp-6",
        habilidad="sat_expresion",
        nivel=NIVEL_AVANZADO,
        question=(
            "Where should the following sentence be added?\n\n"
            "“When the water gets too warm, corals expel the algae that live "
            "in their tissue.”\n\n"
            "(1) Coral reefs cover less than one percent of the ocean floor. "
            "(2) Even so, a large share of all marine species depend on them. "
            "(3) Warming water breaks that relationship apart. "
            "(4) Without the algae, the coral turns white and eventually starves."
        ),
        options=[
            "After sentence 3",
            "After sentence 1",
            "After sentence 2",
            "After sentence 4",
        ],
        correct="After sentence 3",
        explanation=(
            "La pista está en la frase 4: empieza con “Without the "
            "algae”, y las algas tienen que haber aparecido antes o el "
            "lector no sabe de qué se habla. Además la frase 3 anuncia el efecto "
            "del calentamiento y la frase que hay que insertar lo explica. En "
            "estas preguntas la respuesta casi siempre se decide por un pronombre "
            "o un artículo definido que exige un antecedente."
        ),
    ),
]


# ---------------------------------------------------------------------------
# SAT · lectura y evidencia
# ---------------------------------------------------------------------------

_ITEMS_SAT_LECTURA = [
    _item(
        "sat-read-1",
        habilidad="sat_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="coastlines",
        question="Which choice best states the main idea of the text?",
        options=[
            "Coastlines change over time, so maps now show them as bands instead of fixed lines.",
            "Satellite photographs are sharper than printed maps.",
            "Storms are the main cause of coastal erosion.",
            "Cartographers in the twentieth century made frequent mistakes.",
        ],
        correct=(
            "Coastlines change over time, so maps now show them as bands instead "
            "of fixed lines."
        ),
        explanation=(
            "La idea principal tiene que cubrir el texto entero, no una línea. La "
            "nitidez de las fotos y las tormentas aparecen, pero como detalles de "
            "apoyo. La cuarta convierte en error (“mistakes”) lo que el "
            "texto llama costumbre (“habit”) de una época: cambiarle la "
            "carga al texto es el distractor más frecuente en este examen."
        ),
    ),
    _item(
        "sat-read-2",
        habilidad="sat_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="coastlines",
        question="As used in the text, “hedge” most nearly means",
        options=[
            "avoid committing to a single answer",
            "surround something with plants",
            "protect an investment",
            "hide information on purpose",
        ],
        correct="avoid committing to a single answer",
        explanation=(
            "En vocabulario en contexto no gana el significado más común de la "
            "palabra, gana el que sostiene la frase siguiente: “They show a "
            "band, not a border”, o sea, no se comprometen con una línea "
            "única. “Hedge” también significa seto y cubrirse "
            "financieramente, y por eso están ahí. Estrategia: tapa las opciones, "
            "escribe tu propia palabra a partir del contexto y luego busca cuál "
            "se le parece."
        ),
    ),
    _item(
        "sat-read-3",
        habilidad="sat_lectura",
        nivel=NIVEL_AVANZADO,
        passage="coastlines",
        question=(
            "The text most strongly suggests that the change in mapping practice "
            "was driven by"
        ),
        options=[
            "the ability to observe the same place repeatedly over time",
            "new legal requirements for map publishers",
            "a shortage of trained cartographers",
            "public demand for more attractive maps",
        ],
        correct="the ability to observe the same place repeatedly over time",
        explanation=(
            "La única causa que el texto nombra es “Once the same beach "
            "could be photographed every few days…”. Las otras tres son "
            "explicaciones razonables del mundo real, y por eso son peligrosas: "
            "en este examen una inferencia sólo vale si puedes señalar la línea "
            "que la sostiene. Si tienes que traer información de tu cabeza, no es "
            "la respuesta."
        ),
    ),
    _item(
        "sat-read-4",
        habilidad="sat_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="apology",
        question=(
            "The detail about the brother rinsing “the same clean glass for "
            "the third time” mainly serves to"
        ),
        options=[
            "suggest that he is uncomfortable and not fully present",
            "show that he is unusually careful about hygiene",
            "explain why he did not hear what Ana said",
            "indicate that the kitchen was dirty",
        ],
        correct="suggest that he is uncomfortable and not fully present",
        explanation=(
            "El vaso ya está limpio y lo enjuaga tres veces: es un gesto "
            "repetido y sin propósito, que en narrativa señala incomodidad. La "
            "opción de que no la oyó es tentadora, pero el texto la descarta "
            "porque él responde “okay” al final. Cuando la pregunta "
            "dice “serves to”, está preguntando para qué puso el autor "
            "ese detalle, no qué es literalmente."
        ),
    ),
    _item(
        "sat-read-5",
        habilidad="sat_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="apology",
        question="Which choice best describes the function of the last sentence?",
        options=[
            "It leaves the outcome of the apology unresolved.",
            "It resolves the conflict between the siblings.",
            "It reveals that Ana regrets having apologised.",
            "It explains why Ana rehearsed for two days.",
        ],
        correct="It leaves the outcome of the apology unresolved.",
        explanation=(
            "La frase presenta dos lecturas posibles del “okay” (final "
            "o principio) y no elige ninguna: eso es dejar el desenlace abierto. "
            "Nada en el texto dice que Ana se arrepienta, y el ensayo de dos días "
            "se explica antes, no aquí."
        ),
    ),
    _item(
        "sat-read-6",
        habilidad="sat_lectura",
        nivel=NIVEL_AVANZADO,
        passage="apology",
        question="Based on the text, Ana’s apology is best described as",
        options=[
            "carefully prepared and met with an ambiguous response",
            "careless and delivered in a hurry",
            "insincere and intended to manipulate her brother",
            "openly rejected by her brother",
        ],
        correct="carefully prepared and met with an ambiguous response",
        explanation=(
            "“rehearsed for two days”, “specific” y "
            "“unhurried” sostienen la primera mitad. Para la segunda: "
            "“okay” más irse del cuarto es ambiguo, no un rechazo "
            "explícito, así que la última opción dice más de lo que el texto "
            "autoriza. En opciones de dos partes, verifica que las DOS estén "
            "respaldadas: basta con que una falle para descartarla."
        ),
    ),
]


# ---------------------------------------------------------------------------
# SAT · álgebra
# ---------------------------------------------------------------------------

_ITEMS_SAT_ALGEBRA = [
    _item(
        "sat-alg-1",
        habilidad="sat_algebra",
        nivel=NIVEL_FUNDAMENTOS,
        question="If 3x − 7 = 14, what is the value of x?",
        options=["7", "3", "21", "5"],
        correct="7",
        explanation=(
            "Se suma 7 a los dos lados: 3x = 21. Se divide entre 3: x = 7. El "
            "distractor 21 es el paso intermedio, y está puesto porque mucha "
            "gente resuelve bien y marca antes de terminar. Comprueba siempre "
            "reemplazando: 3(7) − 7 = 14."
        ),
    ),
    _item(
        "sat-alg-2",
        habilidad="sat_algebra",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "A phone plan charges a fixed fee of 12 dollars per month plus 5 "
            "cents per minute of calls. Which equation gives the total cost c, in "
            "dollars, for m minutes in one month?"
        ),
        options=[
            "c = 0.05m + 12",
            "c = 12m + 0.05",
            "c = 12(m + 0.05)",
            "c = 0.05(m + 12)",
        ],
        correct="c = 0.05m + 12",
        explanation=(
            "Lo que se repite por minuto multiplica a la variable; lo que se paga "
            "una sola vez se suma. Aquí lo variable son los 5 centavos por minuto "
            "(0.05m) y lo fijo son los 12 dólares. La segunda opción invierte los "
            "papeles: cobraría 12 dólares por minuto. Ojo con la unidad: 5 "
            "centavos son 0.05 dólares, no 5."
        ),
    ),
    _item(
        "sat-alg-3",
        habilidad="sat_algebra",
        nivel=NIVEL_INTERMEDIO,
        question="If 2x + y = 11 and x − y = 1, what is the value of x?",
        options=["4", "3", "5", "7"],
        correct="4",
        explanation=(
            "Sumando las dos ecuaciones, la y desaparece: 3x = 12, así que x = 4 "
            "(y entonces y = 3). Cuando una variable aparece con signos opuestos "
            "en los dos renglones, sumar es más rápido que despejar. "
            "Verificación: 2(4) + 3 = 11 y 4 − 3 = 1."
        ),
    ),
    _item(
        "sat-alg-4",
        habilidad="sat_algebra",
        nivel=NIVEL_INTERMEDIO,
        question="If 5 − 2x > 1, which of the following must be true?",
        options=["x < 2", "x > 2", "x < −2", "x > −2"],
        correct="x < 2",
        explanation=(
            "Se resta 5: −2x > −4. Al dividir entre −2 hay que "
            "INVERTIR el sentido de la desigualdad: x < 2. Ese cambio de sentido "
            "al multiplicar o dividir por un número negativo es el error que este "
            "tipo de pregunta busca, y por eso la opción x > 2 está ahí. Prueba "
            "con x = 0: 5 − 0 = 5 > 1, y 0 sí cumple x < 2."
        ),
    ),
    _item(
        "sat-alg-5",
        habilidad="sat_algebra",
        nivel=NIVEL_AVANZADO,
        question=(
            "A line passes through the points (2, 5) and (6, 13). What is its "
            "slope?"
        ),
        options=["2", "1/2", "4", "−2"],
        correct="2",
        explanation=(
            "La pendiente es el cambio en y sobre el cambio en x: (13 − 5) / "
            "(6 − 2) = 8/4 = 2. El distractor 1/2 sale de invertir la "
            "fracción, que es el error más común. Basta con mantener el mismo "
            "orden de los puntos arriba y abajo."
        ),
    ),
    _item(
        "sat-alg-6",
        habilidad="sat_algebra",
        nivel=NIVEL_AVANZADO,
        question=(
            "The function f is defined by f(x) = 2x + 1. If f(a) = 9, what is the "
            "value of f(a + 3)?"
        ),
        options=["15", "12", "9", "27"],
        correct="15",
        explanation=(
            "Camino largo: 2a + 1 = 9, entonces a = 4, y f(7) = 15. Camino corto, "
            "que es el que ahorra tiempo en el examen: en una función lineal, "
            "aumentar x en 3 aumenta f en 2 × 3 = 6, así que 9 + 6 = 15. El "
            "distractor 12 sale de sumarle 3 al resultado en vez de a la entrada."
        ),
    ),
]


# ---------------------------------------------------------------------------
# SAT · datos, razones y porcentajes
# ---------------------------------------------------------------------------

_ITEMS_SAT_DATOS = [
    _item(
        "sat-dat-1",
        habilidad="sat_datos",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "A jacket costs 80 dollars. During a sale, its price is reduced by 25 "
            "percent. What is the sale price?"
        ),
        options=["60 dollars", "55 dollars", "75 dollars", "20 dollars"],
        correct="60 dollars",
        explanation=(
            "El 25% de 80 es 20, así que el precio baja a 60. Atajo que sirve "
            "siempre: descontar 25% es multiplicar por 0.75, y 80 × 0.75 = "
            "60. El distractor 20 es el descuento, no el precio final: la "
            "pregunta pide lo que se paga."
        ),
    ),
    _item(
        "sat-dat-2",
        habilidad="sat_datos",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "A recipe uses 3 cups of flour for every 2 cups of milk. If a cook "
            "uses 9 cups of flour, how many cups of milk are needed?"
        ),
        options=["6", "4", "5", "13.5"],
        correct="6",
        explanation=(
            "9 cups de harina son 3 veces las 3 originales, así que la leche "
            "también se triplica: 2 × 3 = 6. En proporciones, escribe la "
            "razón como fracción y resuelve 3/2 = 9/x. El distractor 13.5 sale de "
            "invertir la razón."
        ),
    ),
    _item(
        "sat-dat-3",
        habilidad="sat_datos",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A car travels 240 kilometres in 3 hours. At the same rate, how far "
            "does it travel in 5 hours?"
        ),
        options=["400 kilometres", "300 kilometres", "480 kilometres", "144 kilometres"],
        correct="400 kilometres",
        explanation=(
            "Primero la tasa unitaria: 240/3 = 80 km por hora. Después: 80 "
            "× 5 = 400. Bajar siempre a “por una unidad” convierte "
            "casi todos los problemas de tasas en una multiplicación."
        ),
    ),
    _item(
        "sat-dat-4",
        habilidad="sat_datos",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A data set contains the values 2, 3, 5, 5 and 45. Which statement is "
            "true?"
        ),
        options=[
            "The mean is greater than the median.",
            "The median is greater than the mean.",
            "The mean and the median are equal.",
            "The median cannot be determined.",
        ],
        correct="The mean is greater than the median.",
        explanation=(
            "La media es 60/5 = 12; la mediana es el valor del medio con los "
            "datos ordenados, o sea 5. Un valor extremo (el 45) arrastra la media "
            "y no mueve la mediana. Por eso los ingresos de un país se reportan "
            "con mediana: es la idea que este tipo de pregunta evalúa, más que la "
            "cuenta."
        ),
    ),
    _item(
        "sat-dat-5",
        habilidad="sat_datos",
        nivel=NIVEL_AVANZADO,
        question=(
            "The population of a town grew from 250 to 300. What was the percent "
            "increase?"
        ),
        options=["20 percent", "16.7 percent", "50 percent", "25 percent"],
        correct="20 percent",
        explanation=(
            "La variación porcentual se calcula sobre el valor INICIAL: 50/250 = "
            "0.20, o sea 20%. El distractor 16.7% sale de dividir entre 300, que "
            "es el error clásico; el 50 es el aumento absoluto, no el porcentaje."
        ),
    ),
    _item(
        "sat-dat-6",
        habilidad="sat_datos",
        nivel=NIVEL_AVANZADO,
        question=(
            "In a survey of 200 students, 120 said they walk to school. Of those "
            "120, 45 also play a sport. If one of the students who walk to school "
            "is chosen at random, what is the probability that the student plays "
            "a sport?"
        ),
        options=["3/8", "9/40", "2/5", "3/5"],
        correct="3/8",
        explanation=(
            "La pregunta ya te restringe al subgrupo: “uno de los estudiantes "
            "que caminan”. Entonces el denominador es 120, no 200: 45/120 = "
            "3/8. El distractor 9/40 es 45/200, que respondería otra pregunta "
            "(elegir entre los 200). En tablas de doble entrada, la frase que "
            "define el grupo manda sobre el total."
        ),
    ),
]


# ---------------------------------------------------------------------------
# SAT · álgebra avanzada y geometría
# ---------------------------------------------------------------------------

_ITEMS_SAT_AVANZADO = [
    _item(
        "sat-adv-1",
        habilidad="sat_avanzado",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "A right triangle has legs of length 6 and 8. What is the length of "
            "the hypotenuse?"
        ),
        options=["10", "14", "12", "7"],
        correct="10",
        explanation=(
            "Teorema de Pitágoras: 6² + 8² = 36 + 64 = 100, y la raíz "
            "de 100 es 10. Vale la pena memorizar los tríos 3-4-5 (y sus "
            "múltiplos, como este 6-8-10) y 5-12-13: aparecen todo el tiempo y "
            "ahorran la cuenta. El 14 sale de sumar los catetos, que nunca es la "
            "hipotenusa."
        ),
    ),
    _item(
        "sat-adv-2",
        habilidad="sat_avanzado",
        nivel=NIVEL_INTERMEDIO,
        question="What are the solutions of x² − 5x + 6 = 0?",
        options=[
            "x = 2 and x = 3",
            "x = −2 and x = −3",
            "x = 1 and x = 6",
            "x = −1 and x = −6",
        ],
        correct="x = 2 and x = 3",
        explanation=(
            "Se buscan dos números que multiplicados den 6 y sumados den 5: son 2 "
            "y 3, así que la expresión se factoriza como (x − 2)(x − 3) "
            "= 0. Ojo con los signos: los factores llevan menos, pero las "
            "soluciones son positivas. Si dudas, reemplaza: 2² − 5(2) + "
            "6 = 0."
        ),
    ),
    _item(
        "sat-adv-3",
        habilidad="sat_avanzado",
        nivel=NIVEL_INTERMEDIO,
        question="The graph of y = (x − 3)² + 4 has its vertex at",
        options=["(3, 4)", "(−3, 4)", "(3, −4)", "(4, 3)"],
        correct="(3, 4)",
        explanation=(
            "En la forma y = (x − h)² + k el vértice es (h, k), y el "
            "signo de h aparece invertido dentro del paréntesis: “− "
            "3” significa h = 3. Ese cambio de signo es justamente lo que la "
            "pregunta evalúa."
        ),
    ),
    _item(
        "sat-adv-4",
        habilidad="sat_avanzado",
        nivel=NIVEL_INTERMEDIO,
        question="A circle has an area of 36π. What is its radius?",
        options=["6", "9", "18", "12"],
        correct="6",
        explanation=(
            "El área es πr², así que r² = 36 y r = 6. El "
            "distractor 18 sale de confundir el área con el perímetro (2πr), "
            "y el 12 de calcular el diámetro."
        ),
    ),
    _item(
        "sat-adv-5",
        habilidad="sat_avanzado",
        nivel=NIVEL_AVANZADO,
        question=(
            "A bacterial culture starts with 500 cells and doubles every 3 hours. "
            "Which expression gives the number of cells after t hours?"
        ),
        options=[
            "500 · 2^(t/3)",
            "500 · 2^(3t)",
            "500 · 3^(t/2)",
            "500 + 2t",
        ],
        correct="500 · 2^(t/3)",
        explanation=(
            "En crecimiento exponencial, la base es POR CUÁNTO se multiplica (2, "
            "porque duplica) y el exponente es CUÁNTAS VECES ya ocurrió eso: t "
            "horas divididas entre las 3 que tarda cada duplicación. Comprueba "
            "con t = 3: 500 · 2¹ = 1000. La opción 2^(3t) triplicaría la "
            "velocidad en vez de dividirla."
        ),
    ),
    _item(
        "sat-adv-6",
        habilidad="sat_avanzado",
        nivel=NIVEL_AVANZADO,
        question=(
            "In right triangle ABC, angle C measures 90 degrees, AB = 13 and BC = "
            "5. What is sin A?"
        ),
        options=["5/13", "12/13", "5/12", "13/5"],
        correct="5/13",
        explanation=(
            "El seno es cateto opuesto sobre hipotenusa. El ángulo recto está en "
            "C, así que la hipotenusa es AB = 13. El lado opuesto al ángulo A es "
            "BC = 5 (el que no lo toca). Entonces sin A = 5/13. El 12/13 es el "
            "coseno, y está ahí porque identificar mal cuál lado es el opuesto es "
            "el error típico."
        ),
    ),
]


# ---------------------------------------------------------------------------
# IELTS · comprensión de lectura académica
# ---------------------------------------------------------------------------

_ITEMS_IELTS_LECTURA = [
    _item(
        "ielts-read-1",
        habilidad="ielts_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="urban_bees",
        question=(
            "According to the text, why do city hives often produce more honey "
            "than rural ones?"
        ),
        options=[
            "City plants flower over a longer period and are sprayed less often.",
            "Cities are warmer than the surrounding countryside.",
            "Urban bees belong to a different species.",
            "Beekeepers in cities are more experienced.",
        ],
        correct=(
            "City plants flower over a longer period and are sprayed less often."
        ),
        explanation=(
            "El texto da exactamente dos razones y las numera "
            "(“First… Second…”): floración escalonada y menos "
            "pesticidas. Las otras tres son explicaciones plausibles que el texto "
            "nunca menciona. En este tipo de examen, plausible no es lo mismo que "
            "dicho: busca las palabras señal (“first”, "
            "“second”, “because”) para localizar la respuesta "
            "sin releer todo."
        ),
    ),
    _item(
        "ielts-read-2",
        habilidad="ielts_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="urban_bees",
        question=(
            "Decide whether the statement agrees with the text.\n\n"
            "Statement: “Pollution has no effect on bees living in "
            "cities.”"
        ),
        options=["False", "True", "Not Given"],
        correct="False",
        explanation=(
            "El texto dice lo contrario: “pollution shortens the life of "
            "individual workers”. Cuando el texto CONTRADICE la afirmación, "
            "la respuesta es False. Se reserva “Not Given” para cuando "
            "el texto no dice nada del asunto, ni a favor ni en contra. Confundir "
            "esas dos es lo que más puntos cuesta en esta sección."
        ),
    ),
    _item(
        "ielts-read-3",
        habilidad="ielts_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="urban_bees",
        question=(
            "Decide whether the statement agrees with the text.\n\n"
            "Statement: “Rooftop hives are more expensive to maintain than "
            "rural hives.”"
        ),
        options=["Not Given", "True", "False"],
        correct="Not Given",
        explanation=(
            "Suena razonable, y por eso es la trampa: el texto nunca compara "
            "costos de mantenimiento. Habla de producción de miel, de floración, "
            "de pesticidas y de contaminación, pero de dinero no dice ni una "
            "palabra. La regla es dura y es la que hay que practicar: si no "
            "puedes subrayar la línea, no es True ni es False."
        ),
    ),
    _item(
        "ielts-read-4",
        habilidad="ielts_lectura",
        nivel=NIVEL_AVANZADO,
        passage="urban_bees",
        question="What is the writer’s main purpose in the final sentence?",
        options=[
            "To qualify the earlier claim by pointing out drawbacks",
            "To recommend that cities ban beekeeping",
            "To explain how a swarm is relocated",
            "To compare several European capitals",
        ],
        correct="To qualify the earlier claim by pointing out drawbacks",
        explanation=(
            "“Cities are not paradise, however” avisa el giro: viene un "
            "matiz a lo bueno que se dijo antes, no una recomendación ni una "
            "instrucción. Las preguntas de propósito se resuelven mirando el "
            "conector, no el contenido: “however”, “yet” y "
            "“on the other hand” anuncian matiz."
        ),
    ),
    _item(
        "ielts-read-5",
        habilidad="ielts_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="night_trains",
        question=(
            "Which of the following is given as a COMMERCIAL rather than "
            "environmental reason for the return of night trains?"
        ),
        options=[
            "They save the traveller the cost of a hotel night.",
            "They produce fewer emissions than flying.",
            "Travellers feel nostalgic about them.",
            "New safety rules encourage them.",
        ],
        correct="They save the traveller the cost of a hotel night.",
        explanation=(
            "El texto separa los dos tipos de razón: primero la ambiental "
            "(emisiones) y después “But operators point to something less "
            "obvious”, que es la de plata. La pregunta pide la segunda "
            "categoría, así que la de emisiones es correcta como dato y "
            "equivocada como respuesta. Lee siempre qué categoría te piden."
        ),
    ),
    _item(
        "ielts-read-6",
        habilidad="ielts_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="night_trains",
        question=(
            "Complete the sentence according to the text.\n\n"
            "Sleeper carriages are costly partly because they ______."
        ),
        options=[
            "are not used during the daytime",
            "must cross four countries",
            "require larger crews than other trains",
            "are built in only one country",
        ],
        correct="are not used during the daytime",
        explanation=(
            "El texto dice “they sit unused during the day”, y la "
            "opción correcta lo parafrasea. Las otras usan palabras que SÍ "
            "aparecen en el texto (“four countries”) pero contestan otra "
            "cosa: allí se habla de normas de seguridad, no de costo. Ese es el "
            "distractor típico de esta sección — repetir vocabulario del texto "
            "para que suene familiar."
        ),
    ),
    _item(
        "ielts-read-7",
        habilidad="ielts_lectura",
        nivel=NIVEL_AVANZADO,
        passage="night_trains",
        question=(
            "Decide whether the statement agrees with the writer’s view.\n\n"
            "Statement: “The writer believes nostalgia is the main obstacle "
            "to night trains.”"
        ),
        options=["False", "True", "Not Given"],
        correct="False",
        explanation=(
            "“The obstacles are practical rather than romantic” dice "
            "exactamente lo contrario. Aquí sí hay contradicción explícita, así "
            "que es False y no Not Given. Cuando la pregunta es sobre la OPINIÓN "
            "del autor, busca las frases donde valora (“rather than”, "
            "“less obvious”), no los datos."
        ),
    ),
    _item(
        "ielts-read-8",
        habilidad="ielts_lectura",
        nivel=NIVEL_AVANZADO,
        passage="night_trains",
        question=(
            "In the phrase “the obstacles are practical rather than "
            "romantic”, the word “romantic” refers to"
        ),
        options=[
            "an idealised view of travelling by train",
            "love stories set on trains",
            "the price of a sleeper ticket",
            "a nineteenth-century style of design",
        ],
        correct="an idealised view of travelling by train",
        explanation=(
            "La oposición con “practical” define el sentido: lo "
            "contrario de lo práctico aquí es lo idealizado, no el amor. En "
            "vocabulario en contexto, el sentido lo fija la palabra con la que se "
            "contrasta, no el diccionario."
        ),
    ),
]


# ---------------------------------------------------------------------------
# IELTS · vocabulario académico
# ---------------------------------------------------------------------------

_ITEMS_IELTS_VOCABULARIO = [
    _item(
        "ielts-voc-1",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best word.\n\n"
            "The researchers ______ a survey of four hundred households."
        ),
        options=["conducted", "made", "did", "took"],
        correct="conducted",
        explanation=(
            "“Conduct a survey / a study / an experiment” es la "
            "colocación que se usa en escritura académica. “Make a "
            "survey” no es idiomático y “take a survey” significa "
            "responderla, no realizarla: cambia quién hace qué. Aprender verbos y "
            "sustantivos en pareja rinde más que aprender palabras sueltas."
        ),
    ),
    _item(
        "ielts-voc-2",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best word.\n\n"
            "The government has ______ measures to reduce plastic waste."
        ),
        options=["introduced", "entered", "arrived", "placed"],
        correct="introduced",
        explanation=(
            "“Introduce measures / a policy / a law” es la combinación "
            "habitual. “Enter” y “arrive” no toman este "
            "objeto, y “place” pide algo físico. Fíjate en que "
            "“introducir” en español y “introduce” en inglés "
            "no siempre coinciden: en inglés no se usa para meter algo dentro de "
            "otra cosa."
        ),
    ),
    _item(
        "ielts-voc-3",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the best word.\n\n"
            "The two studies reached ______ conclusions: one found a clear "
            "benefit, the other found none."
        ),
        options=["conflicting", "similar", "consecutive", "mutual"],
        correct="conflicting",
        explanation=(
            "Los dos puntos anuncian la explicación, y lo que sigue son dos "
            "resultados opuestos: eso es “conflicting”. "
            "“Similar” contradice la frase, “consecutive” "
            "habla de orden y “mutual” de algo compartido. Cuando hay "
            "dos puntos, la respuesta casi siempre está después de ellos."
        ),
    ),
    _item(
        "ielts-voc-4",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the best word.\n\n"
            "Housing prices rose ______ over the period, more than doubling in "
            "some districts."
        ),
        options=["sharply", "slightly", "narrowly", "barely"],
        correct="sharply",
        explanation=(
            "“More than doubling” obliga a un adverbio de magnitud "
            "grande. Los otros tres apuntan a un cambio mínimo, así que "
            "contradicen la propia frase. Este vocabulario de magnitud "
            "(sharply, steadily, slightly, gradually) es el que más se usa al "
            "describir gráficas, y usarlo mal es lo que hace que una descripción "
            "correcta suene equivocada."
        ),
    ),
    _item(
        "ielts-voc-5",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the best word.\n\n"
            "The results should be treated with caution because the sample was "
            "not ______ of the wider population."
        ),
        options=["representative", "responsible", "respective", "reliable"],
        correct="representative",
        explanation=(
            "“Representative of” significa que la muestra refleja al "
            "grupo grande, que es justo lo que la frase discute. Los otros tres "
            "son parónimos que suenan parecido y significan otra cosa: "
            "“respective” es “respectivo” y "
            "“reliable” es fiable, que se dice de un método, no de una "
            "muestra frente a una población."
        ),
    ),
    _item(
        "ielts-voc-6",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the best word.\n\n"
            "Although the policy was well designed, its ______ was delayed by a "
            "lack of funding."
        ),
        options=["implementation", "implication", "imposition", "impression"],
        correct="implementation",
        explanation=(
            "Lo que se retrasa por falta de plata es la puesta en marcha: "
            "“implementation”. “Implication” es una "
            "consecuencia o algo que se sobreentiende, e “imposition” "
            "añade una carga de obligación que la frase no tiene. Cuatro palabras "
            "con la misma raíz visual y significados distintos: en escritura "
            "académica esta familia se confunde todo el tiempo."
        ),
    ),
]


# ---------------------------------------------------------------------------
# IELTS · estructuras del inglés académico
# ---------------------------------------------------------------------------

_ITEMS_IELTS_GRAMATICA = [
    _item(
        "ielts-gram-1",
        habilidad="ielts_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the correct option.\n\n"
            "She is studying ______ engineering at a university in Canada."
        ),
        options=["(no article)", "the", "a", "an"],
        correct="(no article)",
        explanation=(
            "Los nombres de disciplinas y de materias de estudio van sin artículo "
            "cuando se habla de ellas en general: “study engineering”, "
            "“study medicine”. El artículo reaparece cuando se "
            "especifica (“the engineering of the bridge”). Para quien "
            "habla español éste es de los errores más persistentes, porque en "
            "español sí decimos “estudia la ingeniería”."
        ),
    ),
    _item(
        "ielts-gram-2",
        habilidad="ielts_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the correct option.\n\n"
            "There has been a steady increase ______ the number of applicants."
        ),
        options=["in", "of", "on", "for"],
        correct="in",
        explanation=(
            "“An increase IN” se usa para decir QUÉ aumentó; “an "
            "increase OF” se reserva para la magnitud (“an increase of "
            "twenty percent”). Las dos existen y significan cosas "
            "diferentes, y esta pareja aparece en casi cualquier descripción de "
            "datos, así que vale la pena fijarla."
        ),
    ),
    _item(
        "ielts-gram-3",
        habilidad="ielts_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the correct option.\n\n"
            "______ the evidence is limited, the authors argue that the trend is "
            "real."
        ),
        options=["Although", "Despite", "However", "In spite"],
        correct="Although",
        explanation=(
            "Lo que sigue es una oración completa (sujeto + verbo), y eso pide "
            "una conjunción: “although”. “Despite” necesita "
            "un sustantivo o un “-ing” (“despite the limited "
            "evidence”), “however” une dos oraciones ya separadas "
            "por punto o punto y coma, y “in spite” está incompleto: le "
            "falta “of”."
        ),
    ),
    _item(
        "ielts-gram-4",
        habilidad="ielts_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the correct option.\n\n"
            "The samples ______ at three different temperatures."
        ),
        options=["were tested", "were testing", "have tested", "testing"],
        correct="were tested",
        explanation=(
            "Las muestras no prueban: son probadas, así que va pasiva (verbo to "
            "be + participio). “Were testing” las convierte en quien "
            "hace la prueba. La pasiva es habitual en escritura académica cuando "
            "importa el procedimiento y no quién lo ejecutó, pero abusar de ella "
            "vuelve el texto pesado: úsala cuando el agente no aporte."
        ),
    ),
    _item(
        "ielts-gram-5",
        habilidad="ielts_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the correct option.\n\n"
            "The students ______ in the first group finished sooner than the "
            "others."
        ),
        options=["placed", "who placed", "were placed", "placing"],
        correct="placed",
        explanation=(
            "Es una cláusula relativa reducida: “the students who were "
            "placed in the first group” se acorta quitando “who "
            "were”. “Who placed” cambia el sentido (serían ellos "
            "quienes colocan a alguien) y “were placed” dejaría la "
            "oración con dos verbos principales. Reducir relativas es una de las "
            "formas más limpias de escribir frases complejas sin enredarlas."
        ),
    ),
    _item(
        "ielts-gram-6",
        habilidad="ielts_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the correct option.\n\n"
            "If funding ______ available next year, the trial will continue."
        ),
        options=["is", "were", "would be", "will be"],
        correct="is",
        explanation=(
            "La otra mitad dice “will continue”: es una condición real "
            "sobre el futuro, así que la cláusula “if” va en presente. "
            "Poner “will” dentro del “if” es el error más "
            "repetido, y “were” pertenece al patrón hipotético, que "
            "pediría “would continue”."
        ),
    ),
]


# ---------------------------------------------------------------------------
# IELTS · decisiones de escritura
#
# Se practica ELIGIENDO, no escribiendo. Motivo explícito (y honesto): no
# calificamos ensayos con IA. Un puntaje automático de escritura sería
# justamente el tipo de dato inventado que este proyecto ya se cobró una vez.
# ---------------------------------------------------------------------------

_ITEMS_IELTS_ESCRITURA = [
    _item(
        "ielts-writ-1",
        habilidad="ielts_escritura",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "A line graph shows a company’s sales rising over a decade, with "
            "a temporary fall in the middle year. Which sentence works best as "
            "the overall summary?"
        ),
        options=[
            "Overall, sales increased over the decade, despite a temporary fall in the middle of the period.",
            "In the middle year, sales were lower than in the year before.",
            "Sales are an important indicator of a company’s health.",
            "The graph shows the sales of a company over ten years.",
        ],
        correct=(
            "Overall, sales increased over the decade, despite a temporary fall "
            "in the middle of the period."
        ),
        explanation=(
            "El resumen general describe la tendencia de todo el período y la "
            "excepción más visible. La segunda opción es un dato puntual (va en "
            "el cuerpo, no en el resumen), la tercera es una opinión que el "
            "gráfico no muestra y la cuarta sólo repite el enunciado sin decir "
            "qué pasó. Regla práctica: si tu resumen no tiene una dirección "
            "(subió, bajó, se mantuvo), todavía no es un resumen."
        ),
    ),
    _item(
        "ielts-writ-2",
        habilidad="ielts_escritura",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Task prompt: “Some people think that children should start "
            "school at the age of four.”\n\n"
            "Which sentence is the best paraphrase to open your answer?"
        ),
        options=[
            "It is sometimes argued that formal education should begin in early childhood.",
            "Some people think that children should begin school when they are four.",
            "I completely disagree with sending children to school at four.",
            "Children are the future of every society.",
        ],
        correct=(
            "It is sometimes argued that formal education should begin in early "
            "childhood."
        ),
        explanation=(
            "Parafrasear es cambiar estructura y vocabulario conservando el "
            "sentido. La segunda opción sólo cambia una palabra, así que sigue "
            "siendo copiar. La tercera adelanta la postura antes de presentar el "
            "tema y la cuarta es relleno que no dice nada del asunto. Copiar el "
            "enunciado tal cual es la forma más rápida de empezar mal."
        ),
    ),
    _item(
        "ielts-writ-3",
        habilidad="ielts_escritura",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A figure moves from 48 percent in one year to 51 percent the "
            "following year. Which sentence describes the change most "
            "accurately?"
        ),
        options=[
            "The figure rose slightly, from 48 percent to 51 percent.",
            "The figure rose dramatically to 51 percent.",
            "The figure almost doubled.",
            "The figure remained unchanged.",
        ],
        correct="The figure rose slightly, from 48 percent to 51 percent.",
        explanation=(
            "Tres puntos porcentuales son un cambio pequeño: describirlo como "
            "dramático exagera y describirlo como estable niega el cambio. "
            "Exagerar la magnitud es el error más caro al describir datos, porque "
            "quien lee el gráfico ve de inmediato que la palabra no corresponde. "
            "Di el cambio y ancla las dos cifras."
        ),
    ),
    _item(
        "ielts-writ-4",
        habilidad="ielts_escritura",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Which sentence best continues this one?\n\n"
            "“Cities are expanding faster than their public transport "
            "networks.”"
        ),
        options=[
            "As a result, commuting times have grown in most large capitals.",
            "Moreover, buses are painted yellow in some countries.",
            "In contrast, cities are expanding quickly.",
            "For example, transport is important.",
        ],
        correct="As a result, commuting times have grown in most large capitals.",
        explanation=(
            "La continuación tiene que avanzar la idea y el conector tiene que "
            "describir de verdad la relación. La segunda es información "
            "irrelevante, la tercera anuncia contraste y repite lo mismo, y la "
            "cuarta anuncia un ejemplo y da una generalidad. Un conector mal "
            "usado desorienta más que no poner ninguno."
        ),
    ),
    _item(
        "ielts-writ-5",
        habilidad="ielts_escritura",
        nivel=NIVEL_AVANZADO,
        question=(
            "The task asks: “To what extent do you agree?” Which "
            "sentence states the clearest position?"
        ),
        options=[
            "I largely agree, although the measure should apply only to secondary schools.",
            "There are advantages and disadvantages to consider.",
            "This essay will discuss both sides of the argument.",
            "It depends on many different factors.",
        ],
        correct=(
            "I largely agree, although the measure should apply only to secondary "
            "schools."
        ),
        explanation=(
            "“To what extent” pide postura Y grado. La opción correcta "
            "dice cuánto se está de acuerdo y en qué condición; las otras tres "
            "evitan comprometerse, y una respuesta que no toma posición no puede "
            "responder la pregunta que le hicieron. Matizar no es lo mismo que no "
            "responder."
        ),
    ),
    _item(
        "ielts-writ-6",
        habilidad="ielts_escritura",
        nivel=NIVEL_AVANZADO,
        question=(
            "Which sentence best develops the claim “remote work reduces "
            "commuting emissions”?"
        ),
        options=[
            "If an employee who drives thirty kilometres a day stays at home twice a week, two fifths of that travel disappears.",
            "Many people enjoy working from home.",
            "Emissions are a serious problem worldwide.",
            "Remote work has become increasingly popular.",
        ],
        correct=(
            "If an employee who drives thirty kilometres a day stays at home "
            "twice a week, two fifths of that travel disappears."
        ),
        explanation=(
            "Desarrollar una afirmación es explicar el mecanismo con un caso "
            "concreto, y aquí la cuenta se sigue sola: dos días de cinco son dos "
            "quintos del trayecto semanal. Las otras tres cambian de tema, "
            "repiten la idea general o dicen algo cierto que no sostiene la "
            "afirmación. Un párrafo se sostiene con el ejemplo, no con el "
            "adjetivo."
        ),
    ),
]


# ---------------------------------------------------------------------------
# El banco completo
# ---------------------------------------------------------------------------

EXAM_PREP_ITEMS: List[Dict[str, Any]] = [
    *_ITEMS_SAT_GRAMATICA,
    *_ITEMS_SAT_EXPRESION,
    *_ITEMS_SAT_LECTURA,
    *_ITEMS_SAT_ALGEBRA,
    *_ITEMS_SAT_DATOS,
    *_ITEMS_SAT_AVANZADO,
    *_ITEMS_IELTS_LECTURA,
    *_ITEMS_IELTS_VOCABULARIO,
    *_ITEMS_IELTS_GRAMATICA,
    *_ITEMS_IELTS_ESCRITURA,
]

_ITEM_POR_ID = {i["id"]: i for i in EXAM_PREP_ITEMS}
if len(_ITEM_POR_ID) != len(EXAM_PREP_ITEMS):
    raise ValueError("hay ids de ejercicio repetidos en el banco")


def _contar(exam_id: str) -> int:
    return sum(1 for i in EXAM_PREP_ITEMS if i["exam"] == exam_id)


# ---------------------------------------------------------------------------
# Las fichas de cada examen
#
# Contrato de `vocational_tests.py` + los campos propios de este módulo
# (`disclaimer`, `trademark`, `format`, `notCovered`, `languages`).
# ---------------------------------------------------------------------------

EXAMENES: List[Dict[str, Any]] = [
    {
        "id": EXAMEN_SAT,
        "slug": "practica-sat",
        "name": "Práctica de habilidades para el SAT",
        "shortName": "Práctica SAT",
        "description": (
            "Ejercicios propios para practicar lo que el SAT evalúa: lectura con "
            "evidencia, convenciones del inglés escrito, álgebra, datos y "
            "geometría. Cada ejercicio viene con la explicación de por qué la "
            "respuesta correcta lo es."
        ),
        "academicBasis": (
            "Material de práctica escrito por el equipo de Mentoring. No son "
            "preguntas del examen ni de ningún proveedor, no está avalado por "
            "College Board y no predice tu puntaje: practica las habilidades, no "
            "reproduce el instrumento."
        ),
        "estimatedMinutes": 20,
        "questionCount": _contar(EXAMEN_SAT),
        "icon": "target",
        "audiencia": (
            "Pensado para grados 11 y 12, que es cuando esta preparación cae en "
            "el momento útil."
        ),
        "formato": [
            "El examen se presenta en inglés, incluida la parte de matemáticas.",
            "Hay una parte de lectura y escritura y otra de matemáticas.",
            "Casi todo es de opción múltiple, con algunas preguntas de respuesta "
            "numérica en matemáticas.",
            "Las preguntas de lectura vienen con un texto corto y se responden "
            "sólo con lo que el texto dice.",
        ],
        "no_cubierto": [
            {
                "que": "Un simulacro completo y cronometrado",
                "porque": (
                    "Administrar el tiempo real del examen requiere el examen "
                    "real. Aquí se practica habilidad por habilidad."
                ),
            },
            {
                "que": "Preguntas de respuesta numérica abierta",
                "porque": (
                    "Todo el banco es de opción múltiple para poder explicarte "
                    "también por qué las otras opciones no sirven."
                ),
            },
        ],
    },
    {
        "id": EXAMEN_IELTS,
        "slug": "practica-ielts",
        "name": "Práctica de habilidades para el IELTS",
        "shortName": "Práctica IELTS",
        "description": (
            "Ejercicios propios de lectura académica, vocabulario, estructuras "
            "del inglés formal y decisiones de escritura, cada uno con su "
            "explicación."
        ),
        "academicBasis": (
            "Material de práctica escrito por el equipo de Mentoring. No son "
            "preguntas del examen ni de ningún proveedor, no está avalado por los "
            "titulares del IELTS y no estima la banda que obtendrías."
        ),
        "estimatedMinutes": 20,
        "questionCount": _contar(EXAMEN_IELTS),
        "icon": "globe",
        "audiencia": (
            "Pensado para quien está mirando estudiar fuera del país o quiere "
            "reforzar su inglés antes de presentar un examen internacional."
        ),
        "formato": [
            "Todo el examen se presenta en inglés.",
            "Tiene cuatro partes: comprensión auditiva, lectura, escritura y una "
            "entrevista oral con un examinador.",
            "En lectura hay preguntas donde debes decidir si una afirmación "
            "coincide con el texto, lo contradice o simplemente no aparece.",
            "En escritura hay una tarea de describir información y otra de "
            "argumentar una postura.",
        ],
        "no_cubierto": [
            {
                "que": "Comprensión auditiva (listening)",
                "porque": (
                    "Necesita audio grabado propio y todavía no lo tenemos. "
                    "Preferimos decírtelo a que asumas que está cubierto."
                ),
            },
            {
                "que": "Entrevista oral (speaking)",
                "porque": (
                    "Se practica hablando con una persona. Coordínalo con tu "
                    "asesor o tu profesor de inglés."
                ),
            },
            {
                "que": "Calificación de ensayos",
                "porque": (
                    "No le ponemos puntaje automático a un texto tuyo: sería "
                    "inventarte una nota. La práctica de escritura de aquí es de "
                    "decisiones (qué frase funciona mejor y por qué)."
                ),
            },
        ],
    },
]

_EXAMEN_POR_ID = {e["id"]: e for e in EXAMENES}


# ---------------------------------------------------------------------------
# Consultas puras sobre el banco
# ---------------------------------------------------------------------------

def get_examen(exam_id: str) -> Optional[Dict[str, Any]]:
    """La ficha del examen, o None (mismo criterio que `get_test_by_id`)."""
    return _EXAMEN_POR_ID.get(exam_id)


def get_habilidad(skill_id: str) -> Optional[Dict[str, Any]]:
    return _HABILIDAD_POR_ID.get(skill_id)


def habilidades_de(exam_id: str) -> List[Dict[str, Any]]:
    """Las habilidades de un examen, con cuántos ejercicios tiene cada una."""
    salida = []
    for h in HABILIDADES:
        if h["exam"] != exam_id:
            continue
        entrada = dict(h)
        entrada["itemCount"] = sum(
            1 for i in EXAM_PREP_ITEMS if i["skill"] == h["id"]
        )
        entrada["levels"] = sorted(
            {i["level"] for i in EXAM_PREP_ITEMS if i["skill"] == h["id"]},
            key=NIVELES.index,
        )
        salida.append(entrada)
    return salida


def get_item(item_id: str) -> Optional[Dict[str, Any]]:
    return _ITEM_POR_ID.get(item_id)


def items(
    *,
    exam_id: Optional[str] = None,
    skill_id: Optional[str] = None,
    nivel: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Los ejercicios que cumplen los filtros, en el orden del banco.

    El orden es estable a propósito: dos estudiantes con el mismo perfil ven la
    misma sesión, y los tests no dependen de un `random`.
    """
    salida = []
    for i in EXAM_PREP_ITEMS:
        if exam_id and i["exam"] != exam_id:
            continue
        if skill_id and i["skill"] != skill_id:
            continue
        if nivel and i["level"] != nivel:
            continue
        salida.append(i)
    return salida


def texto(passage_id: str) -> Optional[str]:
    return _TEXTOS.get(passage_id)


def item_publico(item: Dict[str, Any]) -> Dict[str, Any]:
    """El ejercicio SIN la respuesta ni la explicación, para mandarlo al front.

    Mismo criterio que `english_test_questions.get_questions_for_client`: la
    clave nunca sale del servidor antes de que el estudiante responda.
    """
    publico = {
        "id": item["id"],
        "exam": item["exam"],
        "skill": item["skill"],
        "level": item["level"],
        "type": item["type"],
        "question": item["question"],
        "options": list(item["options"]),
    }
    if item["passage_id"]:
        publico["passage"] = _TEXTOS[item["passage_id"]]
    return publico
