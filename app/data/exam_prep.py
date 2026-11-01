"""Bancos de PRÁCTICA para exámenes de admisión (SAT · IELTS · Saber 11).

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

## Saber 11 (Sprint 4, I-4/I-5): propio, y por una razón concreta

Los cuadernillos de preguntas que publica el Icfes **no se pueden usar aquí**.
Sus términos de uso (leídos en el cuadernillo de Matemáticas Saber 11 de marzo
de 2026, p. 3) prohíben el uso total o parcial "con fines de lucro", directo o
indirecto, y prohíben la "transformación" (adaptarlos o reescribirlos). Mentoring
es una plataforma comercial. Por eso los ejercicios de Saber 11 son propios,
modelados sobre la estructura pública del examen (sus cinco pruebas y lo que
evalúa cada una), sin copiar ni adaptar ninguna pregunta del Icfes. Por la misma
razón el producto se llama "Práctica Saber 11" y no usa el nombre del instituto
(decisión de JP, 2026-10-31): sus marcas son registradas.

Los enunciados de Saber 11 van en **español** (el examen se presenta en
español), salvo la prueba de inglés.

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
EXAMEN_SABER11 = "saber11"
EXAMENES_IDS = (EXAMEN_SAT, EXAMEN_IELTS, EXAMEN_SABER11)

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
    EXAMEN_SABER11: (
        "Saber 11 es el examen de Estado que administra el Icfes. Mentoring no "
        "está afiliado al Icfes ni avalado por él, y este material no proviene "
        "de sus publicaciones: los ejercicios los escribimos nosotros."
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
    # --- Saber 11 (Sprint 4 · I-5) -----------------------------------------
    # Las cinco pruebas del examen. Solo la de inglés arranca en el nivel del
    # diagnóstico de inglés; las demás no tienen diagnóstico propio.
    {
        "id": "s11_lectura",
        "exam": EXAMEN_SABER11,
        "name": "Lectura crítica",
        "description": (
            "Entender lo que dice un texto, cómo está armado y qué postura toma: "
            "idea principal, función de un párrafo, supuestos y argumentos."
        ),
        "dependsOnEnglish": False,
    },
    {
        "id": "s11_matematicas",
        "exam": EXAMEN_SABER11,
        "name": "Matemáticas",
        "description": (
            "Interpretar tablas y gráficas, porcentajes y proporciones, "
            "ecuaciones, geometría y probabilidad aplicadas a situaciones reales."
        ),
        "dependsOnEnglish": False,
    },
    {
        "id": "s11_sociales",
        "exam": EXAMEN_SABER11,
        "name": "Sociales y ciudadanas",
        "description": (
            "La Constitución y los derechos, cómo funciona el Estado, y analizar "
            "una situación desde las perspectivas de quienes participan en ella."
        ),
        "dependsOnEnglish": False,
    },
    {
        "id": "s11_ciencias",
        "exam": EXAMEN_SABER11,
        "name": "Ciencias naturales",
        "description": (
            "Biología, química y física desde la indagación: leer un "
            "experimento, explicar un fenómeno y sacar conclusiones de los datos."
        ),
        "dependsOnEnglish": False,
    },
    # s11_ingles se suma con sus ejercicios (tanda 3): una habilidad sin
    # ejercicios rompe la regla de que todas tienen los tres niveles
    # (`test_cada_habilidad_tiene_ejercicios…`).
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
    # I-1b · Sprint 4 · textos propios para la ampliación de lectura del SAT.
    # Escritos para este repo; ninguno viene de un examen ni de un libro.
    "sleep_memory": (
        "Sleep and Memory\n\n"
        "In a small study, twenty-four university students memorised a list of "
        "forty word pairs in the evening. Half of them then slept normally; the "
        "other half stayed awake in the laboratory. The next afternoon, after "
        "both groups had rested, the students who had slept recalled about a "
        "third more pairs than those who had not. The researchers argue that "
        "sleep does not simply protect memories from interference but actively "
        "strengthens them. They are careful, however, to call their result a "
        "starting point: the group was small, and every participant was a "
        "student between eighteen and twenty-two."
    ),
    "market_morning": (
        "Every Saturday my grandfather bargained for tomatoes he had already "
        "decided to buy. He would lift one, frown at it as though it had "
        "personally disappointed him, and name a price so low that the seller "
        "laughed. Then the real conversation began: about the rain, about the "
        "seller's daughter, about a bus route that had been cancelled in 1987. "
        "By the time the tomatoes went into his bag, the price had stopped "
        "mattering to either of them. I was twelve before I understood that he "
        "had never once been shopping."
    ),
    "postal_codes": (
        "Paying for a Letter\n\n"
        "In much of eighteenth-century Europe, the person who received a letter, "
        "not the person who sent it, paid the postage. The cost depended on the "
        "distance and the number of sheets, and for many families it was a "
        "real expense. Some correspondents found a way around it. They agreed "
        "in advance on small marks — a dot in a corner, a particular way of "
        "writing the address — that carried a short message by themselves. The "
        "receiver would read the outside of the letter, learn that all was "
        "well, and politely refuse to pay. The practice was one of the reasons "
        "reformers later argued that senders should pay in advance."
    ),
    "glaciers": (
        "Retreating Glaciers\n\n"
        "A survey of thirty mountain glaciers measured how far the front edge of "
        "each one moved between 2000 and 2020. Twenty-six of them retreated, "
        "with a median loss of about 400 metres. Of the four that did not, "
        "three were in a single valley that received unusually heavy snowfall "
        "during the period, and one could not be measured reliably after a "
        "landslide covered its edge. The authors conclude that the overall "
        "pattern is clear, but they warn against using the few stable glaciers "
        "as evidence that the trend has stopped."
    ),
    "libraries_argument": (
        "Libraries as Infrastructure\n\n"
        "We tend to describe public libraries as places that lend books, and "
        "then we are surprised when people ask whether we still need them. "
        "But lending was never the whole job. A library is one of the few "
        "indoor public spaces where nobody is expected to buy anything: a "
        "student can do homework there, a job seeker can print a résumé, and "
        "an older resident can ask for help with a form. Critics are right that "
        "fewer people borrow printed books than before. That is an argument for "
        "changing what libraries offer, not for closing them. A city does not "
        "close its bridges because fewer people walk across them."
    ),
    "octopus": (
        "Thinking with Arms\n\n"
        "An octopus has about five hundred million neurons, a number closer to "
        "that of a dog than to that of most invertebrates. What surprises "
        "researchers is where those neurons are: roughly two thirds of them sit "
        "in the arms rather than in the central brain. In experiments, an arm "
        "that has been separated from the body can still reach toward food and "
        "pull away from an unpleasant touch. The central brain appears to set "
        "general goals, while each arm works out many of the details on its "
        "own."
    ),
    "translator": (
        "Every translator keeps a private list of words that refuse to cross "
        "the border. Mine begins with a word from my grandmother's language for "
        "the particular silence of a house after guests have left: not "
        "emptiness, not peace, but something with the warmth of both. For years "
        "I tried to translate it with a phrase, then with a footnote, and each "
        "time the word arrived on the other side smaller than it had been. I no "
        "longer think of this as a failure. A word that resists translation is "
        "not a gap in the other language; it is a record of what one group of "
        "people decided was worth naming."
    ),
    # I-3 · Sprint 4 · textos académicos propios para la ampliación de lectura
    # del IELTS. Escritos para este repo; ninguno viene de un examen.
    "desalination": (
        "Turning Seawater into Drinking Water\n\n"
        "Removing salt from seawater, a process known as desalination, now "
        "supplies drinking water to millions of people in dry coastal regions. "
        "The most common method, reverse osmosis, pushes seawater through "
        "membranes that hold back the salt. It uses far less energy than the "
        "older approach of boiling water and collecting the steam, but it is "
        "still expensive, largely because pumping water at high pressure "
        "requires a great deal of electricity. The process also produces "
        "brine, a highly salty waste that can harm marine life if it is "
        "released carelessly. Engineers are testing ways to dilute the brine "
        "before it is discharged, and some plants now run partly on solar "
        "power to reduce their running costs."
    ),
    "urban_heat": (
        "Cooling the City\n\n"
        "Cities are often several degrees warmer than the countryside around "
        "them, a pattern known as the urban heat island effect. Dark surfaces "
        "such as asphalt and roofs absorb sunlight during the day and release "
        "the heat slowly at night, so the difference is usually greatest after "
        "sunset. Trees help in two ways: they shade streets and buildings, and "
        "they release water vapour that cools the air around them. Some cities "
        "have also begun painting roofs white, since light colours reflect "
        "more sunlight. These measures do not remove the effect entirely, but "
        "in neighbourhoods where they have been combined, summer night "
        "temperatures have fallen noticeably."
    ),
    "language_loss": (
        "When Languages Disappear\n\n"
        "Linguists estimate that around half of the world's roughly seven "
        "thousand languages may stop being spoken by the end of this century. "
        "A language rarely disappears suddenly. More often, parents decide "
        "that their children will have better opportunities if they speak a "
        "dominant language, and within two or three generations the original "
        "language survives only among the elderly. When that happens, more "
        "than words are lost: many languages contain detailed knowledge of "
        "local plants, weather patterns or navigation that has never been "
        "written down. Recording projects can preserve grammar and vocabulary, "
        "but most linguists agree that a language only stays alive if children "
        "continue to learn it at home."
    ),
    "four_day_week": (
        "The Four-Day Week\n\n"
        "Several companies have experimented with a four-day working week in "
        "which employees keep their full salary. In one trial involving around "
        "sixty firms, most chose to continue the arrangement after six months, "
        "reporting similar or higher productivity and fewer sick days. Critics "
        "point out that the companies volunteered for the trial, which "
        "suggests they already expected it to work, and that the results may "
        "not apply to sectors such as healthcare, where services must run "
        "every day. Supporters reply that the trial was never meant to prove "
        "that a shorter week suits every job, only that it can work in many "
        "of them."
    ),
    "microplastics": (
        "Microplastics\n\n"
        "Microplastics are pieces of plastic smaller than five millimetres. "
        "Some are made at this size, for example the tiny beads once added to "
        "cosmetics, but most come from larger objects that break down over "
        "time, such as bottles, fishing nets and synthetic clothing, which "
        "sheds fibres in the washing machine. They have been found in rivers, "
        "in Arctic ice and in the bodies of many animals. Scientists still know "
        "relatively little about how they affect human health, and several "
        "research teams are now studying this question. What is already clear "
        "is that once microplastics enter the ocean, removing them is almost "
        "impossible, so most experts argue that the priority should be to stop "
        "them from getting there in the first place."
    ),
}


# ---------------------------------------------------------------------------
# Constructor de ítems · valida en tiempo de import
#
# Un banco con la respuesta "correcta" fuera de las opciones, o con un ítem sin
# explicación, es exactamente el tipo de defecto que sólo se descubre cuando un
# estudiante ya lo vio. Aquí revienta al importar el módulo.
# ---------------------------------------------------------------------------

# Sprint 4 · I-5 · los textos y ejercicios de Saber 11 viven en su propio
# módulo (por tamaño). Sus textos entran aquí antes de validar los ejercicios.
from app.data.exam_prep_saber11 import TEXTOS as _TEXTOS_SABER11  # noqa: E402
from app.data.exam_prep_saber11 import construir as _construir_saber11  # noqa: E402

_TEXTOS.update(_TEXTOS_SABER11)


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
    # I-1b · Sprint 4 · ampliación del banco (de 9 a 25). Ver la nota en álgebra.
    _item(
        "sat-gram-10",
        habilidad="sat_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "Each of the players on the team ______ a new uniform for the season."
        ),
        options=["has", "have", "are", "were"],
        correct="has",
        explanation=(
            "El sujeto es “Each”, que siempre es singular: cada uno, de a uno. "
            "“of the players on the team” solo dice de qué grupo se habla. El "
            "oído pide “have” por “players”, que es la trampa. Tapa todo lo que "
            "va después de “of” y lee “Each has a new uniform”."
        ),
    ),
    _item(
        "sat-gram-11",
        habilidad="sat_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "The students left ______ backpacks in the hallway before the assembly."
        ),
        options=["their", "there", "they're", "its"],
        correct="their",
        explanation=(
            "Las mochilas son DE los estudiantes: posesivo plural, “their”. "
            "“There” es un lugar (“allí”) y “they're” es “they are”: lee la "
            "oración con “they are backpacks” y deja de tener sentido. “Its” es "
            "posesivo singular, y “students” es plural."
        ),
    ),
    _item(
        "sat-gram-12",
        habilidad="sat_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Which option joins the two ideas correctly?\n\n"
            "The rain finally stopped ______ went outside to play."
        ),
        options=[", so we", ", we", " we", " so, we"],
        correct=", so we",
        explanation=(
            "Son dos oraciones completas (“The rain stopped” y “we went "
            "outside”). Para unirlas con coma hace falta una conjunción: coma + "
            "“so”. Solo la coma (“, we”) es el error que en inglés se llama "
            "comma splice, y sin nada (“ we”) las dos oraciones quedan pegadas. "
            "La coma va ANTES de la conjunción, no después."
        ),
    ),
    _item(
        "sat-gram-13",
        habilidad="sat_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "Yesterday, the team ______ the final report to the director."
        ),
        options=["submitted", "submits", "will submit", "has submitted"],
        correct="submitted",
        explanation=(
            "“Yesterday” fija un momento terminado del pasado, y eso pide el "
            "pasado simple. “Has submitted” es la trampa: el present perfect no "
            "se usa con un tiempo pasado concreto (“yesterday”, “in 2020”, "
            "“last week”). Busca siempre la palabra que marca el tiempo."
        ),
    ),
    _item(
        "sat-gram-14",
        habilidad="sat_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "The two ______ cars were parked outside the house."
        ),
        options=["brothers'", "brother's", "brothers", "brothers's"],
        correct="brothers'",
        explanation=(
            "Son DOS hermanos y los carros son de ellos: plural posesivo. Para "
            "un plural terminado en s, el apóstrofo va después de la s: "
            "“brothers'”. “Brother's” sería de un solo hermano, y “brothers” sin "
            "apóstrofo no indica posesión. “Brothers's” no existe."
        ),
    ),
    _item(
        "sat-gram-15",
        habilidad="sat_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "There were ______ people at the concert this year than last year."
        ),
        options=["fewer", "less", "lesser", "few"],
        correct="fewer",
        explanation=(
            "“People” se puede contar (una persona, dos personas), y con lo "
            "contable se usa “fewer”. “Less” es para lo que no se cuenta "
            "(“less water”, “less time”). “Few” no sirve con “than”: la "
            "comparación pide la forma comparativa."
        ),
    ),
    _item(
        "sat-gram-16",
        habilidad="sat_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Which option joins the two ideas correctly?\n\n"
            "The main road was closed for repairs ______ we took a longer route."
        ),
        options=["; therefore,", ", therefore", " therefore", ", therefore;"],
        correct="; therefore,",
        explanation=(
            "“Therefore” NO es una conjunción como “so” o “and”: es un adverbio, "
            "y no puede unir dos oraciones con una coma. Lo correcto es punto y "
            "coma antes y coma después. “, therefore” es el error más frecuente "
            "del examen, justamente porque suena bien al leerlo en voz alta."
        ),
    ),
    _item(
        "sat-gram-17",
        habilidad="sat_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "Neither the teacher nor the students ______ ready for the surprise "
            "fire drill."
        ),
        options=["were", "was", "is", "has been"],
        correct="were",
        explanation=(
            "Con “neither… nor” (y con “either… or”) el verbo concuerda con el "
            "sustantivo MÁS CERCANO: “the students”, plural, pide “were”. “Was” "
            "concuerda con “the teacher”, que está más lejos. Si la oración "
            "fuera “neither the students nor the teacher”, sería “was”."
        ),
    ),
    _item(
        "sat-gram-18",
        habilidad="sat_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "The coach gave the trophy to Lucía and ______."
        ),
        options=["her", "she", "herself", "hers"],
        correct="her",
        explanation=(
            "Después de “to” va pronombre objeto: “her”. El mismo truco de "
            "siempre: quita “Lucía and” y lee “gave the trophy to she”, que "
            "suena mal de inmediato. “Herself” solo va cuando sujeto y objeto son "
            "la misma persona, y “hers” es posesivo (“the trophy is hers”)."
        ),
    ),
    _item(
        "sat-gram-19",
        habilidad="sat_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "She packed only three things for the trip______ a camera, a map, "
            "and a notebook."
        ),
        options=[":", ";", ", which", " and"],
        correct=":",
        explanation=(
            "Los dos puntos presentan una lista o una explicación DESPUÉS de una "
            "oración completa: “She packed only three things” ya está completa, y "
            "lo que sigue dice cuáles. El punto y coma pide una oración completa "
            "a cada lado, y “a camera, a map…” no lo es. Truco: si puedes poner "
            "“namely” en el lugar, van dos puntos."
        ),
    ),
    _item(
        "sat-gram-20",
        habilidad="sat_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "The new policy aims to reduce costs, improve customer service, and "
            "______."
        ),
        options=[
            "increase sales",
            "increasing sales",
            "the increase of sales",
            "sales will increase",
        ],
        correct="increase sales",
        explanation=(
            "En una lista, todos los elementos tienen que tener la misma forma "
            "(paralelismo). Los dos primeros son verbos en base: “reduce”, "
            "“improve”; el tercero también: “increase”. “Increasing” cambia la "
            "forma, y las otras dos opciones meten un sustantivo o una oración "
            "entera donde iba un verbo."
        ),
    ),
    _item(
        "sat-gram-21",
        habilidad="sat_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "Having finished the exam early, ______"
        ),
        options=[
            "Tomás quietly left the room.",
            "the room was left quietly by Tomás.",
            "the exam was handed in by Tomás.",
            "it was time for Tomás to leave.",
        ],
        correct="Tomás quietly left the room.",
        explanation=(
            "La frase inicial (“Having finished the exam early”) describe a "
            "alguien, y en inglés ese alguien tiene que ser lo primero después "
            "de la coma. ¿Quién terminó el examen? Tomás. En las otras opciones "
            "lo primero es “the room”, “the exam” o “it”, y la oración termina "
            "diciendo que el salón o el examen terminaron el examen."
        ),
    ),
    _item(
        "sat-gram-22",
        habilidad="sat_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "The scientist ______ the committee selected will present her "
            "findings first."
        ),
        options=["whom", "who", "whose", "which"],
        correct="whom",
        explanation=(
            "El comité seleccionó A la científica: es objeto del verbo "
            "“selected”, y el pronombre objeto es “whom”. Prueba: reescribe la "
            "parte con “he/him”: “the committee selected HIM”, no “HE”; si va "
            "“him”, va “whom”. “Which” es para cosas, y “whose” indica posesión."
        ),
    ),
    _item(
        "sat-gram-23",
        habilidad="sat_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "If she ______ the earlier bus, she would have arrived on time."
        ),
        options=["had caught", "caught", "would catch", "has caught"],
        correct="had caught",
        explanation=(
            "La segunda parte (“would have arrived”) habla de algo que NO pasó "
            "en el pasado. Esa condición imposible pide past perfect en el “if”: "
            "“had caught”. “Caught” sirve para una situación hipotética del "
            "presente (“If she caught…, she would arrive”). “Would” nunca va "
            "dentro del “if”."
        ),
    ),
    _item(
        "sat-gram-24",
        habilidad="sat_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "On the top shelf of the library ______ several old dictionaries."
        ),
        options=["are", "is", "was", "has been"],
        correct="are",
        explanation=(
            "La oración está invertida: el sujeto va DESPUÉS del verbo. "
            "Reordénala: “Several old dictionaries are on the top shelf”. El "
            "sujeto es plural. La trampa es que justo antes del espacio hay dos "
            "sustantivos singulares (“shelf”, “library”) que empujan hacia "
            "“is”."
        ),
    ),
    _item(
        "sat-gram-25",
        habilidad="sat_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the option that completes the sentence correctly.\n\n"
            "The population of Bogotá is much larger than ______."
        ),
        options=[
            "that of Medellín",
            "Medellín",
            "those of Medellín",
            "Medellín's population's",
        ],
        correct="that of Medellín",
        explanation=(
            "La comparación tiene que ser entre cosas del mismo tipo: población "
            "con población, no población con ciudad. “That of Medellín” "
            "significa “the population of Medellín”. “Medellín” solo compara una "
            "población con una ciudad, que es justo lo que el examen castiga. "
            "“Those” es plural, y “population” es singular."
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
    # I-1b · Sprint 4 · ampliación del banco (de 6 a 25). Ver la nota en álgebra.
    _item(
        "sat-exp-7",
        habilidad="sat_expresion",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best transition.\n\n"
            "Many desert animals avoid the heat of the day. ______, the fennec fox "
            "hunts at night and rests in a cool burrow while the sun is up."
        ),
        options=["For example", "However", "In contrast", "Finally"],
        correct="For example",
        explanation=(
            "La segunda oración es un caso concreto de la primera: el zorro "
            "fennec es UN animal del desierto que evita el calor. Eso pide una "
            "transición de ejemplo. \"However\" e \"In contrast\" anuncian lo "
            "contrario, y \"Finally\" cierra una lista que no existe. Pregúntate "
            "qué relación hay entre las dos ideas antes de mirar las opciones."
        ),
    ),
    _item(
        "sat-exp-8",
        habilidad="sat_expresion",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best transition.\n\n"
            "The new park gives children a safe place to play. ______, it gives "
            "older residents a shaded place to meet in the afternoons."
        ),
        options=["In addition", "Instead", "Nevertheless", "For instance"],
        correct="In addition",
        explanation=(
            "Las dos oraciones nombran beneficios del parque, uno después del "
            "otro: la segunda SUMA. \"Instead\" diría que el segundo reemplaza al "
            "primero, y \"Nevertheless\" que hay un contraste. \"For instance\" "
            "presentaría un ejemplo de lo primero, y los mayores no son un "
            "ejemplo de los niños."
        ),
    ),
    _item(
        "sat-exp-9",
        habilidad="sat_expresion",
        nivel=NIVEL_FUNDAMENTOS,
        question="Which choice states the idea most concisely?",
        options=[
            "The meeting was postponed until Friday.",
            "The meeting was postponed and moved to a later date, which was Friday.",
            "The meeting, which had been planned, was postponed until a later day, Friday.",
            "The meeting was postponed until Friday, a day that was later.",
        ],
        correct="The meeting was postponed until Friday.",
        explanation=(
            "\"Postponed\" ya significa \"movido a una fecha posterior\": decirlo "
            "otra vez es redundante. Lo mismo \"which had been planned\" (toda "
            "reunión aplazada estaba planeada). En estas preguntas gana la opción "
            "más corta que conserva TODA la información, y aquí la información es "
            "solo \"se aplazó\" y \"hasta el viernes\"."
        ),
    ),
    _item(
        "sat-exp-10",
        habilidad="sat_expresion",
        nivel=NIVEL_FUNDAMENTOS,
        question="Which choice states the idea most concisely?",
        options=[
            "She repeated the instructions.",
            "She repeated the instructions again.",
            "She repeated the instructions again a second time.",
            "She said the instructions again, repeating them.",
        ],
        correct="She repeated the instructions.",
        explanation=(
            "\"Repeat\" ya incluye la idea de \"otra vez\", así que \"again\" sobra, "
            "y \"a second time\" sobra todavía más. La última opción dice lo mismo "
            "dos veces con verbos distintos. La redundancia suena natural al "
            "hablar, y por eso el examen la usa como trampa."
        ),
    ),
    _item(
        "sat-exp-11",
        habilidad="sat_expresion",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best transition.\n\n"
            "The bridge was closed for three months of repairs. ______, many "
            "drivers had to take a route that added twenty minutes to their trip."
        ),
        options=["As a result", "For example", "Similarly", "On the other hand"],
        correct="As a result",
        explanation=(
            "El desvío de veinte minutos es CONSECUENCIA del cierre del puente: "
            "causa y efecto. \"Similarly\" compararía dos cosas parecidas y \"On "
            "the other hand\" presentaría un contraste. Truco: si puedes unir las "
            "dos oraciones con \"so\", la transición es de consecuencia."
        ),
    ),
    _item(
        "sat-exp-12",
        habilidad="sat_expresion",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the most precise word.\n\n"
            "The recipe calls for a ______ amount of salt: just a pinch, so that "
            "the flavour of the fish is not covered."
        ),
        options=["small", "big", "strange", "normal"],
        correct="small",
        explanation=(
            "La misma oración da la pista: \"just a pinch\" (apenas una pizca). "
            "La palabra tiene que coincidir con esa idea. \"Normal\" no dice nada "
            "sobre la cantidad, y \"strange\" no tiene relación con el contexto. "
            "En estas preguntas casi siempre hay una pista escrita después de la "
            "coma o de los dos puntos."
        ),
    ),
    _item(
        "sat-exp-13",
        habilidad="sat_expresion",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best transition.\n\n"
            "Cats spend a large part of the day sleeping to save energy for "
            "hunting. ______, lions rest for up to twenty hours a day between hunts."
        ),
        options=["Similarly", "However", "Instead", "Therefore"],
        correct="Similarly",
        explanation=(
            "Los leones hacen LO MISMO que los gatos (descansar mucho entre "
            "cacerías), así que la transición es de semejanza. \"However\" "
            "anunciaría que hacen algo distinto. \"Therefore\" diría que los leones "
            "descansan PORQUE los gatos duermen, y una cosa no causa la otra."
        ),
    ),
    _item(
        "sat-exp-14",
        habilidad="sat_expresion",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A student has taken these notes:\n"
            "• Venus and Earth are almost the same size.\n"
            "• The surface of Venus is about 460 °C.\n"
            "• The average surface temperature of Earth is about 15 °C.\n\n"
            "The student wants to emphasise A DIFFERENCE between the two planets. "
            "Which choice best accomplishes that goal?"
        ),
        options=[
            "Although Venus and Earth are almost the same size, the surface of Venus is about 460 °C, while Earth's averages about 15 °C.",
            "Venus and Earth are almost the same size.",
            "Venus and Earth are both planets that are almost the same size.",
            "Venus, which is almost the same size as Earth, is a planet.",
        ],
        correct="Although Venus and Earth are almost the same size, the surface of Venus is about 460 °C, while Earth's averages about 15 °C.",
        explanation=(
            "El objetivo es una DIFERENCIA, y la única diferencia en las notas es "
            "la temperatura. Las otras tres opciones solo dicen lo que tienen en "
            "común: el tamaño. \"Although\" además prepara el contraste. Busca qué "
            "nota responde al objetivo y descarta las opciones que no la usan."
        ),
    ),
    _item(
        "sat-exp-15",
        habilidad="sat_expresion",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A student has taken these notes:\n"
            "• Gabriel García Márquez was a Colombian writer.\n"
            "• He won the Nobel Prize in Literature in 1982.\n"
            "• His best-known novel is One Hundred Years of Solitude.\n\n"
            "The student wants to introduce García Márquez to an audience that "
            "has never heard of him. Which choice best accomplishes that goal?"
        ),
        options=[
            "Gabriel García Márquez, a Colombian writer best known for the novel One Hundred Years of Solitude, won the Nobel Prize in Literature in 1982.",
            "One Hundred Years of Solitude is García Márquez's best-known novel.",
            "In 1982, the Nobel Prize in Literature went to García Márquez.",
            "García Márquez won the prize in 1982 for his writing.",
        ],
        correct="Gabriel García Márquez, a Colombian writer best known for the novel One Hundred Years of Solitude, won the Nobel Prize in Literature in 1982.",
        explanation=(
            "Para un público que no lo conoce hace falta decir QUIÉN es: el "
            "nombre completo y que era un escritor colombiano. Solo la primera "
            "opción lo dice. Las otras asumen que el lector ya sabe quién es "
            "(\"García Márquez\" a secas), y la última ni siquiera dice qué premio "
            "ganó."
        ),
    ),
    _item(
        "sat-exp-16",
        habilidad="sat_expresion",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the best transition.\n\n"
            "Most smartphones are replaced after about three years. ______, a "
            "well-maintained bicycle can be used for decades."
        ),
        options=["In contrast", "For example", "As a result", "In addition"],
        correct="In contrast",
        explanation=(
            "Tres años frente a décadas: las dos oraciones se oponen en cuánto "
            "duran las cosas. Eso pide contraste. \"As a result\" diría que la "
            "bicicleta dura PORQUE los celulares se cambian, y \"In addition\" "
            "sumaría una idea del mismo sentido. Cuando las dos oraciones tienen "
            "datos que chocan, busca el contraste."
        ),
    ),
    _item(
        "sat-exp-17",
        habilidad="sat_expresion",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Where should the following sentence be added?\n\n"
            "\"These early devices were expensive and could store only a few "
            "songs.\"\n\n"
            "(1) Portable music players first became popular in the late 1990s. "
            "(2) Within a few years, however, prices dropped and storage grew "
            "enormously. "
            "(3) Today, most people listen to music on their phones instead. "
            "(4) Dedicated music players are now sold mainly to runners."
        ),
        options=[
            "After sentence 1",
            "After sentence 2",
            "After sentence 3",
            "After sentence 4",
        ],
        correct="After sentence 1",
        explanation=(
            "\"These early devices\" necesita que los aparatos se acaben de "
            "nombrar: eso pasa en la frase 1. Además la frase 2 empieza con "
            "\"however, prices dropped\", y ese contraste solo tiene sentido si "
            "antes se dijo que eran caros. El pronombre al comienzo de la oración "
            "nueva y el conector de la siguiente deciden la posición."
        ),
    ),
    _item(
        "sat-exp-18",
        habilidad="sat_expresion",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the most precise word.\n\n"
            "The two witnesses gave ______ accounts of the accident: one said the "
            "car was red, and the other said it was blue."
        ),
        options=["conflicting", "detailed", "emotional", "brief"],
        correct="conflicting",
        explanation=(
            "La parte después de los dos puntos es la definición de la palabra "
            "que falta: un testigo dijo rojo y el otro azul, así que sus versiones "
            "se contradicen. \"Detailed\" podría ser cierto, pero no es lo que el "
            "ejemplo muestra. La palabra correcta es la que el resto de la "
            "oración demuestra, no una que simplemente podría ser verdad."
        ),
    ),
    _item(
        "sat-exp-19",
        habilidad="sat_expresion",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A writer is explaining how honeybees tell each other where to find "
            "food. Which sentence is LEAST relevant to that explanation and "
            "should be removed?\n\n"
            "(1) A bee that finds flowers returns to the hive and performs a "
            "movement called the waggle dance. "
            "(2) The angle of the dance shows the direction of the food. "
            "(3) Honey has been used as a medicine for thousands of years. "
            "(4) The length of the dance tells the other bees how far away the "
            "food is."
        ),
        options=["Sentence 3", "Sentence 1", "Sentence 2", "Sentence 4"],
        correct="Sentence 3",
        explanation=(
            "El párrafo explica CÓMO se comunican las abejas, y las frases 1, 2 "
            "y 4 forman esa explicación (la danza, su dirección, su distancia). "
            "El uso medicinal de la miel es un dato verdadero e interesante, pero "
            "de otro tema. Lo que hay que preguntarse no es si es cierto, sino si "
            "sirve al propósito declarado."
        ),
    ),
    _item(
        "sat-exp-20",
        habilidad="sat_expresion",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the best transition.\n\n"
            "The team expected the new fertiliser to increase the harvest. ______, "
            "the plots that received it produced slightly less than the others."
        ),
        options=["Instead", "Similarly", "For example", "Therefore"],
        correct="Instead",
        explanation=(
            "Se esperaba un aumento y ocurrió lo contrario: \"Instead\" marca que "
            "pasó algo distinto de lo previsto. \"Therefore\" diría que la caída "
            "fue CONSECUENCIA de la expectativa, que no tiene sentido. "
            "\"Similarly\" y \"For example\" no contrastan nada."
        ),
    ),
    _item(
        "sat-exp-21",
        habilidad="sat_expresion",
        nivel=NIVEL_AVANZADO,
        question=(
            "A student has taken these notes:\n"
            "• Researchers studied 300 high-school students for one year.\n"
            "• Half of them took a 20-minute walk before class.\n"
            "• The students who walked scored higher on attention tests.\n"
            "• The researchers say more studies are needed.\n\n"
            "The student wants to PRESENT THE STUDY'S FINDING while "
            "acknowledging its limits. Which choice best accomplishes that goal?"
        ),
        options=[
            "In a one-year study of 300 high-school students, those who walked for 20 minutes before class scored higher on attention tests, though the researchers say more studies are needed.",
            "Walking for 20 minutes before class improves the attention of every high-school student.",
            "Researchers studied 300 high-school students for one year, and half of them walked before class.",
            "More studies are needed on high-school students and attention.",
        ],
        correct="In a one-year study of 300 high-school students, those who walked for 20 minutes before class scored higher on attention tests, though the researchers say more studies are needed.",
        explanation=(
            "El objetivo tiene dos partes: el hallazgo Y sus límites. La segunda "
            "opción da el hallazgo pero lo convierte en una verdad para \"every "
            "student\", lo contrario de reconocer límites. La tercera describe el "
            "estudio sin decir qué encontró, y la cuarta solo da el límite. "
            "Revisa que la opción cumpla TODAS las partes del objetivo."
        ),
    ),
    _item(
        "sat-exp-22",
        habilidad="sat_expresion",
        nivel=NIVEL_AVANZADO,
        question=(
            "Where should the following sentence be added?\n\n"
            "\"Her answer surprised everyone: the city should plant trees "
            "instead.\"\n\n"
            "(1) In 2015, the city asked an engineer how to reduce flooding in "
            "the downtown streets. "
            "(2) Most officials expected her to recommend larger drainage pipes. "
            "(3) Tree roots, she explained, help the soil absorb rainwater before "
            "it reaches the streets. "
            "(4) Ten years later, flooding downtown has dropped by half."
        ),
        options=[
            "After sentence 2",
            "After sentence 1",
            "After sentence 3",
            "After sentence 4",
        ],
        correct="After sentence 2",
        explanation=(
            "\"Surprised everyone\" necesita que antes se diga qué esperaban (la "
            "frase 2: tuberías más grandes), e \"instead\" contrasta con eso "
            "mismo. Y la frase 3 (\"Tree roots, she explained…\") explica una "
            "propuesta de árboles que ya tiene que haber aparecido. Los dos "
            "lados de la oración nueva encajan solo entre la 2 y la 3."
        ),
    ),
    _item(
        "sat-exp-23",
        habilidad="sat_expresion",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the most precise word.\n\n"
            "The historian was careful not to overstate her case; she described "
            "the letters as ______ evidence that the two writers had met, not as "
            "proof."
        ),
        options=["suggestive", "conclusive", "irrelevant", "fabricated"],
        correct="suggestive",
        explanation=(
            "La oración da los dos límites: no exagerar y \"not as proof\". La "
            "palabra tiene que estar entre \"nada\" y \"prueba\": evidencia que "
            "apunta a algo sin demostrarlo, \"suggestive\". \"Conclusive\" es "
            "justamente lo que se niega. \"Irrelevant\" y \"fabricated\" van "
            "demasiado lejos hacia el otro lado: ella sí la considera evidencia."
        ),
    ),
    _item(
        "sat-exp-24",
        habilidad="sat_expresion",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the best transition.\n\n"
            "Electric buses are more expensive to buy than diesel ones. ______, "
            "they cost far less to run, and many cities recover the difference "
            "within a few years."
        ),
        options=["Even so", "For instance", "As a result", "Likewise"],
        correct="Even so",
        explanation=(
            "La primera oración da una desventaja y la segunda un argumento que "
            "la compensa: \"Even so\" (aun así) reconoce la desventaja y sigue "
            "adelante. \"As a result\" diría que cuestan menos de operar PORQUE "
            "son caros de comprar. \"Likewise\" sumaría otra desventaja. Las "
            "transiciones de concesión son las más difíciles del examen."
        ),
    ),
    _item(
        "sat-exp-25",
        habilidad="sat_expresion",
        nivel=NIVEL_AVANZADO,
        question=(
            "A writer claims that reading on paper helps people remember more "
            "than reading on a screen. Which sentence, if added, would best "
            "SUPPORT that claim?"
        ),
        options=[
            "In one experiment, students who read a story on paper recalled the order of events better than students who read the same story on a tablet.",
            "Many people say they prefer the smell of printed books.",
            "Tablets can store thousands of books in a single device.",
            "Paper has been used for writing for about two thousand years.",
        ],
        correct="In one experiment, students who read a story on paper recalled the order of events better than students who read the same story on a tablet.",
        explanation=(
            "La afirmación es sobre RECORDAR, y solo la primera opción da "
            "evidencia sobre memoria, comparando papel y pantalla con el mismo "
            "texto. Que a la gente le guste el olor del papel es una preferencia, "
            "no un efecto en la memoria. Las otras dos son datos ciertos que no "
            "tocan la afirmación."
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
    # I-1b · Sprint 4 · ampliación del banco (de 6 a 25), sobre 7 textos propios
    # nuevos. Ver la nota en álgebra.
    _item(
        "sat-read-7",
        habilidad="sat_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="sleep_memory",
        question="Which choice best states the main idea of the text?",
        options=[
            "A small study suggests that sleep helps strengthen memories, though the authors treat the result with caution.",
            "University students remember word pairs better in the afternoon than in the evening.",
            "Staying awake in a laboratory damages the memory of young people.",
            "Sleep has been proven to improve memory in people of all ages.",
        ],
        correct="A small study suggests that sleep helps strengthen memories, though the authors treat the result with caution.",
        explanation=(
            "La idea principal tiene que cubrir el texto entero: el hallazgo "
            "(dormir ayudó a recordar) Y la cautela del final. La última opción "
            "dice \"proven\" y \"all ages\", justo lo que los autores se cuidan de "
            "no decir. La segunda se queda con un detalle de la hora. Desconfía "
            "de las opciones más absolutas que el texto."
        ),
    ),
    _item(
        "sat-read-8",
        habilidad="sat_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="sleep_memory",
        question=(
            "According to the text, how did the two groups of students differ "
            "the next afternoon?"
        ),
        options=[
            "The students who had slept recalled more word pairs.",
            "The students who had stayed awake recalled more word pairs.",
            "Both groups recalled the same number of word pairs.",
            "Only the students who had slept were tested.",
        ],
        correct="The students who had slept recalled more word pairs.",
        explanation=(
            "El texto lo dice de forma literal: \"the students who had slept "
            "recalled about a third more pairs\". En las preguntas de detalle "
            "(\"According to the text\") la respuesta está escrita; no hay que "
            "deducir nada. Vuelve a la frase exacta antes de marcar."
        ),
    ),
    _item(
        "sat-read-9",
        habilidad="sat_lectura",
        nivel=NIVEL_AVANZADO,
        passage="sleep_memory",
        question=(
            "Which finding, if true, would most directly address the limitation "
            "the researchers mention?"
        ),
        options=[
            "A larger study including people of many ages finds a similar effect of sleep on memory.",
            "A second group of twenty-four students shows the same result.",
            "Students who memorised the list in the morning recalled fewer pairs.",
            "Students say they feel more rested after a full night of sleep.",
        ],
        correct="A larger study including people of many ages finds a similar effect of sleep on memory.",
        explanation=(
            "Los autores nombran DOS límites: el grupo era pequeño y todos eran "
            "estudiantes de 18 a 22 años. Solo la primera opción responde a los "
            "dos. Repetirlo con otros veinticuatro estudiantes sigue siendo un "
            "grupo pequeño y de la misma edad. Que se sientan descansados no dice "
            "nada sobre la memoria."
        ),
    ),
    _item(
        "sat-read-10",
        habilidad="sat_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="market_morning",
        question=(
            "The detail that the grandfather had \"already decided to buy\" the "
            "tomatoes mainly serves to"
        ),
        options=[
            "show that the bargaining was not really about the price.",
            "suggest that the grandfather could not afford the tomatoes.",
            "explain why the seller laughed at the grandfather.",
            "indicate that the tomatoes were of poor quality.",
        ],
        correct="show that the bargaining was not really about the price.",
        explanation=(
            "Si ya había decidido comprarlos, regatear no tenía un fin práctico. "
            "El resto del texto lo confirma: \"the price had stopped mattering\". "
            "El ceño fruncido ante el tomate es teatro, no una queja real por la "
            "calidad. Pregúntate qué cambiaría si se borrara el detalle."
        ),
    ),
    _item(
        "sat-read-11",
        habilidad="sat_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="market_morning",
        question=(
            "Which choice best describes what the narrator realises in the last "
            "sentence?"
        ),
        options=[
            "The weekly trip to the market was mainly a social ritual for the grandfather.",
            "The grandfather had been paying too much for tomatoes for years.",
            "The seller had always known that the grandfather would not pay.",
            "The narrator should have gone shopping with the grandfather more often.",
        ],
        correct="The weekly trip to the market was mainly a social ritual for the grandfather.",
        explanation=(
            "\"He had never once been shopping\" no es literal: sí compraba los "
            "tomates. Lo que el narrador entiende es que el propósito real era la "
            "conversación (la lluvia, la hija del vendedor, la ruta de bus). "
            "Las otras opciones leen la frase al pie de la letra o inventan algo "
            "que el texto no dice."
        ),
    ),
    _item(
        "sat-read-12",
        habilidad="sat_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="market_morning",
        question=(
            "As used in the text, the phrase \"the real conversation\" suggests "
            "that the bargaining was"
        ),
        options=[
            "an opening rather than the main purpose of the visit.",
            "a dishonest attempt to cheat the seller.",
            "the most important part of the grandfather's week.",
            "a skill the grandfather was trying to teach the narrator.",
        ],
        correct="an opening rather than the main purpose of the visit.",
        explanation=(
            "\"Real\" contrapone lo que viene después con lo que vino antes: si la "
            "conversación sobre la lluvia es la \"real\", el regateo era la "
            "entrada, la excusa. Nada sugiere engaño (el vendedor se ríe, le "
            "sigue el juego) ni que quisiera enseñarle algo al nieto."
        ),
    ),
    _item(
        "sat-read-13",
        habilidad="sat_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="postal_codes",
        question="According to the text, who usually paid the postage on a letter?",
        options=[
            "The person who received the letter",
            "The person who sent the letter",
            "The postal service",
            "The sender and the receiver equally",
        ],
        correct="The person who received the letter",
        explanation=(
            "Está en la primera frase: \"the person who received a letter, not the "
            "person who sent it, paid the postage\". La segunda opción es justo lo "
            "que cambió DESPUÉS, con la reforma del final, y por eso confunde: "
            "fíjate a qué época se refiere cada parte del texto."
        ),
    ),
    _item(
        "sat-read-14",
        habilidad="sat_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="postal_codes",
        question=(
            "Based on the text, why would a receiver \"politely refuse to pay\" "
            "for a letter?"
        ),
        options=[
            "The marks on the outside had already given the receiver the message.",
            "The letter had been sent to the wrong address.",
            "The postage was higher than the receiver had expected.",
            "The receiver did not know the person who sent it.",
        ],
        correct="The marks on the outside had already given the receiver the message.",
        explanation=(
            "El texto explica el truco justo antes: las marcas acordadas "
            "\"carried a short message by themselves\", así que con leer el sobre "
            "ya bastaba para saber que todo estaba bien. El costo alto es la "
            "razón general del problema, no la de esta negativa en particular."
        ),
    ),
    _item(
        "sat-read-15",
        habilidad="sat_lectura",
        nivel=NIVEL_AVANZADO,
        passage="postal_codes",
        question="The final sentence mainly serves to",
        options=[
            "connect the practice described in the text to a later change in the postal system.",
            "suggest that the marks on envelopes were illegal.",
            "explain how reformers discovered the secret marks.",
            "argue that receivers should still pay for their letters.",
        ],
        correct="connect the practice described in the text to a later change in the postal system.",
        explanation=(
            "La última frase sale del truco y mira hacia adelante: fue \"one of "
            "the reasons\" para que luego pagara el remitente. Esa es su función: "
            "conectar. No dice que fuera ilegal ni cómo lo descubrieron, y la "
            "cuarta opción defiende lo contrario de lo que pedían los reformadores."
        ),
    ),
    _item(
        "sat-read-16",
        habilidad="sat_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="glaciers",
        question=(
            "Which choice best describes why three of the four glaciers did not "
            "retreat?"
        ),
        options=[
            "They were in a valley that received unusually heavy snowfall.",
            "A landslide covered their front edges.",
            "They were too small to be measured.",
            "They were located at a higher altitude than the others.",
        ],
        correct="They were in a valley that received unusually heavy snowfall.",
        explanation=(
            "El texto separa los cuatro casos: tres por la nevada en un mismo "
            "valle, y UNO que no se pudo medir por un deslizamiento. La segunda "
            "opción aplica a los tres la razón del cuarto, y por eso es la "
            "trampa. La altitud no aparece en ninguna parte."
        ),
    ),
    _item(
        "sat-read-17",
        habilidad="sat_lectura",
        nivel=NIVEL_AVANZADO,
        passage="glaciers",
        question=(
            "A reader claims that the study shows glacier retreat has stopped in "
            "some regions. Based on the text, how would the authors most likely "
            "respond?"
        ),
        options=[
            "The few glaciers that did not retreat can be explained by local conditions and do not show that the trend has stopped.",
            "The reader is correct, because four of the thirty glaciers did not retreat.",
            "The study cannot say anything about retreat, because one glacier could not be measured.",
            "Glacier retreat has stopped only in the valley with heavy snowfall.",
        ],
        correct="The few glaciers that did not retreat can be explained by local conditions and do not show that the trend has stopped.",
        explanation=(
            "Los autores lo anticipan: advierten contra usar los glaciares "
            "estables \"as evidence that the trend has stopped\", y el texto da "
            "una explicación local para cada uno. La tercera opción exagera: un "
            "glaciar sin medir no anula los otros veintinueve. La cuarta convierte "
            "un período de nevadas en un cambio de tendencia."
        ),
    ),
    _item(
        "sat-read-18",
        habilidad="sat_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="libraries_argument",
        question="Which choice best states the author's main claim?",
        options=[
            "Public libraries serve purposes beyond lending books and should be adapted rather than closed.",
            "Public libraries should stop lending printed books.",
            "Fewer people visit public libraries than in the past.",
            "Cities should spend more money on bridges than on libraries.",
        ],
        correct="Public libraries serve purposes beyond lending books and should be adapted rather than closed.",
        explanation=(
            "El texto entero sostiene dos cosas: el préstamo \"was never the "
            "whole job\" y la caída del préstamo es razón para \"changing what "
            "libraries offer, not for closing them\". La tercera opción es lo que "
            "dicen los críticos, no el autor (y además habla de visitas, no de "
            "préstamos). Los puentes son una comparación, no el tema."
        ),
    ),
    _item(
        "sat-read-19",
        habilidad="sat_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="libraries_argument",
        question=(
            "The examples of the student, the job seeker and the older resident "
            "mainly serve to"
        ),
        options=[
            "illustrate uses of a library that do not involve borrowing books.",
            "show that libraries are used mostly by young people.",
            "prove that libraries lend more books than critics believe.",
            "describe the people who have stopped using libraries.",
        ],
        correct="illustrate uses of a library that do not involve borrowing books.",
        explanation=(
            "Los tres ejemplos aparecen justo después de \"lending was never the "
            "whole job\": hacer tareas, imprimir una hoja de vida y pedir ayuda "
            "con un formulario. Ninguno es pedir un libro, y ese es el punto. "
            "Uno de los tres es una persona mayor, así que la segunda opción "
            "contradice el texto."
        ),
    ),
    _item(
        "sat-read-20",
        habilidad="sat_lectura",
        nivel=NIVEL_AVANZADO,
        passage="libraries_argument",
        question="How does the author respond to the critics mentioned in the text?",
        options=[
            "By accepting their evidence but drawing a different conclusion from it",
            "By showing that their evidence is false",
            "By agreeing that libraries should be closed",
            "By ignoring their argument entirely",
        ],
        correct="By accepting their evidence but drawing a different conclusion from it",
        explanation=(
            "\"Critics are right that fewer people borrow printed books\": el "
            "autor acepta el dato. Lo que discute es la conclusión: \"That is an "
            "argument for changing… not for closing\". Esta estrategia (conceder "
            "el hecho y discutir la interpretación) es muy frecuente en los "
            "textos argumentativos del examen, y la segunda opción es su trampa "
            "simétrica."
        ),
    ),
    _item(
        "sat-read-21",
        habilidad="sat_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="octopus",
        question=(
            "According to the text, where are most of an octopus's neurons "
            "located?"
        ),
        options=[
            "In its arms",
            "In its central brain",
            "Evenly divided between its brain and its arms",
            "In its eyes",
        ],
        correct="In its arms",
        explanation=(
            "\"Roughly two thirds of them sit in the arms rather than in the "
            "central brain\": dos tercios es la mayoría. La segunda opción es lo "
            "que uno esperaría sin leer, y por eso está. La tercera exagera hacia "
            "el otro lado: dos tercios no es mitad y mitad."
        ),
    ),
    _item(
        "sat-read-22",
        habilidad="sat_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="octopus",
        question=(
            "The experiment with the separated arm is presented mainly as "
            "evidence that"
        ),
        options=[
            "an octopus's arms can control some of their own movements.",
            "an octopus can survive after losing an arm.",
            "octopuses are more intelligent than dogs.",
            "the central brain of an octopus has no role in movement.",
        ],
        correct="an octopus's arms can control some of their own movements.",
        explanation=(
            "Un brazo separado del cuerpo que todavía busca comida solo puede "
            "estar controlado por sus propias neuronas: eso respalda que los "
            "brazos \"work out many of the details on their own\". La cuarta "
            "opción va demasiado lejos: el texto dice que el cerebro central "
            "\"set[s] general goals\". La comparación con el perro es sobre el "
            "número de neuronas, no sobre inteligencia."
        ),
    ),
    _item(
        "sat-read-23",
        habilidad="sat_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="translator",
        question=(
            "In the text, the word from the grandmother's language refers to"
        ),
        options=[
            "the silence of a house after guests have left.",
            "the sadness of saying goodbye to guests.",
            "a phrase the narrator invented.",
            "a house where nobody lives.",
        ],
        correct="the silence of a house after guests have left.",
        explanation=(
            "Está definido en el texto: \"the particular silence of a house after "
            "guests have left\". La segunda opción le pone una emoción que el "
            "texto descarta (\"not emptiness\"; tiene \"the warmth\" de la paz). "
            "La casa no está deshabitada: los invitados se acaban de ir."
        ),
    ),
    _item(
        "sat-read-24",
        habilidad="sat_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="translator",
        question=(
            "As used in the text, the phrase \"arrived on the other side smaller\" "
            "most nearly means that the translation"
        ),
        options=[
            "lost part of the word's meaning.",
            "used fewer letters than the original word.",
            "was printed in a smaller font.",
            "was easier to pronounce.",
        ],
        correct="lost part of the word's meaning.",
        explanation=(
            "\"Cruzar al otro lado\" es la metáfora de la traducción que el texto "
            "usa desde el principio (\"refuse to cross the border\"). Llegar \"más "
            "pequeña\" es llegar con menos significado del que tenía. Las otras "
            "opciones leen \"smaller\" de forma literal: tamaño de letra o número "
            "de letras."
        ),
    ),
    _item(
        "sat-read-25",
        habilidad="sat_lectura",
        nivel=NIVEL_AVANZADO,
        passage="translator",
        question="Which choice best describes the overall structure of the text?",
        options=[
            "The narrator describes a recurring difficulty and then reinterprets it in a more positive way.",
            "The narrator explains a problem and then proposes a technical solution to it.",
            "The narrator compares two languages and concludes that one is richer.",
            "The narrator tells a story about a grandmother and then describes her house.",
        ],
        correct="The narrator describes a recurring difficulty and then reinterprets it in a more positive way.",
        explanation=(
            "Primero el problema que se repite (la frase, la nota al pie, \"each "
            "time\"); después el giro: \"I no longer think of this as a "
            "failure\". No hay una solución técnica: el narrador cambia de "
            "mirada, no de método. Y la conclusión es justo que la palabra NO "
            "muestra un vacío del otro idioma, así que no declara a ninguno más "
            "rico."
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
    # I-1b · Sprint 4 · ampliación del banco (de 6 a 25). Mismas reglas que los
    # de arriba: propios, enunciado en inglés, explicación en español con la
    # trampa de cada distractor. Las respuestas las comprueba
    # `tests/test_banco_sat_i1b.py` haciendo la cuenta.
    _item(
        "sat-alg-7",
        habilidad="sat_algebra",
        nivel=NIVEL_FUNDAMENTOS,
        question="If 4(x + 2) = 28, what is the value of x?",
        options=["5", "7", "6.5", "3"],
        correct="5",
        explanation=(
            "Primero se divide entre 4: x + 2 = 7. Después se resta 2: x = 5. El "
            "distractor 7 es el valor de x + 2, un paso antes de terminar. El 6.5 "
            "sale de olvidar que el 4 multiplica TODO el paréntesis (4x + 2 = 28). "
            "Comprueba: 4(5 + 2) = 28."
        ),
    ),
    _item(
        "sat-alg-8",
        habilidad="sat_algebra",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "A taxi charges a fixed fee of 3 dollars plus 2 dollars per kilometre. "
            "A ride cost 19 dollars. How many kilometres long was the ride?"
        ),
        options=["8", "11", "9.5", "6"],
        correct="8",
        explanation=(
            "La ecuación es 2k + 3 = 19. Se quita lo fijo: 2k = 16, y k = 8. El "
            "9.5 sale de dividir 19 entre 2 sin restar la tarifa fija, y el 11 de "
            "SUMARLA en vez de restarla. Lo fijo se paga una vez y no depende de "
            "los kilómetros: siempre sale primero."
        ),
    ),
    _item(
        "sat-alg-9",
        habilidad="sat_algebra",
        nivel=NIVEL_FUNDAMENTOS,
        question="If x/3 + 2 = 6, what is the value of x?",
        options=["12", "24", "4", "6"],
        correct="12",
        explanation=(
            "Se resta 2: x/3 = 4. Se multiplica por 3: x = 12. El distractor 4 es "
            "el valor de x/3, no de x. El 24 sale de multiplicar por 3 antes de "
            "restar el 2: (6 + 2) × 3. El orden importa: deshaz primero lo que "
            "está más afuera (la suma) y al final lo que está pegado a la x."
        ),
    ),
    _item(
        "sat-alg-10",
        habilidad="sat_algebra",
        nivel=NIVEL_FUNDAMENTOS,
        question="What value of x satisfies 7 − x = 2x + 1?",
        options=["2", "−2", "6", "8/3"],
        correct="2",
        explanation=(
            "Se pasan las x a un lado y los números al otro: 7 − 1 = 2x + x, o "
            "sea 6 = 3x, y x = 2. El 6 es el valor de 3x. El 8/3 sale de sumar el "
            "1 en vez de restarlo (7 + 1 = 3x). Comprueba: 7 − 2 = 5 y 2(2) + 1 = 5."
        ),
    ),
    _item(
        "sat-alg-11",
        habilidad="sat_algebra",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "The sum of a number and 9 is equal to 4 times the number. What is the "
            "number?"
        ),
        options=["3", "9/4", "13", "36"],
        correct="3",
        explanation=(
            "Traducido: n + 9 = 4n. Se resta n: 9 = 3n, y n = 3. El 9/4 sale de "
            "escribir 4n = 9 olvidando que la n también estaba a la izquierda. El "
            "36 es 4 × 9. En problemas de palabras, escribe la ecuación completa "
            "antes de hacer cualquier cuenta."
        ),
    ),
    _item(
        "sat-alg-12",
        habilidad="sat_algebra",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "The graph of y = 3x − 4 crosses the y-axis at which value of y?"
        ),
        options=["−4", "3", "4", "4/3"],
        correct="−4",
        explanation=(
            "La recta cruza el eje y cuando x = 0: y = 3(0) − 4 = −4. En la forma "
            "y = mx + b, ese punto es la b. El 3 es la pendiente, no el corte. El "
            "4/3 es donde cruza el eje X (cuando y = 0), que es la otra pregunta "
            "que suelen confundir."
        ),
    ),
    _item(
        "sat-alg-13",
        habilidad="sat_algebra",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Maria has 50 dollars and spends 6 dollars every day. Which expression "
            "gives the amount of money she has left after d days?"
        ),
        options=["50 − 6d", "6d − 50", "50d − 6", "44d"],
        correct="50 − 6d",
        explanation=(
            "Empieza con 50 y cada día resta 6: después de d días restó 6d. "
            "6d − 50 da negativo al principio, que no tiene sentido. El 44d sale "
            "de restar 50 − 6 una sola vez y multiplicar. Truco: prueba con d = 1, "
            "la respuesta correcta tiene que dar 44."
        ),
    ),
    _item(
        "sat-alg-14",
        habilidad="sat_algebra",
        nivel=NIVEL_INTERMEDIO,
        question="If x + y = 10 and x − y = 4, what is the value of y?",
        options=["3", "7", "6", "4"],
        correct="3",
        explanation=(
            "Sumando las ecuaciones: 2x = 14, x = 7. Reemplazando: 7 + y = 10, "
            "y = 3. El distractor 7 es la x: la pregunta pide la y. Otra forma, "
            "más corta: restando las ecuaciones queda 2y = 6. Lee siempre al final "
            "qué variable te piden."
        ),
    ),
    _item(
        "sat-alg-15",
        habilidad="sat_algebra",
        nivel=NIVEL_INTERMEDIO,
        question="Which of the following gives all solutions of |x − 3| = 5?",
        options=["x = 8 or x = −2", "x = 8 only", "x = 2 or x = −8", "x = −2 only"],
        correct="x = 8 or x = −2",
        explanation=(
            "El valor absoluto es una distancia: x está a 5 unidades del 3, hacia "
            "un lado o hacia el otro. Entonces x − 3 = 5 (x = 8) o x − 3 = −5 "
            "(x = −2). Quedarse solo con el 8 es el error más común. El par 2 y −8 "
            "sale de leer |x + 3| en vez de |x − 3|."
        ),
    ),
    _item(
        "sat-alg-16",
        habilidad="sat_algebra",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A line has a slope of −3 and passes through the point (0, 2). Which "
            "is an equation of the line?"
        ),
        options=["y = −3x + 2", "y = 2x − 3", "y = −3x − 2", "y = 3x + 2"],
        correct="y = −3x + 2",
        explanation=(
            "En y = mx + b, m es la pendiente y b el punto donde cruza el eje y. "
            "El punto (0, 2) está sobre el eje y, así que b = 2, y m = −3. La "
            "opción y = 2x − 3 invierte los papeles; las otras dos cambian un "
            "signo. Comprueba: con x = 0, y = 2."
        ),
    ),
    _item(
        "sat-alg-17",
        habilidad="sat_algebra",
        nivel=NIVEL_INTERMEDIO,
        question="Which line is parallel to the line y = 2x + 5?",
        options=["y = 2x − 3", "y = −2x + 5", "y = (1/2)x + 5", "y = −(1/2)x − 3"],
        correct="y = 2x − 3",
        explanation=(
            "Las rectas paralelas tienen la MISMA pendiente y distinto corte. La "
            "pendiente de y = 2x + 5 es 2, y la única opción con pendiente 2 es "
            "y = 2x − 3. La opción −(1/2) es la pendiente de una perpendicular, "
            "que es la otra pregunta típica. Que compartan el +5 no las hace "
            "paralelas: comparten un punto."
        ),
    ),
    _item(
        "sat-alg-18",
        habilidad="sat_algebra",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Three notebooks and two pens cost 13 dollars. One notebook and two "
            "pens cost 7 dollars. What is the price of one notebook?"
        ),
        options=["3 dollars", "2 dollars", "4 dollars", "6 dollars"],
        correct="3 dollars",
        explanation=(
            "Las dos compras tienen los mismos dos bolígrafos. La diferencia (13 − 7 "
            "= 6 dólares) es solo de cuadernos: 2 cuadernos cuestan 6, así que uno "
            "cuesta 3. El distractor 6 es el precio de DOS cuadernos. El 2 es el "
            "precio de un bolígrafo (7 − 3 = 4, entre 2). Restar ecuaciones que "
            "comparten un término es el camino corto."
        ),
    ),
    _item(
        "sat-alg-19",
        habilidad="sat_algebra",
        nivel=NIVEL_INTERMEDIO,
        question="Which of the following is equivalent to 2(x − 1) ≤ 3x + 4?",
        options=["x ≥ −6", "x ≤ −6", "x ≥ 6", "x ≤ 6"],
        correct="x ≥ −6",
        explanation=(
            "Se distribuye: 2x − 2 ≤ 3x + 4. Se pasan las x a la derecha, donde "
            "quedan positivas: −2 − 4 ≤ 3x − 2x, o sea −6 ≤ x, que es x ≥ −6. "
            "Pasarlas a la derecha evita dividir por un negativo y voltear el "
            "signo. La opción x ≤ −6 es justo el error de dividir entre −1 sin "
            "voltearlo."
        ),
    ),
    _item(
        "sat-alg-20",
        habilidad="sat_algebra",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A plumber charges a fixed visit fee plus an hourly rate. A 2-hour job "
            "costs 110 dollars and a 5-hour job costs 230 dollars. What is the "
            "hourly rate?"
        ),
        options=["40 dollars", "46 dollars", "55 dollars", "120 dollars"],
        correct="40 dollars",
        explanation=(
            "Entre los dos trabajos la tarifa fija es la misma, así que la "
            "diferencia es solo por horas: 230 − 110 = 120 dólares por 3 horas "
            "más, o sea 40 por hora (y la visita cuesta 30). El 55 y el 46 "
            "dividen el total entre las horas, como si no hubiera tarifa fija. El "
            "120 es la diferencia sin dividir entre las 3 horas."
        ),
    ),
    _item(
        "sat-alg-21",
        habilidad="sat_algebra",
        nivel=NIVEL_AVANZADO,
        question=(
            "In the system 2x + 3y = 6 and 4x + ky = 12, k is a constant. For what "
            "value of k does the system have infinitely many solutions?"
        ),
        options=["6", "3", "−6", "12"],
        correct="6",
        explanation=(
            "Infinitas soluciones quiere decir que las dos ecuaciones son la "
            "MISMA recta. La segunda tiene que ser la primera multiplicada por un "
            "número: 4x es 2 × 2x y 12 es 2 × 6, así que el factor es 2 y "
            "k = 2 × 3 = 6. El distractor 3 es el coeficiente original sin "
            "multiplicar. Si te pidieran \"ninguna solución\", cambiaría solo el "
            "lado derecho."
        ),
    ),
    _item(
        "sat-alg-22",
        habilidad="sat_algebra",
        nivel=NIVEL_AVANZADO,
        question=(
            "The lines 3x + 2y = 12 and y = x + 1 intersect at the point (a, b). "
            "What is the value of a + b?"
        ),
        options=["5", "2", "3", "6"],
        correct="5",
        explanation=(
            "Se reemplaza la y de la segunda en la primera: 3x + 2(x + 1) = 12, "
            "5x + 2 = 12, x = 2. Entonces y = 3, y a + b = 5. Los distractores 2 "
            "y 3 son cada coordenada por separado: la pregunta pide la suma. "
            "Cuando una ecuación ya trae la y despejada, sustituir es lo más rápido."
        ),
    ),
    _item(
        "sat-alg-23",
        habilidad="sat_algebra",
        nivel=NIVEL_AVANZADO,
        question="If a/b = 3/4 and b = 2a − 10, what is the value of a?",
        options=["15", "20", "12", "30"],
        correct="15",
        explanation=(
            "De a/b = 3/4 sale b = 4a/3. Igualando: 4a/3 = 2a − 10. Multiplicando "
            "por 3: 4a = 6a − 30, entonces 2a = 30 y a = 15 (y b = 20). El 20 es "
            "la b. El 30 es el valor de 2a. Comprueba la razón: 15/20 = 3/4."
        ),
    ),
    _item(
        "sat-alg-24",
        habilidad="sat_algebra",
        nivel=NIVEL_AVANZADO,
        question=(
            "Line ℓ is perpendicular to the line y = (2/3)x + 1 and passes through "
            "the point (0, 4). Which is an equation of line ℓ?"
        ),
        options=[
            "y = −(3/2)x + 4",
            "y = (3/2)x + 4",
            "y = −(2/3)x + 4",
            "y = (2/3)x − 4",
        ],
        correct="y = −(3/2)x + 4",
        explanation=(
            "La pendiente de una perpendicular es la recíproca CON el signo "
            "cambiado: de 2/3 pasa a −3/2. El punto (0, 4) da el corte: +4. La "
            "opción (3/2) invierte la fracción pero olvida el signo; la −(2/3) "
            "cambia el signo pero no invierte. Hacen falta las dos cosas."
        ),
    ),
    _item(
        "sat-alg-25",
        habilidad="sat_algebra",
        nivel=NIVEL_AVANZADO,
        question=(
            "The sum of two numbers is 30. One of the numbers is 6 more than twice "
            "the other. What is the larger number?"
        ),
        options=["22", "8", "18", "24"],
        correct="22",
        explanation=(
            "Si el menor es x, el mayor es 2x + 6. Entonces x + 2x + 6 = 30, "
            "3x = 24, x = 8, y el mayor es 22. El 8 es el número menor: la "
            "pregunta pide el mayor. El 24 es el valor de 3x. Comprueba: "
            "8 + 22 = 30 y 22 = 2(8) + 6."
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
    # I-1b · Sprint 4 · ampliación del banco (de 6 a 25). Ver la nota en álgebra.
    _item(
        "sat-dat-7",
        habilidad="sat_datos",
        nivel=NIVEL_FUNDAMENTOS,
        question="12 is what percent of 48?",
        options=["25 percent", "4 percent", "36 percent", "400 percent"],
        correct="25 percent",
        explanation=(
            "\"Qué porcentaje es A de B\" se calcula A/B: 12/48 = 0.25, o sea 25%. "
            "El 400% sale de dividir al revés (48/12 = 4). El 36 es la resta "
            "48 − 12, que no es un porcentaje de nada. La parte va arriba; el "
            "total, abajo."
        ),
    ),
    _item(
        "sat-dat-8",
        habilidad="sat_datos",
        nivel=NIVEL_FUNDAMENTOS,
        question="What is the mean of the values 4, 7, 10 and 15?",
        options=["9", "8.5", "10", "36"],
        correct="9",
        explanation=(
            "La media es la suma entre la cantidad de datos: (4 + 7 + 10 + 15) / 4 "
            "= 36/4 = 9. El 8.5 es la MEDIANA (el promedio de los dos del medio, "
            "7 y 10). El 36 es la suma sin dividir. En el examen ponen las dos "
            "medidas juntas a propósito: lee cuál te piden."
        ),
    ),
    _item(
        "sat-dat-9",
        habilidad="sat_datos",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "On a map, 1 centimetre represents 5 kilometres. Two towns are 7.5 "
            "centimetres apart on the map. What is the actual distance between "
            "them?"
        ),
        options=["37.5 kilometres", "1.5 kilometres", "12.5 kilometres", "35 kilometres"],
        correct="37.5 kilometres",
        explanation=(
            "Cada centímetro vale 5 km, así que 7.5 cm valen 7.5 × 5 = 37.5 km. "
            "El 1.5 sale de dividir en vez de multiplicar. El 12.5 suma 7.5 + 5. "
            "El 35 multiplica solo los 7 centímetros enteros y se come el medio."
        ),
    ),
    _item(
        "sat-dat-10",
        habilidad="sat_datos",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "The price of a book is 50 dollars. The price increases by 10 percent. "
            "What is the new price?"
        ),
        options=["55 dollars", "60 dollars", "5 dollars", "50.10 dollars"],
        correct="55 dollars",
        explanation=(
            "El 10% de 50 es 5, y el precio sube a 55. Atajo: subir 10% es "
            "multiplicar por 1.10. El 5 es el aumento, no el precio nuevo. El "
            "50.10 sale de sumar \"10\" como si fueran centavos. El 60 suma 10 "
            "dólares en vez de 10 por ciento."
        ),
    ),
    _item(
        "sat-dat-11",
        habilidad="sat_datos",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "A class has 12 boys and 18 girls. What is the ratio of boys to the "
            "total number of students in the class?"
        ),
        options=["2:5", "2:3", "3:5", "3:2"],
        correct="2:5",
        explanation=(
            "El total es 12 + 18 = 30, y 12:30 simplificado es 2:5. El 2:3 es la "
            "razón de niños a NIÑAS (12:18), que es lo que la mayoría responde "
            "sin leer \"to the total\". El 3:5 es niñas sobre el total. Antes de "
            "simplificar, mira qué dos cantidades compara la pregunta."
        ),
    ),
    _item(
        "sat-dat-12",
        habilidad="sat_datos",
        nivel=NIVEL_FUNDAMENTOS,
        question="What is the median of the values 3, 9, 1, 8 and 4?",
        options=["4", "1", "5", "8"],
        correct="4",
        explanation=(
            "Para la mediana primero se ORDENAN: 1, 3, 4, 8, 9. El del medio es 4. "
            "El 1 es el que queda en el medio sin ordenar, que es la trampa. El 5 "
            "es la media (25/5). Ordenar es un paso que no se puede saltar."
        ),
    ),
    _item(
        "sat-dat-13",
        habilidad="sat_datos",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "A store sells 3 pens for 2.40 dollars. At the same price per pen, how "
            "much do 5 pens cost?"
        ),
        options=["4.00 dollars", "4.80 dollars", "3.60 dollars", "12.00 dollars"],
        correct="4.00 dollars",
        explanation=(
            "Precio por unidad: 2.40 / 3 = 0.80 dólares. Cinco cuestan 5 × 0.80 = "
            "4.00. El 12.00 multiplica 2.40 por 5, como si 2.40 fuera el precio de "
            "uno. El 4.80 duplica el paquete de 3 (eso serían 6). Bajar a \"por "
            "uno\" evita las tres trampas."
        ),
    ),
    _item(
        "sat-dat-14",
        habilidad="sat_datos",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "The price of an item is increased by 20 percent and then the new price "
            "is decreased by 20 percent. How does the final price compare with the "
            "original price?"
        ),
        options=[
            "It is 4 percent lower.",
            "It is the same.",
            "It is 4 percent higher.",
            "It is 20 percent lower.",
        ],
        correct="It is 4 percent lower.",
        explanation=(
            "Con 100 de precio: sube a 120, y el 20% de 120 es 24, así que baja a "
            "96. Queda 4% por debajo. El \"es igual\" es la intuición que el examen "
            "castiga: el segundo 20% se calcula sobre un número más grande. En "
            "multiplicadores: 1.20 × 0.80 = 0.96."
        ),
    ),
    _item(
        "sat-dat-15",
        habilidad="sat_datos",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "The mean of a student's first 5 test scores is 82. What score does "
            "the student need on the 6th test to raise the mean of all 6 scores "
            "to 84?"
        ),
        options=["94", "86", "84", "100"],
        correct="94",
        explanation=(
            "Se trabaja con totales, no con promedios: los 5 primeros suman "
            "5 × 82 = 410, y para un promedio de 84 en 6 hacen falta 6 × 84 = 504 "
            "puntos. Falta 504 − 410 = 94. El 86 sale de pensar \"subir 2 puntos, "
            "entonces 2 más que el promedio deseado\": no alcanza, porque el "
            "último examen tiene que levantar a los otros cinco."
        ),
    ),
    _item(
        "sat-dat-16",
        habilidad="sat_datos",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A line of best fit for a set of data is y = 1.5x + 20, where y is the "
            "height of a plant, in centimetres, and x is the number of weeks since "
            "it was measured for the first time. What is the best interpretation "
            "of 1.5 in this context?"
        ),
        options=[
            "The plant grows about 1.5 centimetres per week.",
            "The plant was about 1.5 centimetres tall when first measured.",
            "The plant grows about 20 centimetres per week.",
            "After 1.5 weeks, the plant is about 20 centimetres tall.",
        ],
        correct="The plant grows about 1.5 centimetres per week.",
        explanation=(
            "En y = mx + b, la pendiente (1.5) es cuánto cambia y por cada unidad "
            "de x: centímetros por semana. El 20 es la altura en la semana 0, el "
            "punto de partida. La segunda y la tercera opción intercambian los "
            "papeles de los dos números. \"About\" está ahí porque es una recta de "
            "ajuste: describe la tendencia, no cada planta."
        ),
    ),
    _item(
        "sat-dat-17",
        habilidad="sat_datos",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A train travels at 90 kilometres per hour. What is this speed in "
            "metres per second?"
        ),
        options=["25", "1.5", "324", "250"],
        correct="25",
        explanation=(
            "90 km son 90 000 m, y una hora son 3 600 segundos: 90 000 / 3 600 = "
            "25 m/s. El 1.5 divide entre 60 solo una vez (de horas a minutos). El "
            "324 multiplica por 3.6 en vez de dividir. Escribe las unidades en la "
            "cuenta: si al final no queda m/s, la operación está al revés."
        ),
    ),
    _item(
        "sat-dat-18",
        habilidad="sat_datos",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A bag contains 4 red marbles, 6 blue marbles and 10 green marbles. "
            "If one marble is chosen at random, what is the probability that it is "
            "NOT green?"
        ),
        options=["1/2", "1/10", "3/10", "1/5"],
        correct="1/2",
        explanation=(
            "No verdes son 4 + 6 = 10 de un total de 20: 10/20 = 1/2. El 3/10 es "
            "solo la probabilidad de azul y el 1/5 solo la de roja: cada uno "
            "cuenta la mitad de los casos. Atajo: P(no verde) = 1 − P(verde) = "
            "1 − 10/20."
        ),
    ),
    _item(
        "sat-dat-19",
        habilidad="sat_datos",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "After a 15 percent discount, a laptop costs 680 dollars. What was the "
            "price before the discount?"
        ),
        options=["800 dollars", "782 dollars", "578 dollars", "695 dollars"],
        correct="800 dollars",
        explanation=(
            "Con descuento del 15% se paga el 85% del precio original: "
            "0.85 × P = 680, P = 680 / 0.85 = 800. El 782 sale de sumarle el 15% "
            "a 680, que es la trampa clásica: ese 15% se calculó sobre el precio "
            "original, no sobre el rebajado. Comprueba: el 15% de 800 es 120, y "
            "800 − 120 = 680."
        ),
    ),
    _item(
        "sat-dat-20",
        habilidad="sat_datos",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Data set A is 48, 49, 50, 51, 52. Data set B is 30, 40, 50, 60, 70. "
            "Which statement is true?"
        ),
        options=[
            "The sets have the same mean, and set B has the larger standard deviation.",
            "The sets have the same mean, and set A has the larger standard deviation.",
            "Set B has the larger mean.",
            "The sets have the same standard deviation.",
        ],
        correct="The sets have the same mean, and set B has the larger standard deviation.",
        explanation=(
            "Los dos están centrados en 50, así que la media es la misma. La "
            "desviación estándar mide qué tan lejos están los datos del centro: "
            "en B se alejan hasta 20, en A apenas 2. No hace falta calcularla; el "
            "examen pregunta la idea. Que B tenga números más grandes no le sube "
            "la media."
        ),
    ),
    _item(
        "sat-dat-21",
        habilidad="sat_datos",
        nivel=NIVEL_AVANZADO,
        question=(
            "A random sample of 400 residents of a city was surveyed, and 36 "
            "percent said they support building a new park. The margin of error "
            "for this estimate is 5 percentage points. Which conclusion is best "
            "supported?"
        ),
        options=[
            "It is plausible that between 31 and 41 percent of all residents of the city support the park.",
            "Exactly 36 percent of all residents of the city support the park.",
            "Between 31 and 41 percent of the 400 residents surveyed support the park.",
            "Most residents of the city support the park.",
        ],
        correct="It is plausible that between 31 and 41 percent of all residents of the city support the park.",
        explanation=(
            "El margen de error habla de TODA la población, no de la muestra: en "
            "la muestra ya sabemos que fue exactamente 36%. Por eso la tercera "
            "opción está mal aunque traiga los mismos números. \"Exactamente\" "
            "ignora el margen, y \"la mayoría\" contradice el dato. La palabra "
            "\"plausible\" es la que el examen usa para estas conclusiones."
        ),
    ),
    _item(
        "sat-dat-22",
        habilidad="sat_datos",
        nivel=NIVEL_AVANZADO,
        question=(
            "A population of bacteria doubles every 3 hours. If there are 500 "
            "bacteria now, how many will there be after 12 hours?"
        ),
        options=["8,000", "2,000", "4,000", "6,000"],
        correct="8,000",
        explanation=(
            "En 12 horas hay 12/3 = 4 duplicaciones: 500 × 2 × 2 × 2 × 2 = "
            "500 × 16 = 8 000. El 2 000 multiplica por 4 (las duplicaciones) en "
            "vez de por 2⁴. El 6 000 multiplica por 12 horas, como si creciera "
            "igual cada hora. Duplicar es crecimiento exponencial: se multiplica, "
            "no se suma."
        ),
    ),
    _item(
        "sat-dat-23",
        habilidad="sat_datos",
        nivel=NIVEL_AVANZADO,
        question=(
            "A savings account starts with 1,000 dollars and earns 5 percent "
            "interest per year, compounded once a year. How much money is in the "
            "account after 2 years?"
        ),
        options=["1,102.50 dollars", "1,100.00 dollars", "1,105.00 dollars", "1,050.00 dollars"],
        correct="1,102.50 dollars",
        explanation=(
            "Cada año se multiplica por 1.05: 1 000 × 1.05 × 1.05 = 1 102.50. El "
            "1 100 es interés simple (50 + 50): olvida que el segundo año el 5% se "
            "calcula sobre 1 050. El 1 050 es el saldo después de un solo año. "
            "Interés compuesto es lo mismo que el aumento porcentual repetido."
        ),
    ),
    _item(
        "sat-dat-24",
        habilidad="sat_datos",
        nivel=NIVEL_AVANZADO,
        question=(
            "In a group of 60 students, 25 take French, 30 take art, and 10 take "
            "both French and art. How many students take neither French nor art?"
        ),
        options=["15", "5", "25", "45"],
        correct="15",
        explanation=(
            "Los 10 que toman las dos materias están contados en los 25 Y en los "
            "30. Los que toman al menos una son 25 + 30 − 10 = 45, y ninguna, "
            "60 − 45 = 15. El 5 sale de no restar los 10 repetidos (60 − 55). El "
            "45 es la cantidad que toma al menos una: es el paso intermedio."
        ),
    ),
    _item(
        "sat-dat-25",
        habilidad="sat_datos",
        nivel=NIVEL_AVANZADO,
        question=(
            "Class A has 20 students with a mean score of 70. Class B has 30 "
            "students with a mean score of 80. What is the mean score of all 50 "
            "students?"
        ),
        options=["76", "75", "78", "74"],
        correct="76",
        explanation=(
            "No se promedian los promedios (eso da 75, el distractor), porque los "
            "grupos son de distinto tamaño. Se suman los totales: 20 × 70 = 1 400 "
            "y 30 × 80 = 2 400; la suma, 3 800, se divide entre 50 estudiantes: 76. La clase más "
            "grande pesa más, por eso el resultado queda más cerca de 80."
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
    # I-1b · Sprint 4 · ampliación del banco (de 6 a 25). Ver la nota en álgebra.
    _item(
        "sat-adv-7",
        habilidad="sat_avanzado",
        nivel=NIVEL_FUNDAMENTOS,
        question="A rectangle is 8 units long and 5 units wide. What is its perimeter?",
        options=["26", "40", "13", "21"],
        correct="26",
        explanation=(
            "El perímetro es la vuelta completa: 8 + 5 + 8 + 5 = 26, o 2(8 + 5). "
            "El 40 es el ÁREA (8 × 5), que es la confusión que buscan. El 13 suma "
            "solo dos lados, media vuelta. Perímetro se mide en unidades; área, "
            "en unidades cuadradas."
        ),
    ),
    _item(
        "sat-adv-8",
        habilidad="sat_avanzado",
        nivel=NIVEL_FUNDAMENTOS,
        question="What is the value of 2³ + 3²?",
        options=["17", "12", "15", "72"],
        correct="17",
        explanation=(
            "2³ = 2 × 2 × 2 = 8 y 3² = 3 × 3 = 9; la suma es 17. El 12 sale de "
            "multiplicar base por exponente (2 × 3 + 3 × 2), que es el error de "
            "fondo con potencias. El 72 multiplica los dos resultados (8 × 9) en "
            "vez de sumarlos."
        ),
    ),
    _item(
        "sat-adv-9",
        habilidad="sat_avanzado",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Two angles of a triangle measure 50 degrees and 60 degrees. What is "
            "the measure of the third angle?"
        ),
        options=["70 degrees", "110 degrees", "80 degrees", "90 degrees"],
        correct="70 degrees",
        explanation=(
            "Los ángulos de cualquier triángulo suman 180°: 180 − 50 − 60 = 70. "
            "El 110 es la suma de los dos dados, un paso antes de terminar. El 90 "
            "asume un triángulo rectángulo, y nada en el enunciado lo dice."
        ),
    ),
    _item(
        "sat-adv-10",
        habilidad="sat_avanzado",
        nivel=NIVEL_FUNDAMENTOS,
        question="Which expression is equivalent to (x + 3)(x − 3)?",
        options=["x² − 9", "x² + 9", "x² − 6x − 9", "x² − 3"],
        correct="x² − 9",
        explanation=(
            "Multiplicando todo por todo: x² − 3x + 3x − 9 = x² − 9; los términos "
            "del medio se cancelan. Es la \"diferencia de cuadrados\", y conviene "
            "reconocerla de memoria: (a + b)(a − b) = a² − b². El x² + 9 es el "
            "error de signo, y el x² − 3 multiplica solo los primeros y olvida "
            "elevar el 3."
        ),
    ),
    _item(
        "sat-adv-11",
        habilidad="sat_avanzado",
        nivel=NIVEL_FUNDAMENTOS,
        question="A circle has a radius of 5. What is its circumference?",
        options=["10π", "25π", "5π", "20π"],
        correct="10π",
        explanation=(
            "La circunferencia (el borde) es 2πr = 2π × 5 = 10π. El 25π es el "
            "ÁREA (πr²), que es la fórmula con la que la confunden. El 5π olvida "
            "el 2, o usa el radio donde iba el diámetro."
        ),
    ),
    _item(
        "sat-adv-12",
        habilidad="sat_avanzado",
        nivel=NIVEL_FUNDAMENTOS,
        question="If f(x) = x² − 1, what is the value of f(4)?",
        options=["15", "7", "17", "9"],
        correct="15",
        explanation=(
            "Se reemplaza x por 4: 4² − 1 = 16 − 1 = 15. El 7 sale de calcular "
            "2 × 4 − 1, o sea leer x² como 2x. El 17 suma el 1 en vez de "
            "restarlo. Escribir el número entre paréntesis, (4)² − 1, evita "
            "estos dos errores."
        ),
    ),
    _item(
        "sat-adv-13",
        habilidad="sat_avanzado",
        nivel=NIVEL_FUNDAMENTOS,
        question="A triangle has a base of 10 and a height of 6. What is its area?",
        options=["30", "60", "16", "32"],
        correct="30",
        explanation=(
            "El área de un triángulo es base por altura SOBRE DOS: (10 × 6) / 2 "
            "= 30. El 60 olvida dividir entre 2: esa sería el área del rectángulo "
            "que lo contiene. El 16 suma los dos números."
        ),
    ),
    _item(
        "sat-adv-14",
        habilidad="sat_avanzado",
        nivel=NIVEL_FUNDAMENTOS,
        question="Which expression is equivalent to 3x(x + 2)?",
        options=["3x² + 6x", "3x² + 2", "3x² + 6", "x² + 6x"],
        correct="3x² + 6x",
        explanation=(
            "El 3x multiplica a CADA término del paréntesis: 3x · x = 3x² y "
            "3x · 2 = 6x. El 3x² + 2 multiplica solo el primer término. El "
            "3x² + 6 multiplica el 2 por el 3 pero se olvida de la x. Comprueba "
            "con x = 1: 3(1)(3) = 9 y 3 + 6 = 9."
        ),
    ),
    _item(
        "sat-adv-15",
        habilidad="sat_avanzado",
        nivel=NIVEL_INTERMEDIO,
        question="What are the solutions of x² − 49 = 0?",
        options=[
            "x = 7 and x = −7",
            "x = 7 only",
            "x = 49 and x = −49",
            "x = 3.5 and x = −3.5",
        ],
        correct="x = 7 and x = −7",
        explanation=(
            "x² = 49 tiene DOS soluciones, porque (−7)² también es 49. Quedarse "
            "con el 7 es el error más frecuente. El 3.5 sale de dividir 49 entre "
            "2 y otra vez entre 7, confundiendo la raíz con una división."
        ),
    ),
    _item(
        "sat-adv-16",
        habilidad="sat_avanzado",
        nivel=NIVEL_INTERMEDIO,
        question="Which of the following is a factored form of x² + 7x + 12?",
        options=["(x + 3)(x + 4)", "(x + 2)(x + 6)", "(x + 1)(x + 12)", "(x − 3)(x − 4)"],
        correct="(x + 3)(x + 4)",
        explanation=(
            "Se buscan dos números que multiplicados den 12 y sumados den 7: "
            "3 y 4. Las otras dos parejas positivas también multiplican 12, pero "
            "suman 8 y 13: es la trampa, cumplir solo una de las dos condiciones. "
            "(x − 3)(x − 4) da +12 pero −7x."
        ),
    ),
    _item(
        "sat-adv-17",
        habilidad="sat_avanzado",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A cylinder has a radius of 3 and a height of 10. What is its volume?"
        ),
        options=["90π", "30π", "60π", "900π"],
        correct="90π",
        explanation=(
            "El volumen del cilindro es el área de la base por la altura: "
            "πr² × h = π × 9 × 10 = 90π. El 30π olvida elevar el radio al "
            "cuadrado. El 60π es el área de la superficie lateral (2πrh), otra "
            "fórmula del mismo cilindro."
        ),
    ),
    _item(
        "sat-adv-18",
        habilidad="sat_avanzado",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Two triangles are similar. A side of length 4 in the smaller triangle "
            "corresponds to a side of length 6 in the larger triangle. Another "
            "side of the smaller triangle has length 10. What is the length of the "
            "corresponding side of the larger triangle?"
        ),
        options=["15", "12", "20/3", "16"],
        correct="15",
        explanation=(
            "En triángulos semejantes los lados son proporcionales: el grande es "
            "6/4 = 1.5 veces el pequeño, y 10 × 1.5 = 15. El 12 suma la "
            "diferencia (10 + 2) en vez de multiplicar por la razón, que es el "
            "error típico. El 20/3 aplica la razón al revés (10 × 4/6)."
        ),
    ),
    _item(
        "sat-adv-19",
        habilidad="sat_avanzado",
        nivel=NIVEL_INTERMEDIO,
        question="If 2^(x + 1) = 32, what is the value of x?",
        options=["4", "5", "16", "15"],
        correct="4",
        explanation=(
            "32 es 2⁵, así que x + 1 = 5 y x = 4. El 5 es el exponente completo "
            "(x + 1), un paso antes de terminar. El 16 y el 15 tratan la "
            "ecuación como si fuera 2(x + 1) = 32. Con potencias, escribe los "
            "dos lados con la misma base y compara exponentes."
        ),
    ),
    _item(
        "sat-adv-20",
        habilidad="sat_avanzado",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A circle has a radius of 8. What is the length of an arc that "
            "corresponds to a central angle of 90 degrees?"
        ),
        options=["4π", "8π", "16π", "2π"],
        correct="4π",
        explanation=(
            "90° es la cuarta parte de 360°, así que el arco es la cuarta parte "
            "de la circunferencia: (1/4) × 2π × 8 = 4π. El 16π es la "
            "circunferencia completa. El 8π es media vuelta (180°). Arco = "
            "(ángulo/360) × circunferencia."
        ),
    ),
    _item(
        "sat-adv-21",
        habilidad="sat_avanzado",
        nivel=NIVEL_AVANZADO,
        question="What is the minimum value of f(x) = x² − 6x + 5?",
        options=["−4", "3", "5", "−9"],
        correct="−4",
        explanation=(
            "El mínimo de una parábola está en el vértice, en x = −b/(2a) = 6/2 = "
            "3. Pero la pregunta pide el VALOR mínimo, no dónde ocurre: "
            "f(3) = 9 − 18 + 5 = −4. El 3 es la x del vértice, la trampa "
            "principal. El 5 es el corte con el eje y."
        ),
    ),
    _item(
        "sat-adv-22",
        habilidad="sat_avanzado",
        nivel=NIVEL_AVANZADO,
        question="What is the sum of the solutions of 2x² − 8x + 3 = 0?",
        options=["4", "−4", "3/2", "8"],
        correct="4",
        explanation=(
            "No hace falta resolverla: en ax² + bx + c = 0, la suma de las "
            "soluciones es −b/a = −(−8)/2 = 4. El −4 olvida el signo menos de "
            "la fórmula. El 3/2 es el PRODUCTO de las soluciones (c/a). El 8 "
            "olvida dividir entre a. Resolverla con la fórmula general da lo "
            "mismo, pero toma cinco veces más tiempo."
        ),
    ),
    _item(
        "sat-adv-23",
        habilidad="sat_avanzado",
        nivel=NIVEL_AVANZADO,
        question=(
            "In the xy-plane, the graph of (x − 2)² + (y + 1)² = 25 is a circle. "
            "What are the center and the radius of the circle?"
        ),
        options=[
            "Center (2, −1), radius 5",
            "Center (−2, 1), radius 5",
            "Center (2, −1), radius 25",
            "Center (2, 1), radius 5",
        ],
        correct="Center (2, −1), radius 5",
        explanation=(
            "La forma es (x − h)² + (y − k)² = r², con centro (h, k). Como "
            "y + 1 = y − (−1), k = −1: el centro es (2, −1). El lado derecho es "
            "r², así que r = √25 = 5. Las trampas son las dos de siempre: copiar "
            "los signos tal como aparecen y olvidar sacar la raíz."
        ),
    ),
    _item(
        "sat-adv-24",
        habilidad="sat_avanzado",
        nivel=NIVEL_AVANZADO,
        question=(
            "In a right triangle, x is one of the acute angles and sin x = 3/5. "
            "What is cos x?"
        ),
        options=["4/5", "3/4", "5/3", "5/4"],
        correct="4/5",
        explanation=(
            "sin x = 3/5 dice que el cateto opuesto es 3 y la hipotenusa 5; por "
            "Pitágoras el otro cateto es 4 (es el triángulo 3-4-5). El coseno es "
            "adyacente sobre hipotenusa: 4/5. El 3/4 es la tangente. Los "
            "valores mayores que 1 (5/3, 5/4) son imposibles para seno y coseno: "
            "se descartan sin hacer cuentas."
        ),
    ),
    _item(
        "sat-adv-25",
        habilidad="sat_avanzado",
        nivel=NIVEL_AVANZADO,
        question="If x² + y² = 20 and xy = 8, what is the value of (x + y)²?",
        options=["36", "28", "20", "64"],
        correct="36",
        explanation=(
            "(x + y)² = x² + 2xy + y² = (x² + y²) + 2xy = 20 + 16 = 36. No hace "
            "falta encontrar x ni y. El 28 suma xy una sola vez (olvida el 2). El "
            "20 es el error de creer que (x + y)² = x² + y². Cuando te dan sumas "
            "de cuadrados y productos, busca la identidad."
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
    # I-3 · Sprint 4 · ampliación del banco de IELTS (de 8 a 25), sobre 5 textos
    # propios nuevos. True/False/Not Given: True si el texto lo dice, False si lo
    # contradice, Not Given si no dice nada al respecto.
    _item(
        "ielts-read-9",
        habilidad="ielts_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="desalination",
        question="According to the text, why is reverse osmosis still expensive?",
        options=[
            "Pumping water at high pressure uses a lot of electricity.",
            "The membranes must be replaced every day.",
            "It requires boiling large amounts of water.",
            "Brine has to be transported far from the coast.",
        ],
        correct="Pumping water at high pressure uses a lot of electricity.",
        explanation=(
            "El texto lo dice con todas las letras: \"largely because pumping "
            "water at high pressure requires a great deal of electricity\". "
            "Hervir el agua es el método VIEJO, el que la ósmosis inversa "
            "reemplazó, y por eso es la trampa. Del cambio de membranas no se "
            "dice nada."
        ),
    ),
    _item(
        "ielts-read-10",
        habilidad="ielts_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="desalination",
        question=(
            "Decide whether the statement agrees with the text.\n\n"
            "Statement: “Reverse osmosis uses less energy than boiling seawater.”"
        ),
        options=["True", "False", "Not Given"],
        correct="True",
        explanation=(
            "El texto dice que la ósmosis inversa \"uses far less energy than "
            "the older approach of boiling water\". La afirmación dice lo mismo "
            "con otras palabras: True. Que siga siendo cara no la contradice: "
            "gasta menos que hervir, pero gasta bastante."
        ),
    ),
    _item(
        "ielts-read-11",
        habilidad="ielts_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="desalination",
        question=(
            "Decide whether the statement agrees with the text.\n\n"
            "Statement: “Most desalination plants are located in Asia.”"
        ),
        options=["Not Given", "True", "False"],
        correct="Not Given",
        explanation=(
            "El texto habla de \"dry coastal regions\" pero nunca nombra un "
            "continente. No lo confirma ni lo contradice: Not Given. La trampa "
            "es responder con lo que uno sabe del mundo: en el IELTS solo cuenta "
            "lo que dice el texto."
        ),
    ),
    _item(
        "ielts-read-12",
        habilidad="ielts_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="urban_heat",
        question=(
            "According to the text, when is the temperature difference between "
            "cities and the countryside usually greatest?"
        ),
        options=["After sunset", "At midday", "In the early morning", "In winter"],
        correct="After sunset",
        explanation=(
            "\"The difference is usually greatest after sunset\": las superficies "
            "oscuras sueltan de noche el calor que guardaron de día. Mediodía es "
            "la respuesta intuitiva (cuando más calienta el sol), y por eso es la "
            "trampa."
        ),
    ),
    _item(
        "ielts-read-13",
        habilidad="ielts_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="urban_heat",
        question=(
            "Complete the sentence according to the text.\n\n"
            "Painting roofs white helps because light colours ______."
        ),
        options=[
            "reflect more sunlight",
            "release water vapour",
            "shade the streets",
            "absorb heat during the day",
        ],
        correct="reflect more sunlight",
        explanation=(
            "\"Since light colours reflect more sunlight\". Soltar vapor de agua "
            "y dar sombra son lo que hacen los ÁRBOLES, en la frase anterior: la "
            "trampa es mezclar las dos medidas. Absorber calor es lo que hacen "
            "las superficies oscuras, lo contrario."
        ),
    ),
    _item(
        "ielts-read-14",
        habilidad="ielts_lectura",
        nivel=NIVEL_AVANZADO,
        passage="urban_heat",
        question=(
            "What can be inferred about the neighbourhoods where several measures "
            "were combined?"
        ),
        options=[
            "Their nights became cooler, but the heat island effect did not disappear.",
            "The heat island effect was completely eliminated.",
            "Trees turned out to be more effective than white roofs.",
            "They became cooler than the surrounding countryside.",
        ],
        correct="Their nights became cooler, but the heat island effect did not disappear.",
        explanation=(
            "Juntas dos frases: las medidas \"do not remove the effect entirely\" "
            "y donde se combinaron \"summer night temperatures have fallen\". La "
            "segunda opción contradice la primera frase. La tercera compara dos "
            "medidas que el texto nunca compara, y la cuarta va mucho más allá "
            "de lo que dice."
        ),
    ),
    _item(
        "ielts-read-15",
        habilidad="ielts_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="language_loss",
        question=(
            "Decide whether the statement agrees with the text.\n\n"
            "Statement: “Languages usually disappear suddenly.”"
        ),
        options=["False", "True", "Not Given"],
        correct="False",
        explanation=(
            "El texto dice lo contrario: \"A language rarely disappears "
            "suddenly\" y explica que tarda dos o tres generaciones. Cuando el "
            "texto afirma lo opuesto, es False; Not Given es solo cuando el texto "
            "no dice nada del tema."
        ),
    ),
    _item(
        "ielts-read-16",
        habilidad="ielts_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="language_loss",
        question=(
            "Why does the writer mention local plants, weather patterns and "
            "navigation?"
        ),
        options=[
            "To show that losing a language also means losing knowledge",
            "To explain why parents choose a dominant language",
            "To describe what recording projects usually document",
            "To give examples of languages that have already disappeared",
        ],
        correct="To show that losing a language also means losing knowledge",
        explanation=(
            "La frase empieza con \"more than words are lost\": los ejemplos "
            "demuestran que con la lengua se va un saber que \"has never been "
            "written down\". No explican la decisión de los padres (eso viene "
            "antes) ni describen lo que registran los proyectos (eso viene "
            "después)."
        ),
    ),
    _item(
        "ielts-read-17",
        habilidad="ielts_lectura",
        nivel=NIVEL_AVANZADO,
        passage="language_loss",
        question=(
            "Decide whether the statement agrees with the text.\n\n"
            "Statement: “Recording projects are enough to keep a language alive.”"
        ),
        options=["False", "True", "Not Given"],
        correct="False",
        explanation=(
            "El texto dice que los registros \"can preserve grammar and "
            "vocabulary, but\" una lengua \"only stays alive if children "
            "continue to learn it at home\". Ese \"only\" contradice que grabar "
            "baste: False. La palabra \"but\" suele marcar justo dónde está la "
            "respuesta."
        ),
    ),
    _item(
        "ielts-read-18",
        habilidad="ielts_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="four_day_week",
        question=(
            "According to the text, what did most firms do after the six-month "
            "trial?"
        ),
        options=[
            "They decided to continue the four-day week.",
            "They returned to a five-day week.",
            "They reduced their employees' salaries.",
            "They extended the trial to healthcare services.",
        ],
        correct="They decided to continue the four-day week.",
        explanation=(
            "\"Most chose to continue the arrangement after six months\". La "
            "salud aparece en el texto, pero como un sector donde el resultado "
            "podría NO aplicar, según los críticos, no como algo que hicieron "
            "las empresas."
        ),
    ),
    _item(
        "ielts-read-19",
        habilidad="ielts_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="four_day_week",
        question=(
            "Decide whether the statement agrees with the text.\n\n"
            "Statement: “Employees in the trial were paid less for working fewer "
            "days.”"
        ),
        options=["False", "True", "Not Given"],
        correct="False",
        explanation=(
            "La primera frase dice que los empleados \"keep their full salary\". "
            "La afirmación lo contradice: False. Ojo con el sentido común (\"si "
            "trabajan menos, ganan menos\"): el texto dice otra cosa, y manda el "
            "texto."
        ),
    ),
    _item(
        "ielts-read-20",
        habilidad="ielts_lectura",
        nivel=NIVEL_AVANZADO,
        passage="four_day_week",
        question="How does the writer present the debate about the four-day week?",
        options=[
            "By reporting the critics' objections and the supporters' reply without taking a side",
            "By arguing that the four-day week should be adopted in every sector",
            "By rejecting the trial because the companies volunteered",
            "By claiming that healthcare has already adopted a shorter week",
        ],
        correct="By reporting the critics' objections and the supporters' reply without taking a side",
        explanation=(
            "El texto dice \"critics point out…\" y \"supporters reply…\" y nunca "
            "da su propia opinión. Las opciones dos y tres le atribuyen al autor "
            "la postura de uno de los bandos. En estas preguntas, fíjate en quién "
            "dice cada cosa: no todo lo que aparece en el texto es la opinión del "
            "autor."
        ),
    ),
    _item(
        "ielts-read-21",
        habilidad="ielts_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="microplastics",
        question="According to the text, where do most microplastics come from?",
        options=[
            "Larger plastic objects that break down over time",
            "Beads added to cosmetics",
            "Arctic ice",
            "The bodies of animals",
        ],
        correct="Larger plastic objects that break down over time",
        explanation=(
            "\"Most come from larger objects that break down over time\". Las "
            "microesferas de los cosméticos son el ejemplo de las que se "
            "fabrican de ese tamaño, la minoría. El hielo del Ártico y los "
            "animales son lugares donde se ENCONTRARON, no de donde vienen."
        ),
    ),
    _item(
        "ielts-read-22",
        habilidad="ielts_lectura",
        nivel=NIVEL_FUNDAMENTOS,
        passage="microplastics",
        question=(
            "Decide whether the statement agrees with the text.\n\n"
            "Statement: “Synthetic clothing can release plastic fibres when it is "
            "washed.”"
        ),
        options=["True", "False", "Not Given"],
        correct="True",
        explanation=(
            "El texto dice que la ropa sintética \"sheds fibres in the washing "
            "machine\". Es lo mismo dicho con otras palabras: True. El IELTS casi "
            "nunca repite la frase exacta; la parafrasea."
        ),
    ),
    _item(
        "ielts-read-23",
        habilidad="ielts_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="microplastics",
        question="In the text, the word “sheds” is closest in meaning to",
        options=["releases", "repairs", "absorbs", "protects"],
        correct="releases",
        explanation=(
            "La ropa sintética suelta fibras en la lavadora, y así nacen "
            "microplásticos: \"sheds\" es \"releases\" (suelta). Si reemplazas la "
            "palabra en la frase, solo esa opción mantiene el sentido; "
            "\"absorbs\" diría lo contrario."
        ),
    ),
    _item(
        "ielts-read-24",
        habilidad="ielts_lectura",
        nivel=NIVEL_INTERMEDIO,
        passage="microplastics",
        question=(
            "Decide whether the statement agrees with the text.\n\n"
            "Statement: “Plastic beads have now been banned from cosmetics in most "
            "countries.”"
        ),
        options=["Not Given", "True", "False"],
        correct="Not Given",
        explanation=(
            "El texto dice que las microesferas \"once\" se agregaban a los "
            "cosméticos, pero no habla de prohibiciones ni de países. Ese \"once\" "
            "invita a suponer, y suponer es justo el error: Not Given."
        ),
    ),
    _item(
        "ielts-read-25",
        habilidad="ielts_lectura",
        nivel=NIVEL_AVANZADO,
        passage="microplastics",
        question="Which statement best summarises the writer's main point?",
        options=[
            "Because microplastics are almost impossible to remove from the ocean, preventing them from entering it matters most.",
            "Microplastics have been proven to be harmful to human health.",
            "Most microplastics are produced deliberately at a small size.",
            "Scientists have found an effective way to clean microplastics from rivers.",
        ],
        correct="Because microplastics are almost impossible to remove from the ocean, preventing them from entering it matters most.",
        explanation=(
            "El texto cierra con lo que \"is already clear\": sacarlos del mar es "
            "casi imposible, así que la prioridad es evitar que lleguen. La "
            "segunda opción contradice el texto (\"still know relatively little\" "
            "sobre la salud), la tercera invierte el origen y la cuarta inventa "
            "una solución."
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
    # I-3 · Sprint 4 · ampliación del banco de IELTS (de 6 a 25). Mismas reglas
    # que los de arriba: propios, sin ítems oficiales, explicación en español.
    _item(
        "ielts-voc-7",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best word.\n\n"
            "Many students ______ research online before choosing a university."
        ),
        options=["do", "make", "take", "give"],
        correct="do",
        explanation=(
            "En inglés la investigación se \"hace\" con “do”: “do research”. "
            "“Make research” es el calco del español \"hacer\" y es el error más "
            "común. Las colocaciones no se razonan, se aprenden en bloque: "
            "do research, make a decision, take a test."
        ),
    ),
    _item(
        "ielts-voc-8",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best word.\n\n"
            "The new law will ______ everyone who owns a car."
        ),
        options=["affect", "effect", "effort", "afford"],
        correct="affect",
        explanation=(
            "Hace falta un verbo: “affect” (afectar). “Effect” casi siempre es "
            "sustantivo (el efecto): \"the law will have an effect on…\". Truco: "
            "a-ffect es la Acción (verbo), e-ffect es el rEsultado (sustantivo)."
        ),
    ),
    _item(
        "ielts-voc-9",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best word.\n\n"
            "The number of tourists ______ by 20 percent last year."
        ),
        options=["rose", "raised", "arose", "risen"],
        correct="rose",
        explanation=(
            "“Rise” (subir) no lleva objeto: algo sube solo. “Raise” (subir algo) "
            "sí lo necesita: \"they raised prices\". Aquí el número sube por sí "
            "mismo, y en pasado: “rose”. “Risen” es el participio y necesitaría "
            "“has”. En las gráficas del Writing Task 1 este par sale siempre."
        ),
    ),
    _item(
        "ielts-voc-10",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best word.\n\n"
            "Plastic pollution ______ a serious threat to marine life."
        ),
        options=["poses", "makes", "does", "puts"],
        correct="poses",
        explanation=(
            "La colocación es “pose a threat” (representar una amenaza). "
            "“Make a threat” existe, pero significa amenazar a alguien "
            "verbalmente, que es otra cosa. Este tipo de pregunta premia saber "
            "qué verbo acompaña a cada sustantivo."
        ),
    ),
    _item(
        "ielts-voc-11",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best word.\n\n"
            "The campaign aims to ______ awareness of mental health."
        ),
        options=["raise", "rise", "grow", "arise"],
        correct="raise",
        explanation=(
            "“Raise awareness” (crear conciencia) es colocación fija. Además, "
            "como “awareness” es el objeto, hace falta un verbo que lleve objeto: "
            "“raise”. “Rise” y “arise” no llevan objeto, y “grow awareness” no se "
            "usa en inglés académico."
        ),
    ),
    _item(
        "ielts-voc-12",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best word.\n\n"
            "The price ______ throughout the year, going up and down several "
            "times."
        ),
        options=["fluctuated", "stabilised", "doubled", "disappeared"],
        correct="fluctuated",
        explanation=(
            "“Going up and down several times” es la definición de “fluctuate” "
            "(oscilar). “Stabilised” dice lo contrario (se quedó quieto) y "
            "“doubled” describe una sola subida. Describir bien el movimiento de "
            "un dato es la mitad del Writing Task 1."
        ),
    ),
    _item(
        "ielts-voc-13",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best word.\n\n"
            "From these figures, we can ______ a clear conclusion."
        ),
        options=["draw", "pull", "take out", "make up"],
        correct="draw",
        explanation=(
            "La conclusión se \"saca\" con “draw”: “draw a conclusion”. “Take "
            "out” y “pull” son el calco de \"sacar\", y “make up” significa "
            "inventar, justo lo que una conclusión no debe ser."
        ),
    ),
    _item(
        "ielts-voc-14",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the best word.\n\n"
            "Buying food in bulk is more ______ for large families."
        ),
        options=["economical", "economic", "economy", "economist"],
        correct="economical",
        explanation=(
            "“Economical” significa que ahorra dinero; “economic” significa "
            "relacionado con la economía (\"economic growth\"). Aquí se habla de "
            "gastar menos, así que “economical”. Los otros dos ni siquiera son "
            "adjetivos."
        ),
    ),
    _item(
        "ielts-voc-15",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the best word.\n\n"
            "The ______ reason for the delay was a shortage of staff."
        ),
        options=["principal", "principle", "principled", "principally"],
        correct="principal",
        explanation=(
            "“Principal” es adjetivo: principal, más importante. “Principle” es "
            "sustantivo: un principio (\"a moral principle\"). Suenan igual y por "
            "eso se confunden al escribir. Delante de un sustantivo (“reason”) "
            "va el adjetivo."
        ),
    ),
    _item(
        "ielts-voc-16",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the best word.\n\n"
            "The company could not ______ the growing demand for its products."
        ),
        options=["meet", "reach", "arrive", "achieve"],
        correct="meet",
        explanation=(
            "La demanda se atiende con “meet”: “meet the demand” (también "
            "\"meet a deadline\", \"meet the needs\"). “Reach” y “achieve” se "
            "usan con metas, no con demanda, y “arrive” no lleva objeto."
        ),
    ),
    _item(
        "ielts-voc-17",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the best word.\n\n"
            "The two countries finally ______ an agreement after months of talks."
        ),
        options=["reached", "arrived", "got to", "made up"],
        correct="reached",
        explanation=(
            "“Reach an agreement” es la colocación formal (llegar a un acuerdo). "
            "“Arrived an agreement” no lleva la preposición que necesitaría "
            "(\"arrive at\"), “got to” es informal y “made up” significa "
            "reconciliarse o inventar."
        ),
    ),
    _item(
        "ielts-voc-18",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the best word.\n\n"
            "From her tone of voice, I ______ that she was not satisfied."
        ),
        options=["inferred", "implied", "referred", "conferred"],
        correct="inferred",
        explanation=(
            "Quien escucha “infers” (deduce); quien habla “implies” (insinúa). "
            "Aquí \"I\" saca una conclusión del tono de ella, así que “inferred”. "
            "“Implied” diría que yo insinué algo, que es lo contrario."
        ),
    ),
    _item(
        "ielts-voc-19",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the best word.\n\n"
            "There was a ______ increase in sales: they almost tripled."
        ),
        options=["substantial", "slight", "marginal", "negligible"],
        correct="substantial",
        explanation=(
            "Casi triplicarse es un aumento grande: “substantial”. Las otras tres "
            "opciones significan pequeño o casi nada. La pista está después de los "
            "dos puntos: en estas preguntas la oración casi siempre trae la "
            "definición de la palabra que falta."
        ),
    ),
    _item(
        "ielts-voc-20",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the best word.\n\n"
            "The new medicine had no ______ effects on the patients."
        ),
        options=["adverse", "averse", "diverse", "inverse"],
        correct="adverse",
        explanation=(
            "“Adverse effects” son efectos negativos. “Averse” describe a una "
            "persona que rechaza algo (\"risk-averse\"), no un efecto. Las cuatro "
            "se parecen en la forma y solo una encaja en el sentido."
        ),
    ),
    _item(
        "ielts-voc-21",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the best word.\n\n"
            "Rising sea levels could ______ the problem of coastal flooding."
        ),
        options=["exacerbate", "alleviate", "mitigate", "eradicate"],
        correct="exacerbate",
        explanation=(
            "Que suba el mar empeora las inundaciones: “exacerbate” (agravar). "
            "“Alleviate” y “mitigate” significan aliviar, y “eradicate”, "
            "eliminar: las cuatro funcionan con \"the problem\", así que la "
            "gramática no ayuda y decide el sentido."
        ),
    ),
    _item(
        "ielts-voc-22",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the best word.\n\n"
            "Smartphones have become ______: almost everyone carries one."
        ),
        options=["ubiquitous", "obsolete", "scarce", "redundant"],
        correct="ubiquitous",
        explanation=(
            "“Ubiquitous” significa que está en todas partes, y eso es lo que "
            "explica la segunda mitad. “Obsolete” (pasado de moda) y “scarce” "
            "(escaso) dicen lo contrario. Es una palabra de nivel alto que suma "
            "en el criterio de vocabulario del Writing."
        ),
    ),
    _item(
        "ielts-voc-23",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the best word.\n\n"
            "The scale of the flood was ______: nothing like it had ever been "
            "recorded."
        ),
        options=["unprecedented", "predictable", "routine", "marginal"],
        correct="unprecedented",
        explanation=(
            "\"Nothing like it had ever been recorded\" define “unprecedented” "
            "(sin precedentes). “Routine” y “predictable” dicen lo opuesto. Es "
            "una palabra muy útil en los ensayos para hablar de cambios grandes."
        ),
    ),
    _item(
        "ielts-voc-24",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the best word.\n\n"
            "Planting trees along rivers can help ______ the risk of erosion."
        ),
        options=["mitigate", "aggravate", "exacerbate", "intensify"],
        correct="mitigate",
        explanation=(
            "Los árboles reducen el riesgo: “mitigate” (mitigar). Las otras tres "
            "significan empeorar, y la trampa es que \"help ______ the risk\" "
            "funciona gramaticalmente con todas. Va en pareja con el 21: "
            "exacerbate empeora, mitigate alivia."
        ),
    ),
    _item(
        "ielts-voc-25",
        habilidad="ielts_vocabulario",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the best word.\n\n"
            "The two courses ______ each other well: one is theoretical and the "
            "other is practical."
        ),
        options=["complement", "compliment", "supplement", "implement"],
        correct="complement",
        explanation=(
            "“Complement” (con e) es completarse mutuamente, que es lo que hacen "
            "un curso teórico y uno práctico. “Compliment” (con i) es un halago. "
            "“Supplement” es añadir algo extra a una sola cosa, no \"each other\"."
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
    # I-3 · Sprint 4 · ampliación del banco de IELTS (de 6 a 25).
    _item(
        "ielts-gram-7",
        habilidad="ielts_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the correct option.\n\n"
            "______ Amazon is the largest river in South America by volume."
        ),
        options=["The", "A", "An", "(no article)"],
        correct="The",
        explanation=(
            "Los ríos, los océanos y las cordilleras llevan “the” en inglés: the "
            "Amazon, the Pacific, the Andes. Los lagos y las montañas sueltas, "
            "no: Lake Titicaca, Mount Everest. Además el río es único: “a” y "
            "“an” son para algo que hay varios."
        ),
    ),
    _item(
        "ielts-gram-8",
        habilidad="ielts_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the correct option.\n\n"
            "Since 2010, the population of the city ______ steadily."
        ),
        options=["has grown", "grew", "grows", "is growing"],
        correct="has grown",
        explanation=(
            "“Since 2010” une un momento del pasado con el presente: pide present "
            "perfect, “has grown”. El pasado simple (“grew”) necesitaría un "
            "periodo cerrado (\"between 2010 and 2015\"). En el Writing Task 1, "
            "“since” y “for” casi siempre van con present perfect."
        ),
    ),
    _item(
        "ielts-gram-9",
        habilidad="ielts_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the correct option.\n\n"
            "A large ______ of students apply to this programme every year."
        ),
        options=["number", "amount", "deal", "much"],
        correct="number",
        explanation=(
            "Los estudiantes se pueden contar, así que va “a number of”. “Amount "
            "of” y “a great deal of” son para lo que no se cuenta (\"an amount of "
            "money\"). Usar “amount” con personas es de los errores que más "
            "penaliza el examinador."
        ),
    ),
    _item(
        "ielts-gram-10",
        habilidad="ielts_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the correct option.\n\n"
            "For short distances, train travel is ______ than flying."
        ),
        options=["more efficient", "efficienter", "most efficient", "more efficienter"],
        correct="more efficient",
        explanation=(
            "Los adjetivos largos (de tres sílabas o más) forman el comparativo "
            "con “more”: more efficient. “-er” es para los cortos (faster, "
            "cheaper). “Most” es superlativo y no va con “than”, y “more "
            "efficienter” repite la comparación."
        ),
    ),
    _item(
        "ielts-gram-11",
        habilidad="ielts_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the correct option.\n\n"
            "The results depend ______ the size of the sample."
        ),
        options=["on", "of", "from", "in"],
        correct="on",
        explanation=(
            "En inglés se depende \"sobre\": “depend on”. “Depend of” es el calco "
            "del español \"depender de\", y por eso es el error más frecuente. "
            "Los verbos con preposición fija (depend on, consist of, result in) "
            "se aprenden juntos."
        ),
    ),
    _item(
        "ielts-gram-12",
        habilidad="ielts_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the correct option.\n\n"
            "Neither of the two methods ______ perfect."
        ),
        options=["is", "are", "were", "have been"],
        correct="is",
        explanation=(
            "“Neither of…” significa \"ninguno de los dos\", uno por uno: en "
            "inglés formal el verbo va en singular, “is”. En conversación se oye "
            "“are”, pero en un texto académico el examinador espera la forma "
            "formal."
        ),
    ),
    _item(
        "ielts-gram-13",
        habilidad="ielts_gramatica",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the correct option.\n\n"
            "The bridge ______ in 1932 and is still in use today."
        ),
        options=["was built", "built", "has built", "was building"],
        correct="was built",
        explanation=(
            "El puente no construyó nada: lo construyeron. Eso pide voz pasiva, "
            "“was built”. “Built” sin “was” diría que el puente construyó algo. "
            "En los diagramas de proceso del Writing Task 1 la pasiva es "
            "obligatoria."
        ),
    ),
    _item(
        "ielts-gram-14",
        habilidad="ielts_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the correct option.\n\n"
            "Students ______ parents attended university are more likely to "
            "apply."
        ),
        options=["whose", "who", "whom", "which"],
        correct="whose",
        explanation=(
            "Los padres son DE los estudiantes: posesión, “whose”. “Who” no "
            "funciona porque \"students who parents attended\" deja a “parents” "
            "sin conexión. “Which” es para cosas."
        ),
    ),
    _item(
        "ielts-gram-15",
        habilidad="ielts_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the correct option.\n\n"
            "If more people ______ public transport, there would be less traffic."
        ),
        options=["used", "use", "will use", "would use"],
        correct="used",
        explanation=(
            "La otra mitad dice “would be”: es una situación hipotética. Ese "
            "patrón pide pasado simple en el “if”: “used”. “Would” nunca va "
            "dentro del “if”, y “use” con “will” sería una condición real, que "
            "pediría \"there will be\"."
        ),
    ),
    _item(
        "ielts-gram-16",
        habilidad="ielts_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the correct option.\n\n"
            "______ the heavy rain, the match continued."
        ),
        options=["Despite", "Although", "Even though", "However"],
        correct="Despite",
        explanation=(
            "Después del espacio viene un sustantivo (“the heavy rain”), no una "
            "oración: va “despite”. “Although” y “even though” necesitan sujeto y "
            "verbo (\"although it was raining\"). “However” une dos oraciones "
            "separadas."
        ),
    ),
    _item(
        "ielts-gram-17",
        habilidad="ielts_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the correct option.\n\n"
            "Very ______ studies have examined this question, so more research "
            "is needed."
        ),
        options=["few", "a few", "little", "a little"],
        correct="few",
        explanation=(
            "“Studies” se cuenta, así que va “few” o “a few”, no “little”. Y la "
            "segunda mitad (\"more research is needed\") dice que son "
            "insuficientes: “few” tiene sentido negativo (casi ninguno); “a few” "
            "es positivo (algunos)."
        ),
    ),
    _item(
        "ielts-gram-18",
        habilidad="ielts_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the correct option.\n\n"
            "The council decided ______ the old library and build a new one."
        ),
        options=["to close", "closing", "close", "closed"],
        correct="to close",
        explanation=(
            "“Decide” va seguido de infinitivo con “to”: decide to close. Otros "
            "verbos piden -ing (\"avoid closing\", \"consider closing\"). No hay "
            "una regla que lo resuelva: hay que aprender cada verbo con su "
            "forma."
        ),
    ),
    _item(
        "ielts-gram-19",
        habilidad="ielts_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the correct option.\n\n"
            "The number of cars on the road ______ significantly since 2000."
        ),
        options=["has increased", "have increased", "increased", "are increasing"],
        correct="has increased",
        explanation=(
            "El sujeto es “the number” (singular), no “cars”: va “has”. Y "
            "“since 2000” pide present perfect. La trampa es doble: el plural "
            "\"cars\" pegado al verbo y el pasado simple que suena bien. Ojo: "
            "\"A number of cars have…\" sí es plural."
        ),
    ),
    _item(
        "ielts-gram-20",
        habilidad="ielts_gramatica",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Choose the correct option.\n\n"
            "Most men in the survey preferred football, ______ most women chose "
            "tennis."
        ),
        options=["whereas", "despite", "because of", "in spite of"],
        correct="whereas",
        explanation=(
            "Hace falta un conector que contraste dos oraciones completas: "
            "“whereas”. “Despite”, “in spite of” y “because of” van seguidos de "
            "un sustantivo, no de una oración. “Whereas” y “while” son los "
            "conectores clave para comparar datos en el Task 1."
        ),
    ),
    _item(
        "ielts-gram-21",
        habilidad="ielts_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the correct option.\n\n"
            "Had the government acted earlier, the crisis ______ avoided."
        ),
        options=["could have been", "could be", "can be", "would be"],
        correct="could have been",
        explanation=(
            "“Had the government acted” es un tercer condicional invertido (= \"if "
            "the government had acted\"): habla de algo que no pasó. La otra mitad "
            "también tiene que estar en el pasado irreal: “could have been "
            "avoided”. Las demás opciones hablan del presente o del futuro."
        ),
    ),
    _item(
        "ielts-gram-22",
        habilidad="ielts_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the correct option.\n\n"
            "Not only ______ the population grown, but it has also aged."
        ),
        options=["has", "did", "is", "had"],
        correct="has",
        explanation=(
            "Después de “not only” al comienzo, el auxiliar va antes del sujeto "
            "(inversión). La segunda parte está en present perfect (\"it has "
            "also aged\"), así que la primera también: “has the population "
            "grown”. “Did” no va con “grown”, y “had” rompe el paralelismo de "
            "tiempos."
        ),
    ),
    _item(
        "ielts-gram-23",
        habilidad="ielts_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the correct option.\n\n"
            "The more you practise, ______ you become."
        ),
        options=["the more confident", "more confident", "the most confident", "more confidently"],
        correct="the more confident",
        explanation=(
            "Es el patrón \"cuanto más… más…\": “the more…, the more…”, con “the” "
            "en las dos mitades. Sin el segundo “the” la estructura queda rota, "
            "y el superlativo no va aquí. “Confidently” es adverbio y después de "
            "“become” va adjetivo."
        ),
    ),
    _item(
        "ielts-gram-24",
        habilidad="ielts_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the correct option.\n\n"
            "The results ______ with care, as the sample was very small."
        ),
        options=[
            "should be interpreted",
            "should interpret",
            "should have interpreting",
            "should interpreted",
        ],
        correct="should be interpreted",
        explanation=(
            "Los resultados no interpretan: los interpretan. Pasiva con modal: "
            "modal + “be” + participio, “should be interpreted”. “Should "
            "interpret” sería activa y necesitaría un sujeto que interprete. Es "
            "la forma académica de dar una recomendación sin decir quién."
        ),
    ),
    _item(
        "ielts-gram-25",
        habilidad="ielts_gramatica",
        nivel=NIVEL_AVANZADO,
        question=(
            "Choose the correct option.\n\n"
            "______ the plan will succeed is still unclear."
        ),
        options=["Whether", "If", "Because", "Which"],
        correct="Whether",
        explanation=(
            "La oración entera \"______ the plan will succeed\" funciona como "
            "sujeto, y al comienzo de la oración se usa “whether” (si… o no). "
            "“If” también significa \"si\", pero en posición de sujeto no se usa "
            "en inglés formal. “Because” y “which” no forman este tipo de "
            "oración."
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
    # I-3 · Sprint 4 · ampliación del banco de IELTS (de 6 a 25). Sigue siendo
    # práctica de DECISIONES de escritura, en opción múltiple: calificar un texto
    # libre con IA sería inventarle una nota (ver el docstring del módulo).
    _item(
        "ielts-writ-7",
        habilidad="ielts_escritura",
        nivel=NIVEL_FUNDAMENTOS,
        question="Which sentence is most appropriate for an academic essay?",
        options=[
            "A large number of people now work from home at least once a week.",
            "Loads of people work from home these days.",
            "Tons of people are working from home, which is awesome.",
            "Everybody works from home now, right?",
        ],
        correct="A large number of people now work from home at least once a week.",
        explanation=(
            "El registro académico evita palabras coloquiales (\"loads\", "
            "\"tons\", \"awesome\") y preguntas retóricas, y prefiere datos "
            "precisos (\"at least once a week\") a exageraciones (\"everybody\"). "
            "El criterio \"Lexical Resource\" mide justamente esto."
        ),
    ),
    _item(
        "ielts-writ-8",
        habilidad="ielts_escritura",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "A bar chart compares coffee and tea consumption in four countries. "
            "Coffee is higher than tea in three of them. Which sentence works "
            "best as the overview?"
        ),
        options=[
            "Overall, coffee was more popular than tea in three of the four countries.",
            "In the first country, people drank 3 kilograms of coffee per person.",
            "Coffee and tea are popular drinks around the world.",
            "The chart shows coffee and tea consumption in four countries.",
        ],
        correct="Overall, coffee was more popular than tea in three of the four countries.",
        explanation=(
            "El overview resume la tendencia principal sin cifras sueltas. La "
            "segunda es un detalle (va en el cuerpo), la tercera habla del mundo "
            "y no del gráfico, y la cuarta solo repite el enunciado: describe el "
            "gráfico, no lo que muestra. Sin un overview claro, el Task 1 no pasa "
            "de cierta banda."
        ),
    ),
    _item(
        "ielts-writ-9",
        habilidad="ielts_escritura",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "A figure rises from 20 percent to 40 percent. Which sentence "
            "describes the change most accurately?"
        ),
        options=[
            "The figure doubled, from 20 percent to 40 percent.",
            "The figure rose slightly to 40 percent.",
            "The figure increased by 40 percent.",
            "The figure tripled over the period.",
        ],
        correct="The figure doubled, from 20 percent to 40 percent.",
        explanation=(
            "De 20 a 40 es el doble. \"Slightly\" subestima el cambio, y "
            "\"increased by 40 percent\" confunde puntos porcentuales con "
            "porcentaje: subió 20 puntos, que es un 100 % de aumento. Describir un "
            "dato con precisión vale más que un verbo llamativo."
        ),
    ),
    _item(
        "ielts-writ-10",
        habilidad="ielts_escritura",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Task prompt: “Many people believe that the internet has made it "
            "easier to learn new skills.”\n\n"
            "Which sentence is the best paraphrase to open your answer?"
        ),
        options=[
            "It is often argued that online resources have made acquiring new abilities simpler.",
            "Many people believe that the internet has made it easier to learn new skills.",
            "The internet is a very important invention.",
            "I think learning is good for everyone.",
        ],
        correct="It is often argued that online resources have made acquiring new abilities simpler.",
        explanation=(
            "Parafrasear es decir lo mismo con otras palabras y otra estructura. "
            "La segunda copia el enunciado palabra por palabra, y el examinador "
            "no cuenta las palabras copiadas. Las otras dos se salen del tema o "
            "dan una opinión antes de presentar la pregunta."
        ),
    ),
    _item(
        "ielts-writ-11",
        habilidad="ielts_escritura",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Choose the best linking phrase.\n\n"
            "Cycling to work is cheap. ______, it is good for your health."
        ),
        options=["In addition", "However", "As a result", "For example"],
        correct="In addition",
        explanation=(
            "Las dos oraciones nombran ventajas de la bicicleta: la segunda SUMA. "
            "\"However\" anunciaría una desventaja, \"as a result\" diría que es "
            "sano PORQUE es barato, y \"for example\" presentaría un caso de lo "
            "anterior. Los conectores bien usados suman en \"Coherence and "
            "Cohesion\"."
        ),
    ),
    _item(
        "ielts-writ-12",
        habilidad="ielts_escritura",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Which sentence works best as the conclusion of an essay arguing that "
            "public libraries are still valuable?"
        ),
        options=[
            "In conclusion, although fewer people borrow books, libraries remain valuable as free public spaces for learning.",
            "In conclusion, there are many libraries in the world.",
            "In conclusion, I will now discuss the history of libraries.",
            "In conclusion, some people like libraries and some do not.",
        ],
        correct="In conclusion, although fewer people borrow books, libraries remain valuable as free public spaces for learning.",
        explanation=(
            "La conclusión repite la postura del ensayo y su razón principal. La "
            "segunda no dice nada, la tercera abre un tema nuevo (una conclusión "
            "nunca lo hace) y la cuarta deja el ensayo sin postura, que es lo "
            "que el \"Task Response\" penaliza."
        ),
    ),
    _item(
        "ielts-writ-13",
        habilidad="ielts_escritura",
        nivel=NIVEL_FUNDAMENTOS,
        question=(
            "Which sentence best continues this one without repeating the word "
            "“increase”?\n\n"
            "“The number of visitors increased sharply in 2019.”"
        ),
        options=[
            "This upward trend continued in 2020.",
            "The number of visitors increased again in 2020.",
            "There was an increase in the increase in 2020.",
            "Visitors increased and increased in 2020.",
        ],
        correct="This upward trend continued in 2020.",
        explanation=(
            "\"This upward trend\" retoma la idea anterior sin repetir la palabra. "
            "Las otras opciones repiten \"increase\" una o varias veces. Variar el "
            "vocabulario sin perder precisión es lo que separa una banda 6 de una "
            "7 en el criterio de vocabulario."
        ),
    ),
    _item(
        "ielts-writ-14",
        habilidad="ielts_escritura",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "In 2020, Country A produced 30 tonnes of rice and Country B produced "
            "10 tonnes. Which comparison is accurate?"
        ),
        options=[
            "Country A produced three times as much rice as Country B.",
            "Country A produced twice as much rice as Country B.",
            "Country A produced 30 percent more rice than Country B.",
            "Country B produced slightly less rice than Country A.",
        ],
        correct="Country A produced three times as much rice as Country B.",
        explanation=(
            "30 es tres veces 10. \"Twice\" y \"30 percent more\" están mal "
            "calculadas, y \"slightly less\" subestima una diferencia enorme. "
            "Las estructuras de comparación (\"three times as much as\") son de "
            "las más útiles del Task 1."
        ),
    ),
    _item(
        "ielts-writ-15",
        habilidad="ielts_escritura",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Which sentence is the best topic sentence for a body paragraph about "
            "the benefits of public transport?"
        ),
        options=[
            "One major advantage of public transport is that it reduces traffic congestion.",
            "Buses in my city are usually painted blue.",
            "Public transport has existed for more than a century.",
            "Some people prefer to drive their own cars.",
        ],
        correct="One major advantage of public transport is that it reduces traffic congestion.",
        explanation=(
            "La oración temática anuncia de qué trata el párrafo: aquí, una "
            "ventaja concreta. La segunda es un detalle sin importancia, la "
            "tercera es historia y la cuarta habla del punto de vista contrario. "
            "Un párrafo con una idea clara al comienzo es más fácil de seguir."
        ),
    ),
    _item(
        "ielts-writ-16",
        habilidad="ielts_escritura",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A survey of 50 students found that most preferred online classes. "
            "Which sentence makes the most appropriate claim?"
        ),
        options=[
            "The survey suggests that many students may prefer online classes.",
            "The survey proves that all students prefer online classes.",
            "Online classes are definitely better than face-to-face classes.",
            "Every student in the world prefers online classes.",
        ],
        correct="The survey suggests that many students may prefer online classes.",
        explanation=(
            "Con 50 estudiantes no se puede \"probar\" nada para todos. El inglés "
            "académico usa verbos prudentes (\"suggests\", \"may\") para no "
            "afirmar más de lo que los datos permiten. \"Proves\", \"definitely\" "
            "y \"every student\" son exageraciones."
        ),
    ),
    _item(
        "ielts-writ-17",
        habilidad="ielts_escritura",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A diagram shows how recycled paper is produced. Which sentence best "
            "describes the first stage?"
        ),
        options=[
            "First, used paper is collected and sorted.",
            "First, people collect and sort used paper.",
            "First, used paper collecting and sorting.",
            "First, I collect and sort used paper.",
        ],
        correct="First, used paper is collected and sorted.",
        explanation=(
            "En los diagramas de proceso importa qué le pasa al material, no "
            "quién lo hace: voz pasiva (\"is collected and sorted\"). La segunda "
            "es correcta pero menos adecuada, la tercera no tiene verbo y la "
            "cuarta usa la primera persona, que no corresponde."
        ),
    ),
    _item(
        "ielts-writ-18",
        habilidad="ielts_escritura",
        nivel=NIVEL_INTERMEDIO,
        question="Which sentence best introduces an opposing view in an argument essay?",
        options=[
            "Opponents argue, however, that this policy would be too expensive to implement.",
            "However, I am right.",
            "Some people disagree, but they are wrong.",
            "On the other hand, there is the other hand.",
        ],
        correct="Opponents argue, however, that this policy would be too expensive to implement.",
        explanation=(
            "Presentar el punto de vista contrario con respeto, y con su razón "
            "(\"too expensive\"), muestra un ensayo equilibrado; después se "
            "responde. Descalificarlo (\"they are wrong\") o no decir nada "
            "concreto resta puntos en \"Task Response\"."
        ),
    ),
    _item(
        "ielts-writ-19",
        habilidad="ielts_escritura",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "Which sentence is relevant to the question “Should university "
            "education be free?”"
        ),
        options=[
            "Free tuition could allow talented students from poor families to study.",
            "My cousin studied history at university.",
            "Universities often have large libraries.",
            "Many students enjoy living in student halls.",
        ],
        correct="Free tuition could allow talented students from poor families to study.",
        explanation=(
            "Solo la primera responde a la pregunta (el costo y quién puede "
            "estudiar). Las otras hablan de universidades pero no de si deberían "
            "ser gratuitas. Salirse del tema es la forma más rápida de perder "
            "puntos en \"Task Response\"."
        ),
    ),
    _item(
        "ielts-writ-20",
        habilidad="ielts_escritura",
        nivel=NIVEL_INTERMEDIO,
        question=(
            "A figure is 49.7 percent. Which expression describes it most "
            "naturally and accurately?"
        ),
        options=["almost half", "exactly half", "well over half", "around a third"],
        correct="almost half",
        explanation=(
            "49,7 % está apenas por debajo de la mitad: \"almost half\" (casi la "
            "mitad). \"Exactly half\" es impreciso y \"well over half\" dice lo "
            "contrario. Traducir cifras a expresiones (\"almost half\", \"just over "
            "a quarter\") hace el texto más natural sin perder precisión."
        ),
    ),
    _item(
        "ielts-writ-21",
        habilidad="ielts_escritura",
        nivel=NIVEL_AVANZADO,
        question=(
            "The task says: “Discuss both views and give your own opinion.” "
            "Which sentence is the best thesis?"
        ),
        options=[
            "Although some believe that exams are the fairest way to assess students, I would argue that coursework gives a more complete picture, provided it is carefully supervised.",
            "There are two views about exams and coursework.",
            "This essay will discuss exams.",
            "Exams and coursework both have advantages and disadvantages.",
        ],
        correct="Although some believe that exams are the fairest way to assess students, I would argue that coursework gives a more complete picture, provided it is carefully supervised.",
        explanation=(
            "La tarea pide dos cosas: las dos posturas Y tu opinión. Solo la "
            "primera hace ambas: nombra la postura contraria, da la propia y la "
            "matiza (\"provided…\"). Las demás anuncian el tema sin tomar postura, "
            "que es justo lo que la consigna pide evitar."
        ),
    ),
    _item(
        "ielts-writ-22",
        habilidad="ielts_escritura",
        nivel=NIVEL_AVANZADO,
        question=(
            "Which sentence expresses a contrast in the most sophisticated way?"
        ),
        options=[
            "While technology has made communication faster, it has arguably made it more superficial.",
            "Technology makes communication faster. But it is more superficial.",
            "Technology is fast and communication is superficial.",
            "Technology good, communication bad.",
        ],
        correct="While technology has made communication faster, it has arguably made it more superficial.",
        explanation=(
            "Una oración compleja con \"while\" une las dos ideas y muestra el "
            "contraste, y \"arguably\" matiza la afirmación. La segunda es "
            "correcta pero simple (dos oraciones cortas); las otras pierden la "
            "relación entre las ideas. El criterio de gramática premia la "
            "variedad de estructuras bien usadas."
        ),
    ),
    _item(
        "ielts-writ-23",
        habilidad="ielts_escritura",
        nivel=NIVEL_AVANZADO,
        question=(
            "Which sentence best supports the claim “Learning a second language "
            "improves job prospects”?"
        ),
        options=[
            "In a survey of employers, a majority said they prefer candidates who speak more than one language, particularly for roles involving international clients.",
            "Learning a language can be difficult.",
            "There are thousands of languages in the world.",
            "Many people enjoy travelling abroad.",
        ],
        correct="In a survey of employers, a majority said they prefer candidates who speak more than one language, particularly for roles involving international clients.",
        explanation=(
            "Solo la primera da evidencia que conecta el idioma con el empleo, y "
            "además dice en qué tipo de puesto pesa más. Las otras son ciertas "
            "pero no sostienen la afirmación. Un buen párrafo pasa de la idea "
            "general a un apoyo concreto."
        ),
    ),
    _item(
        "ielts-writ-24",
        habilidad="ielts_escritura",
        nivel=NIVEL_AVANZADO,
        question="Which sentence avoids overgeneralising?",
        options=[
            "Many young people spend several hours a day on social media.",
            "All young people are addicted to social media.",
            "Young people never read books any more.",
            "Social media has completely destroyed young people's social lives.",
        ],
        correct="Many young people spend several hours a day on social media.",
        explanation=(
            "\"All\", \"never\" y \"completely\" afirman algo que un solo "
            "contraejemplo derrumba. \"Many\" y \"several hours\" describen sin "
            "exagerar. El examinador penaliza las generalizaciones absolutas porque "
            "debilitan el argumento."
        ),
    ),
    _item(
        "ielts-writ-25",
        habilidad="ielts_escritura",
        nivel=NIVEL_AVANZADO,
        question=(
            "A line graph shows the populations of three cities from 1990 to "
            "2020: one grew steadily, one stayed roughly flat, and one fell after "
            "2005. Which detail is LEAST important to include in the overview?"
        ),
        options=[
            "The exact population of the second city in 1997",
            "That one city grew steadily over the period",
            "That one city's population fell after 2005",
            "That one city stayed roughly the same",
        ],
        correct="The exact population of the second city in 1997",
        explanation=(
            "El overview recoge las tendencias principales, una por ciudad. Una "
            "cifra de un año suelto es un detalle que, si hace falta, va en el "
            "cuerpo. Elegir las características clave es la primera habilidad "
            "que evalúa el Task 1."
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
    *_construir_saber11(_item, NIVEL_FUNDAMENTOS, NIVEL_INTERMEDIO, NIVEL_AVANZADO),
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
    {
        # Sprint 4 · I-5. "Práctica Saber 11", sin el nombre del instituto
        # (decisión de JP, 2026-10-31): sus marcas son registradas.
        "id": EXAMEN_SABER11,
        "slug": "practica-saber-11",
        "name": "Práctica de habilidades para el Saber 11",
        "shortName": "Práctica Saber 11",
        "description": (
            "Ejercicios propios para practicar las cinco pruebas del Saber 11: "
            "lectura crítica, matemáticas, sociales y ciudadanas, ciencias "
            "naturales e inglés. Cada uno con la explicación de por qué la "
            "respuesta correcta lo es y en qué cae cada opción equivocada."
        ),
        "academicBasis": (
            "Material de práctica escrito por el equipo de Mentoring. No son "
            "preguntas del examen ni de los cuadernillos del Icfes, no está "
            "avalado por el Icfes y no predice tu puntaje: practica las "
            "habilidades, no reproduce el instrumento."
        ),
        "estimatedMinutes": 20,
        "questionCount": _contar(EXAMEN_SABER11),
        "icon": "graduation",
        "audiencia": (
            "Pensado para 10°, 11° y 12° de colegio en Colombia, sobre todo en "
            "el último año, que es cuando se presenta."
        ),
        "formato": [
            "Lo presentan los estudiantes de último año de bachillerato en "
            "Colombia.",
            "Tiene cinco pruebas: lectura crítica, matemáticas, sociales y "
            "ciudadanas, ciencias naturales e inglés.",
            "Se presenta en español, salvo la prueba de inglés.",
            "Casi todo es de opción múltiple, y muchas preguntas parten de un "
            "texto, una tabla, una gráfica o una situación.",
        ],
        "no_cubierto": [
            {
                "que": "Un simulacro completo y cronometrado",
                "porque": (
                    "Administrar el tiempo real del examen requiere el examen "
                    "real. Aquí se practica prueba por prueba."
                ),
            },
            {
                "que": "Las preguntas oficiales de los cuadernillos",
                "porque": (
                    "Sus términos de uso no permiten usarlas en una plataforma "
                    "comercial. Puedes descargarlas gratis en la página oficial "
                    "del Icfes y practicarlas por tu cuenta."
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
