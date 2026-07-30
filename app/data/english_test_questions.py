"""Banco real del test de inglés · AMES English Placement Test (60 preguntas).

A5 / P1-8 · Sprint 3 (2026-07-29).

La clienta lo pidió desde el primer feedback: el test de inglés tenía 20 preguntas
**inventadas por nosotros**, no un instrumento real. Con este feedback llegó el
insumo: el examen escaneado de 60 preguntas, la clave de respuestas y la tabla de
equivalencia de AMES International. Los tres archivos están en
`Feedback nuevo/Sprint 3/`.

Transcrito de:
  - `AMES - examen 60 preguntas.pdf`      (9 páginas escaneadas)
  - `AMES - clave de respuestas.pdf`      (clave 1-60 + tabla de ubicación)

## El instrumento se mantiene EN INGLÉS, a propósito

No se traduce ningún enunciado ni opción. Traducir las instrucciones cambiaría la
dificultad de los ítems y **invalidaría la tabla de equivalencia de AMES**, que es
justamente lo que le da valor al cambio. La app sigue en español; el examen no.

## Estructura real del examen

| Ítems | Formato | Opciones |
|---|---|---|
| 1-5   | "Where can you see this notice?" | 3 (A-C) |
| 6-10  | Cloze · THE STARS | 3 (A-C) |
| 11-15 | Cloze · Good smiles ahead for young teeth | 4 (A-D) |
| 16-20 | Cloze · Christopher Columbus and the New World | 4 (A-D) |
| 21-40 | Sentence completion | 4 (A-D) |
| 41-45 | Cloze · CLOCKS | 4 (A-D) |
| 46-50 | Cloze · Dublin City Walks | 4 (A-D) |
| 51-60 | Sentence completion | 4 (A-D) |

## Dos cosas que NO son de AMES y hay que saber

1. **`section` (grammar / vocabulary / reading) es NUESTRA clasificación.** AMES solo
   separa "Part 1" y "Part 2". Las tres secciones existen porque el PDF del
   estudiante y la pantalla de resultados muestran tres barras, y quitarlas sería
   una regresión visible. Se clasificó ítem por ítem con criterio explícito:
   comprensión en contexto → `reading`; estructura (tiempos, preposiciones,
   conectores) → `grammar`; léxico y colocaciones → `vocabulary`. La partición real
   de AMES se expone aparte en `ames_parts`, sin interpretación nuestra.
2. **`difficulty` va en None.** El examen NO trae nivel CEFR por pregunta. El banco
   anterior sí lo traía porque nos lo habíamos inventado. Poner una etiqueta CEFR
   por ítem que AMES no declara sería mostrarle al estudiante un dato falso.

## La tabla de equivalencia es la de ELLA, literal

El insumo de A5 traía **tres** archivos, no dos. El tercero —
`AMES - equivalencia IELTS.jpg`— es la página **"Test de inglés gratuito" de la
propia agencia**, y trae la tabla completa con seis columnas, incluida
**Common European Framework**. `_PLACEMENT` la reproduce tal cual: los puntajes,
el IELTS, el CEFR y los nombres de clase en español que ella publica.

Esto corrigió tres cosas que en la primera versión resolvimos por nuestra cuenta:

- El **CEFR** se derivaba con criterio nuestro y difería del suyo en tres franjas.
  La peor: 56-60 nosotros decíamos **C1** y su web publica **B2**. Ese valor se
  persiste en `user.english_cefr_level`, se le muestra a los asesores, se imprime
  en la hoja de vida y viaja al CRM — o sea, le estábamos mostrando a un
  estudiante un nivel distinto al que la agencia publica para el mismo puntaje.
- El **"> 4"** de la fila 0-7 del PDF, que habíamos leído como "< 4": su tabla dice
  **3.5**. No hacía falta interpretar nada, el dato estaba.
- Los **nombres de clase**: usábamos los del PDF en inglés ("ESP", "IELTS & Uni
  preparation"); ella publica "Nivel postgrado" y "Avanzado académico".

Si alguna vez hay que cambiar la equivalencia, se cambia **solo `_PLACEMENT`**:
nada más en el archivo depende de ella.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Textos de los cloze · transcritos literales, con los huecos numerados
# ---------------------------------------------------------------------------

_PASSAGES: Dict[str, str] = {
    "stars": (
        "THE STARS\n\n"
        "There are millions of stars in the sky. If you look (6) .......... the sky "
        "on a clear night, it is possible to see about 3000 stars. They look small, "
        "but they are really (7) .......... big hot balls of burning gas. Some of them "
        "are huge, but others are much smaller, like our planet Earth. The biggest "
        "stars are very bright, but they only live for a short time. Every day new "
        "stars (8) .......... born and old stars die. All the stars are very far away. "
        "The light from the nearest star takes more (9) .......... four years to reach "
        "Earth. Hundreds of years ago, people (10) .......... stars, like the North "
        "Star, to know which direction to travel in. Today you can still see that star."
    ),
    "teeth": (
        "Good smiles ahead for young teeth\n\n"
        "Older Britons are the worst in Europe when it comes to keeping their teeth. "
        "But British youngsters (11) .......... more to smile about because "
        "(12) .......... teeth are among the best. Almost 80% of Britons over 65 have "
        "lost all or some (13) .......... their teeth according to a World Health "
        "Organisation survey. Eating too (14) .......... sugar is part of the problem. "
        "Among (15) .........., 12 year-olds have an average only three missing, "
        "decayed or filled teeth."
    ),
    "columbus": (
        "Christopher Columbus and the New World\n\n"
        "On August 3, 1492, Christopher Columbus set sail from Spain to find a new "
        "route to India, China and Japan. At this time most people thought you would "
        "fall off the edge of the world if you sailed too far. Yet sailors such as "
        "Columbus had seen how a ship appeared to get lower and lower on the horizon "
        "as it sailed away. For Columbus this (16) .......... that the world was "
        "round. He (17) .......... to his men about the distance traveled each day. He "
        "did not want them to think that he did not (18) .......... exactly where they "
        "were going. (19) .........., on October 12, 1492, Columbus and his men landed "
        "on a small island he named San Salvador. Columbus believed he was in Asia, "
        "(20) .......... he was actually in the Caribbean."
    ),
    "clocks": (
        "CLOCKS\n\n"
        "The clock was the first complex mechanical machinery to enter the home, "
        "(41) .......... it was too expensive for the (42) .......... person until the "
        "19th century, when (43) .......... production techniques lowered the price. "
        "Watches were also developed, but they (44) .......... luxury items until 1868, "
        "when the first cheap pocket watch was designed in Switzerland. Watches later "
        "became (45) .......... available, and Switzerland became the world's leading "
        "watch manufacturing centre for the next 100 years."
    ),
    "dublin": (
        "Dublin City Walks\n\n"
        "What better way of getting to know a new city than by walking around it? "
        "Whether you choose the Medieval Walk, which will (46) .......... you to the "
        "Dublin of 1000 years ago, find out about the more (47) .......... history of "
        "the city on the Eighteenth Century Walk, or meet the ghosts of Dublin's many "
        "writers on the Literary Walk, we know you will enjoy the experience.\n\n"
        "Dublin City Walks (48) .......... twice daily. Meet your guide at 10.30 a.m. "
        "or 2.30 p.m. at the Tourist Information Office. No advance (49) .......... is "
        "necessary. Special (50) .......... are available for families, children and "
        "parties of more than ten people."
    ),
}


# ---------------------------------------------------------------------------
# Clave de respuestas · transcrita de `AMES - clave de respuestas.pdf`
#
# Se deja como una sola cadena, en orden 1→60, para que se pueda cotejar de un
# golpe contra el escaneo. Las letras se resuelven contra el orden impreso de las
# opciones, así que un desfase se detecta releyendo esta línea y no 60 dicts.
# ---------------------------------------------------------------------------

_ANSWER_KEY = (
    "C B A C C A A C C B "   # 1-10
    "C A B A C D A B C B "   # 11-20
    "C D B B A A D A C D "   # 21-30
    "B B C C D B C B C C "   # 31-40
    "B A D D D A C A D D "   # 41-50
    "C C B C D D C B A D "   # 51-60
).split()


# ---------------------------------------------------------------------------
# Los 60 ítems · (nº, sección, enunciado, opciones, id del texto)
#
# `sección` es nuestra (ver docstring). `id del texto` es None cuando el ítem no
# pertenece a un cloze.
# ---------------------------------------------------------------------------

_ITEMS = [
    # --- 1-5 · Where can you see this notice? (3 opciones) -----------------
    (1, "reading", 'Where can you see this notice?\n\n"You can look, but don\'t touch the pictures."',
     ("in an office", "in a cinema", "in a museum"), None),
    (2, "reading", 'Where can you see this notice?\n\n"Please give the right money to the driver."',
     ("in a bank", "on a bus", "in a cinema"), None),
    (3, "reading", 'Where can you see this notice?\n\n"NO PARKING PLEASE"',
     ("in a street", "on a book", "on a table"), None),
    (4, "reading", 'Where can you see this notice?\n\n"CROSS BRIDGE FOR TRAINS TO EDINBURGH"',
     ("in a bank", "in a garage", "in a station"), None),
    (5, "reading", 'Where can you see this notice?\n\n"KEEP IN A COLD PLACE"',
     ("on clothes", "on furniture", "on food"), None),

    # --- 6-10 · THE STARS (3 opciones) ------------------------------------
    (6, "reading", "Gap (6) — choose the word that best fits.", ("at", "up", "on"), "stars"),
    (7, "reading", "Gap (7) — choose the word that best fits.", ("very", "too", "much"), "stars"),
    (8, "reading", "Gap (8) — choose the word that best fits.", ("is", "be", "are"), "stars"),
    (9, "reading", "Gap (9) — choose the word that best fits.", ("that", "of", "than"), "stars"),
    (10, "reading", "Gap (10) — choose the word that best fits.", ("use", "used", "using"), "stars"),

    # --- 11-15 · Good smiles ahead for young teeth ------------------------
    (11, "reading", "Gap (11) — choose the word that best fits.",
     ("getting", "got", "have", "having"), "teeth"),
    (12, "reading", "Gap (12) — choose the word that best fits.",
     ("their", "his", "them", "theirs"), "teeth"),
    (13, "reading", "Gap (13) — choose the word that best fits.",
     ("from", "of", "among", "between"), "teeth"),
    (14, "reading", "Gap (14) — choose the word that best fits.",
     ("much", "lot", "many", "deal"), "teeth"),
    (15, "reading", "Gap (15) — choose the word that best fits.",
     ("person", "people", "children", "family"), "teeth"),

    # --- 16-20 · Christopher Columbus and the New World -------------------
    (16, "reading", "Gap (16) — choose the word that best fits.",
     ("made", "pointed", "was", "proved"), "columbus"),
    (17, "reading", "Gap (17) — choose the word that best fits.",
     ("lied", "told", "cheated", "asked"), "columbus"),
    (18, "reading", "Gap (18) — choose the word that best fits.",
     ("find", "know", "think", "expect"), "columbus"),
    (19, "reading", "Gap (19) — choose the word that best fits.",
     ("Next", "Secondly", "Finally", "Once"), "columbus"),
    (20, "reading", "Gap (20) — choose the word that best fits.",
     ("as", "but", "because", "if"), "columbus"),

    # --- 21-40 · Sentence completion -------------------------------------
    (21, "grammar", "The children won't go to sleep .......... we leave a light on outside their bedroom.",
     ("except", "otherwise", "unless", "but"), None),
    (22, "grammar", "I'll give you my spare keys in case you .......... home before me.",
     ("would get", "got", "will get", "get"), None),
    (23, "vocabulary", "My holiday in Paris gave me a great .......... to improve my French accent.",
     ("by", "chance", "hope", "possibility"), None),
    (24, "grammar", "The singer ended the concert .......... her most popular song.",
     ("by", "with", "in", "as"), None),
    (25, "vocabulary", "Because it had not rained for several months, there was a .......... of water.",
     ("shortage", "drop", "scarce", "waste"), None),
    (26, "vocabulary", "I've always .......... you as my best friend.",
     ("regarded", "thought", "meant", "supposed"), None),
    (27, "vocabulary", "She came to live here .......... a month ago.",
     ("quite", "beyond", "already", "almost"), None),
    (28, "vocabulary", "Don't make such a ..........! The dentist is only going to look at your teeth.",
     ("fuss", "trouble", "worry", "reaction"), None),
    (29, "vocabulary", "He spent a long time looking for a tie which .......... with his new shirt.",
     ("fixed", "made", "went", "wore"), None),
    (30, "vocabulary", "Fortunately, .......... from a bump on the head, she suffered no serious injuries from her fall.",
     ("other", "except", "besides", "apart"), None),
    (31, "vocabulary", "She had changed so much that .......... anyone recognized her.",
     ("almost", "hardly", "not", "nearly"), None),
    (32, "grammar", ".......... teaching English, she also writes children's books.",
     ("Moreover", "As well as", "In addition", "Apart"), None),
    (33, "vocabulary", "It was clear that the young couple were .......... of taking charge of the restaurant.",
     ("responsible", "reliable", "capable", "able"), None),
    (34, "vocabulary", "The book .......... of ten chapters, each one covering a different topic.",
     ("comprises", "includes", "consists", "contains"), None),
    (35, "vocabulary", "Mary was disappointed with her new shirt as the colour .......... very quickly.",
     ("bleached", "died", "vanished", "faded"), None),
    (36, "vocabulary", "National leaders from all over the world are expected to attend the .......... meeting.",
     ("peak", "summit", "top", "apex"), None),
    (37, "vocabulary", "Jane remained calm when she won the lottery and .......... about her business as if nothing had happened.",
     ("came", "brought", "went", "moved"), None),
    (38, "grammar", "I suggest we .......... outside the stadium tomorrow at 8.30.",
     ("meeting", "meet", "met", "will meet"), None),
    (39, "vocabulary", "My remarks were .......... as a joke, but she was offended by them.",
     ("pretended", "thought", "meant", "supposed"), None),
    (40, "vocabulary", "You ought to take up swimming for the .......... of your health.",
     ("concern", "relief", "sake", "cause"), None),

    # --- 41-45 · CLOCKS --------------------------------------------------
    (41, "reading", "Gap (41) — choose the word that best fits.",
     ("despite", "although", "otherwise", "average"), "clocks"),
    (42, "reading", "Gap (42) — choose the word that best fits.",
     ("average", "medium", "general", "common"), "clocks"),
    (43, "reading", "Gap (43) — choose the word that best fits.",
     ("vast", "large", "wide", "mass"), "clocks"),
    (44, "reading", "Gap (44) — choose the word that best fits.",
     ("lasted", "endured", "kept", "remained"), "clocks"),
    (45, "reading", "Gap (45) — choose the word that best fits.",
     ("mostly", "chiefly", "greatly", "widely"), "clocks"),

    # --- 46-50 · Dublin City Walks ---------------------------------------
    (46, "reading", "Gap (46) — choose the word that best fits.",
     ("introduce", "present", "move", "show"), "dublin"),
    (47, "reading", "Gap (47) — choose the word that best fits.",
     ("near", "late", "recent", "close"), "dublin"),
    (48, "reading", "Gap (48) — choose the word that best fits.",
     ("take place", "occur", "work", "function"), "dublin"),
    (49, "reading", "Gap (49) — choose the word that best fits.",
     ("paying", "reserving", "warning", "booking"), "dublin"),
    (50, "reading", "Gap (50) — choose the word that best fits.",
     ("funds", "costs", "fees", "rates"), "dublin"),

    # --- 51-60 · Sentence completion -------------------------------------
    (51, "vocabulary", "If you're not too tired we could have a .......... of tennis after lunch.",
     ("match", "play", "game", "party"), None),
    (52, "grammar", "Don't you get tired .......... watching TV every night?",
     ("with", "by", "of", "at"), None),
    (53, "grammar", "Go on, finish the dessert. It needs .......... up because it won't stay fresh until tomorrow.",
     ("eat", "eating", "to eat", "eaten"), None),
    (54, "grammar", "We're not used to .......... invited to very formal occasions.",
     ("be", "have", "being", "having"), None),
    (55, "grammar", "I'd rather we .......... meet this evening, because I'm very tired.",
     ("wouldn't", "shouldn't", "hadn't", "didn't"), None),
    (56, "vocabulary", "She obviously didn't want to discuss the matter so I didn't .......... the point.",
     ("maintain", "chase", "follow", "pursue"), None),
    (57, "grammar", "Anyone .......... after the start of the play is not allowed in until the interval.",
     ("arrives", "has arrived", "arriving", "arrived"), None),
    (58, "vocabulary", "This new magazine is .......... with interesting stories and useful information.",
     ("full", "packed", "thick", "compiled"), None),
    (59, "vocabulary", "The restaurant was far too noisy to be .......... to relaxed conversation.",
     ("conducive", "suitable", "practical", "fruitful"), None),
    (60, "vocabulary", "In this branch of medicine, it is vital to .......... open to new ideas.",
     ("stand", "continue", "hold", "remain"), None),
]

# La partición real de AMES · sin interpretación nuestra.
_AMES_PART_OF = {n: ("Part 1" if n <= 40 else "Part 2") for n in range(1, 61)}


def _build() -> List[Dict[str, Any]]:
    """Arma el banco resolviendo cada letra de la clave contra el orden impreso."""
    if len(_ANSWER_KEY) != 60:
        raise ValueError(f"la clave debe tener 60 letras, tiene {len(_ANSWER_KEY)}")
    if len(_ITEMS) != 60:
        raise ValueError(f"deben ser 60 ítems, hay {len(_ITEMS)}")

    banco: List[Dict[str, Any]] = []
    for (numero, seccion, enunciado, opciones, passage_id) in _ITEMS:
        letra = _ANSWER_KEY[numero - 1]
        indice = "ABCD".index(letra)
        if indice >= len(opciones):
            raise ValueError(
                f"ítem {numero}: la clave dice {letra} pero solo hay "
                f"{len(opciones)} opciones"
            )
        banco.append(
            {
                "id": f"a{numero}",
                "number": numero,
                "section": seccion,
                # El examen NO declara nivel por pregunta · no se inventa.
                "difficulty": None,
                "question": enunciado,
                "options": list(opciones),
                "correct": opciones[indice],
                "answer_letter": letra,
                "passage_id": passage_id,
                "ames_part": _AMES_PART_OF[numero],
            }
        )
    return banco


ENGLISH_TEST_QUESTIONS: List[Dict[str, Any]] = _build()


# ---------------------------------------------------------------------------
# Tabla de equivalencia · transcrita de `AMES - equivalencia IELTS.jpg`, que es
# la página "Test de inglés gratuito" DE LA PROPIA AGENCIA.
#
# (mínimo, máximo, IELTS, ubicación de clase, CEFR)
#
# Las cuatro columnas son de ELLA, incluido el CEFR. No se deriva nada: si la
# plataforma le mostrara a un estudiante un nivel distinto al que publica su web
# para el mismo puntaje, el dato de la plataforma sería el equivocado.
# ---------------------------------------------------------------------------

_PLACEMENT = [
    (0, 7, "3.5", "Elemental", "A2"),
    (8, 17, "4.0", "Pre intermedio", "B1"),
    (18, 29, "4.5", "Intermedio", "B1"),
    (30, 39, "5.0", "Intermedio alto", "B1"),
    (40, 47, "5.5", "Avanzado", "B2"),
    (48, 55, "6.0", "Avanzado académico", "B2"),
    (56, 60, "6.5", "Nivel postgrado", "B2"),
]

_SECTIONS = ("grammar", "vocabulary", "reading")


def placement_for(score: int) -> Dict[str, str]:
    """Puntaje bruto (0-60) → IELTS aproximado, ubicación de AMES y CEFR."""
    for minimo, maximo, ielts, clase, cefr in _PLACEMENT:
        if minimo <= score <= maximo:
            return {
                "ielts_equivalent": ielts,
                "class_placement": clase,
                "cefr_level": cefr,
            }
    # Fuera de rango: se acota en vez de reventar.
    borde = _PLACEMENT[0] if score < 0 else _PLACEMENT[-1]
    return {
        "ielts_equivalent": borde[2],
        "class_placement": borde[3],
        "cefr_level": borde[4],
    }


def get_questions_for_client() -> List[Dict[str, Any]]:
    """Las preguntas SIN la respuesta correcta, para el front.

    Se manda el texto del cloze en `passage` en cada ítem que pertenece a uno; el
    front ya sabe mostrarlo arriba de la pregunta.
    """
    resultado = []
    for q in ENGLISH_TEST_QUESTIONS:
        item: Dict[str, Any] = {
            "id": q["id"],
            "number": q["number"],
            "section": q["section"],
            "difficulty": q["difficulty"],
            "question": q["question"],
            "options": q["options"],
            "ames_part": q["ames_part"],
        }
        if q["passage_id"]:
            item["passage"] = _PASSAGES[q["passage_id"]]
        resultado.append(item)
    return resultado


def calculate_score(answers: Dict[str, Any]) -> Dict[str, Any]:
    """Califica el test y ubica al estudiante con la tabla de AMES.

    Mantiene las llaves que ya consumen la pantalla de resultados y los dos PDFs
    (`score`, `total_questions`, `percentage`, `cefr_level`, `section_scores`) y
    agrega las de AMES (`ielts_equivalent`, `class_placement`, `ames_parts`).
    """
    seccion_correctas = {s: 0 for s in _SECTIONS}
    seccion_total = {s: 0 for s in _SECTIONS}
    partes: Dict[str, Dict[str, int]] = {}
    total_correctas = 0

    for q in ENGLISH_TEST_QUESTIONS:
        seccion = q["section"]
        seccion_total[seccion] += 1

        parte = partes.setdefault(q["ames_part"], {"correct": 0, "total": 0})
        parte["total"] += 1

        if answers.get(q["id"]) == q["correct"]:
            total_correctas += 1
            seccion_correctas[seccion] += 1
            parte["correct"] += 1

    total_preguntas = len(ENGLISH_TEST_QUESTIONS)
    porcentaje = (total_correctas / total_preguntas * 100) if total_preguntas else 0

    ubicacion = placement_for(total_correctas)

    section_scores = {}
    for seccion in _SECTIONS:
        total = seccion_total[seccion]
        correctas = seccion_correctas[seccion]
        section_scores[seccion] = {
            "correct": correctas,
            "total": total,
            "percentage": round(correctas / total * 100) if total else 0,
        }

    for parte in partes.values():
        parte["percentage"] = (
            round(parte["correct"] / parte["total"] * 100) if parte["total"] else 0
        )

    return {
        "score": total_correctas,
        "total_questions": total_preguntas,
        "percentage": round(porcentaje),
        "cefr_level": ubicacion["cefr_level"],
        "section_scores": section_scores,
        # --- AMES · lo que dice su propio instrumento --------------------
        "ielts_equivalent": ubicacion["ielts_equivalent"],
        "class_placement": ubicacion["class_placement"],
        "ames_parts": partes,
        "instrument": "AMES English Placement Test",
    }
