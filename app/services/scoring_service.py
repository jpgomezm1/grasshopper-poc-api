"""Scoring service for MBTI and iStrong tests.

Both tests reuse the generic Likert mechanics in
``app.data.vocational_tests.calculate_vocational_scores`` and then derive
test-specific aggregates.

* MBTI: 4 dimensions (EI, SN, TF, JP) -> derived 4-letter type (16 possible)
* iStrong: 6 General Occupational Themes (R, I, A, S, E, C) aggregated from
  12 Basic Interest Scales (2 per GOT). Each BIS keeps its own 0-100 score
  for granular reporting.

Scoring algorithms are deterministic and offline. AI is only used downstream
for narrative interpretation of the results, never for the numbers.

See decisions:
* D-011 (iStrong inspired by Holland · NOT Strong Interest Inventory)
* The scoring shape feeds ``VocationalTestResult.scores`` (JSON column).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from app.data.vocational_tests import (
    calculate_vocational_scores,
    get_test_by_id,
)
from app.services.habilidades_blandas_service import (
    TEST_ID as HABILIDADES_BLANDAS_TEST_ID,
    calcular_habilidades_blandas,
)


# ---------------------------------------------------------------------------
# MBTI
# ---------------------------------------------------------------------------

# Each dimension maps to a tuple (high_letter, low_letter).
# ``calculate_vocational_scores`` returns a 0-100 score for each category
# considering ``reversed`` flags. A high score (>=50) means the first letter,
# a low score means the second.
MBTI_DIMENSIONS: List[Tuple[str, str, str]] = [
    ("EI", "E", "I"),
    ("SN", "S", "N"),
    ("TF", "T", "F"),
    ("JP", "J", "P"),
]

# Career hints per type (broad strokes · used for FE display + narrative seed).
MBTI_TYPE_INFO: Dict[str, Dict[str, object]] = {
    "INTJ": {
        "name": "Arquitecto/a",
        "summary": "Estratega independiente · razona en sistemas · diseña planes a largo plazo.",
        "strengths": ["Pensamiento estratégico", "Independencia", "Visión sistémica"],
        "careers": ["Investigación", "Ingeniería de software", "Estrategia corporativa", "Ciencia de datos"],
    },
    "INTP": {
        "name": "Lógico/a",
        "summary": "Pensador/a abstracto/a · curiosidad teórica · busca coherencia conceptual.",
        "strengths": ["Análisis profundo", "Curiosidad intelectual", "Pensamiento crítico"],
        "careers": ["Filosofía", "Matemáticas", "Investigación científica", "Programación"],
    },
    "ENTJ": {
        "name": "Comandante",
        "summary": "Líder estratégico · ejecuta planes ambiciosos · convierte ideas en resultados.",
        "strengths": ["Liderazgo", "Visión estratégica", "Decisión"],
        "careers": ["Dirección general", "Consultoría", "Emprendimiento", "Banca de inversión"],
    },
    "ENTP": {
        "name": "Innovador/a",
        "summary": "Generador de ideas · disfruta el debate · ve oportunidades antes que otros.",
        "strengths": ["Innovación", "Adaptabilidad", "Persuasión"],
        "careers": ["Emprendimiento", "Marketing", "Investigación aplicada", "Consultoría tecnológica"],
    },
    "INFJ": {
        "name": "Abogado/a",
        "summary": "Idealista profundo/a · busca propósito · empático/a y reflexivo/a.",
        "strengths": ["Empatía", "Visión", "Comunicación escrita"],
        "careers": ["Psicología", "Escritura", "Consejería", "Trabajo social", "ONGs"],
    },
    "INFP": {
        "name": "Mediador/a",
        "summary": "Idealista creativo/a · valores fuertes · expresa sensibilidad por el arte.",
        "strengths": ["Creatividad", "Empatía", "Autenticidad"],
        "careers": ["Escritura", "Diseño", "Psicología", "Arte", "Educación"],
    },
    "ENFJ": {
        "name": "Protagonista",
        "summary": "Líder carismático/a · inspira y guía · enfoca su energía en el desarrollo de otros.",
        "strengths": ["Liderazgo inspirador", "Comunicación", "Empatía organizacional"],
        "careers": ["Educación", "Recursos humanos", "Política", "Coaching", "Comunicación"],
    },
    "ENFP": {
        "name": "Activista",
        "summary": "Entusiasta creativo/a · genera ideas y energía · conecta personas.",
        "strengths": ["Creatividad", "Entusiasmo", "Comunicación"],
        "careers": ["Comunicación", "Marketing", "Periodismo", "Emprendimiento social"],
    },
    "ISTJ": {
        "name": "Logístico/a",
        "summary": "Práctico/a y confiable · sigue procedimientos · organiza y ejecuta.",
        "strengths": ["Organización", "Disciplina", "Atención al detalle"],
        "careers": ["Contabilidad", "Auditoría", "Logística", "Administración pública"],
    },
    "ISFJ": {
        "name": "Defensor/a",
        "summary": "Protector/a leal · cuida a su grupo · prefiere actuar tras bambalinas.",
        "strengths": ["Lealtad", "Cuidado", "Atención al detalle"],
        "careers": ["Enfermería", "Educación primaria", "Trabajo social", "Recursos humanos"],
    },
    "ESTJ": {
        "name": "Ejecutivo/a",
        "summary": "Organizador/a tradicional · estructura equipos y procesos · enfoque en resultados.",
        "strengths": ["Liderazgo operativo", "Disciplina", "Orientación a resultados"],
        "careers": ["Administración", "Operaciones", "Militar", "Gerencia de proyectos"],
    },
    "ESFJ": {
        "name": "Cónsul",
        "summary": "Anfitrión/a social · atento/a a las personas · construye comunidad.",
        "strengths": ["Empatía social", "Cooperación", "Organización de eventos"],
        "careers": ["Educación", "Salud", "Hotelería", "Recursos humanos", "Eventos"],
    },
    "ISTP": {
        "name": "Virtuoso/a",
        "summary": "Solucionador/a práctico/a · domina herramientas · aprende haciendo.",
        "strengths": ["Resolución práctica", "Adaptabilidad", "Pensamiento técnico"],
        "careers": ["Ingeniería mecánica", "Mecánica", "Cirugía", "Forenses", "Tecnología"],
    },
    "ISFP": {
        "name": "Aventurero/a",
        "summary": "Sensible y artístico/a · valora la libertad · expresa con acciones.",
        "strengths": ["Creatividad práctica", "Sensibilidad estética", "Adaptabilidad"],
        "careers": ["Artes visuales", "Música", "Diseño", "Veterinaria", "Cocina"],
    },
    "ESTP": {
        "name": "Emprendedor/a",
        "summary": "Activo/a y observador/a · disfruta la acción · responde rápido a la realidad.",
        "strengths": ["Pensamiento rápido", "Adaptabilidad", "Negociación"],
        "careers": ["Ventas", "Emprendimiento", "Deportes profesionales", "Emergencias"],
    },
    "ESFP": {
        "name": "Animador/a",
        "summary": "Espontáneo/a y sociable · disfruta el momento · contagia energía.",
        "strengths": ["Carisma", "Espontaneidad", "Conexión social"],
        "careers": ["Actuación", "Eventos", "Turismo", "Atención al cliente", "Comunicación"],
    },
}


def calculate_mbti(answers: Dict[str, int]) -> Dict[str, object]:
    """Calculate MBTI scores and derive the 4-letter type.

    Returns a dict with shape::

        {
          "dimensions": {
            "EI": {"score": 65, "letter": "E", "preference": 30},
            "SN": {...},
            "TF": {...},
            "JP": {...}
          },
          "type": "ENFJ",
          "type_info": {...}
        }

    Where ``preference`` is a 0-100 strength of the dominant pole
    (``abs(score-50) * 2``) and ``letter`` is the dominant pole.

    The internal Likert score (0-100) treats high values as the first
    letter of the dimension (E, S, T, J) and ``reversed`` items in the
    bank flip toward the second letter (I, N, F, P).
    """
    raw = calculate_vocational_scores("mbti", answers)
    dimensions: Dict[str, Dict[str, int | str]] = {}
    type_letters: List[str] = []

    for code, high, low in MBTI_DIMENSIONS:
        score = int(raw.get(code, 50))
        # tie-break: 50 leans to the high letter to stay deterministic
        letter = high if score >= 50 else low
        preference = abs(score - 50) * 2  # 0..100
        dimensions[code] = {
            "score": score,
            "letter": letter,
            "preference": preference,
        }
        type_letters.append(letter)

    mbti_type = "".join(type_letters)
    return {
        "dimensions": dimensions,
        "type": mbti_type,
        "type_info": MBTI_TYPE_INFO.get(mbti_type, {}),
    }


# ---------------------------------------------------------------------------
# iStrong
# ---------------------------------------------------------------------------

# Mapping General Occupational Theme -> list of Basic Interest Scales.
# Codes match the prefix used in ``vocational_tests.py``.
ISTRONG_GOT_BIS: Dict[str, List[str]] = {
    "R": ["R:mecanica", "R:naturaleza"],
    "I": ["I:ciencias", "I:tecnologia"],
    "A": ["A:visual", "A:performativa"],
    "S": ["S:educacion", "S:salud-mental"],
    "E": ["E:negocios", "E:liderazgo"],
    "C": ["C:datos", "C:logistica"],
}

ISTRONG_BIS_INFO: Dict[str, Dict[str, str]] = {
    "R:mecanica": {"name": "Mecánica e ingeniería aplicada", "got": "R"},
    "R:naturaleza": {"name": "Naturaleza, agro y outdoor", "got": "R"},
    "I:ciencias": {"name": "Ciencias básicas y de la salud", "got": "I"},
    "I:tecnologia": {"name": "Tecnología y software", "got": "I"},
    "A:visual": {"name": "Artes visuales y diseño", "got": "A"},
    "A:performativa": {"name": "Artes escénicas y escritura", "got": "A"},
    "S:educacion": {"name": "Educación y pedagogía", "got": "S"},
    "S:salud-mental": {"name": "Salud mental y acompañamiento", "got": "S"},
    "E:negocios": {"name": "Negocios, finanzas y marketing", "got": "E"},
    "E:liderazgo": {"name": "Liderazgo, leyes y política", "got": "E"},
    "C:datos": {"name": "Análisis de datos y contabilidad", "got": "C"},
    "C:logistica": {"name": "Operaciones y administración", "got": "C"},
}

ISTRONG_GOT_INFO: Dict[str, Dict[str, str]] = {
    "R": {"name": "Realista", "description": "Práctico, manual, orientado a hacer."},
    "I": {"name": "Investigador", "description": "Analítico, intelectual, científico."},
    "A": {"name": "Artístico", "description": "Creativo, expresivo, original."},
    "S": {"name": "Social", "description": "Colaborativo, ayuda a otros, enseña."},
    "E": {"name": "Emprendedor", "description": "Persuasivo, líder, orientado a negocios."},
    "C": {"name": "Convencional", "description": "Organizado, sistemático, detallista."},
}


def calculate_istrong(answers: Dict[str, int]) -> Dict[str, object]:
    """Calculate iStrong GOT (6) and BIS (12) scores.

    Returns::

        {
          "got": {"R": 72, "I": 81, ...},     # 0-100 per General Occupational Theme
          "bis": {"R:mecanica": 68, ...},     # 0-100 per Basic Interest Scale
          "primary_got": "I",
          "secondary_got": "A",
          "tertiary_got": "S",
          "three_letter_code": "IAS",
          "top_bis": ["I:tecnologia", "I:ciencias", "A:visual"],  # top 3 BIS
        }
    """
    bis_scores = calculate_vocational_scores("istrong", answers)
    # Aggregate GOT as the average of its 2 BIS
    got_scores: Dict[str, int] = {}
    for got, bis_list in ISTRONG_GOT_BIS.items():
        values = [bis_scores.get(b, 0) for b in bis_list]
        got_scores[got] = round(sum(values) / len(values)) if values else 0

    sorted_got = sorted(got_scores.items(), key=lambda kv: kv[1], reverse=True)
    sorted_bis = sorted(bis_scores.items(), key=lambda kv: kv[1], reverse=True)

    primary = sorted_got[0][0] if sorted_got else ""
    secondary = sorted_got[1][0] if len(sorted_got) > 1 else ""
    tertiary = sorted_got[2][0] if len(sorted_got) > 2 else ""
    three_letter = (primary + secondary + tertiary) if primary else ""

    return {
        "got": got_scores,
        "bis": bis_scores,
        "primary_got": primary,
        "secondary_got": secondary,
        "tertiary_got": tertiary,
        "three_letter_code": three_letter,
        "top_bis": [b for b, _ in sorted_bis[:3]],
    }


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

# ── T-04 · VARK + Motivadores (algoritmo de la clienta · PDF Sprint 2 §3) ──

VARK_INFO: Dict[str, Dict[str, str]] = {
    "V": {
        "name": "Visual",
        "description": "Aprendes viendo: mapas mentales, infografías, diagramas y colores.",
        "tip": "Convierte tus apuntes en esquemas y diagramas; usa colores para agrupar ideas.",
    },
    "A": {
        "name": "Auditivo",
        "description": "Aprendes escuchando: debates, podcasts, explicaciones verbales o rimas.",
        "tip": "Graba resúmenes en audio y explícale los temas a alguien más en voz alta.",
    },
    "R": {
        "name": "Lecto-Escritura",
        "description": "Aprendes leyendo y escribiendo: listas, libros, apuntes estructurados y manuales.",
        "tip": "Haz resúmenes escritos con tus propias palabras y listas de conceptos clave.",
    },
    "K": {
        "name": "Kinestésico",
        "description": "Aprendes haciendo: tocar, armar, experimentar, moverte y aplicar la teoría a la vida real.",
        "tip": "Busca práctica real: experimentos, maquetas, simulaciones o caminar mientras repasas.",
    },
}

MOTIVADOR_INFO: Dict[str, Dict[str, str]] = {
    "LOG": {
        "name": "Logro",
        "description": "Te mueve resolver lo difícil: dominar habilidades complejas y superar desafíos.",
    },
    "IMP": {
        "name": "Impacto Social",
        "description": "Te mueve que tu trabajo mejore la vida de personas reales y transforme tu comunidad.",
    },
    "AUT": {
        "name": "Autonomía",
        "description": "Te mueve la libertad: crear a tu manera, ser dueño de tu tiempo y de tus reglas.",
    },
    "EST": {
        "name": "Estatus y Reconocimiento",
        "description": "Te mueve el éxito visible: que tu esfuerzo se note, inspire respeto y sea reconocido.",
    },
    "SEG": {
        "name": "Seguridad y Estructura",
        "description": "Te mueve la estabilidad: procesos claros, planificación y tranquilidad financiera.",
    },
}

_VARK_ORDER = ["V", "A", "R", "K"]
_MOTIVADOR_ORDER = ["LOG", "IMP", "AUT", "EST", "SEG"]


def _forced_choice_counts(test_id: str, answers: Dict[str, object], order: List[str]) -> Dict[str, int]:
    """Cuenta cuántas veces se eligió cada variable (1 punto por respuesta)."""
    test = get_test_by_id(test_id)
    counts = {k: 0 for k in order}
    for q in test["questions"]:
        chosen = answers.get(q["id"])
        if chosen in counts:
            counts[chosen] += 1
    return counts


def calculate_vark(answers: Dict[str, object]) -> Dict[str, object]:
    """Estilos de aprendizaje VARK · reglas de la clienta.

    Regla de Oro de Consejería (manejo de empates): si la diferencia entre el
    puntaje más alto y el segundo más alto es de 0 o 1 punto, NO se arroja un
    solo estilo — el alumno es "Perfil Multimodal" y el label combina los dos
    estilos dominantes (ej. "aprendiz híbrido Visual-Kinestésico"). Desempate
    determinista por orden canónico V, A, R, K.
    """
    counts = _forced_choice_counts("vark", answers, _VARK_ORDER)
    ranked = sorted(_VARK_ORDER, key=lambda k: (-counts[k], _VARK_ORDER.index(k)))
    top, second = ranked[0], ranked[1]
    multimodal = (counts[top] - counts[second]) <= 1

    if multimodal:
        styles = [top, second]
        label = f"Perfil Multimodal ({VARK_INFO[top]['name']}-{VARK_INFO[second]['name']})"
        headline = (
            f"Eres un aprendiz híbrido ({VARK_INFO[top]['name']}-{VARK_INFO[second]['name']}): "
            f"combinas dos canales de entrada y te beneficias de mezclarlos al estudiar."
        )
    else:
        styles = [top]
        label = VARK_INFO[top]["name"]
        headline = f"Tu estilo de aprendizaje predominante es {VARK_INFO[top]['name']}."

    return {
        "kind": "vark",
        "counts": counts,
        "multimodal": multimodal,
        "styles": styles,
        "label": label,
        "headline": headline,
        "style_info": [
            {"code": s, **VARK_INFO[s]} for s in styles
        ],
    }


def calculate_motivadores(answers: Dict[str, object]) -> Dict[str, object]:
    """Motivadores iniciales · reglas de la clienta.

    Motivador Primario = mayor puntaje; Secundario = segundo. En caso de
    empate absoluto en el primer lugar, se FUSIONAN ambos motivadores en el
    reporte (ej. "Te mueve el Logro con Impacto Social"). Desempate
    determinista por orden canónico LOG, IMP, AUT, EST, SEG.
    """
    counts = _forced_choice_counts("motivadores", answers, _MOTIVADOR_ORDER)
    ranked = sorted(
        _MOTIVADOR_ORDER, key=lambda k: (-counts[k], _MOTIVADOR_ORDER.index(k))
    )
    top = ranked[0]
    tied = [k for k in ranked if counts[k] == counts[top]]
    fusion = len(tied) >= 2

    if fusion:
        primary, secondary = tied[0], tied[1]
        label = f"{MOTIVADOR_INFO[primary]['name']} con {MOTIVADOR_INFO[secondary]['name']}"
        headline = (
            f"Te mueve el {MOTIVADOR_INFO[primary]['name']} con "
            f"{MOTIVADOR_INFO[secondary]['name']}."
        )
    else:
        primary = top
        secondary = ranked[1]
        label = MOTIVADOR_INFO[primary]["name"]
        headline = (
            f"Tu motivador primario es {MOTIVADOR_INFO[primary]['name']}; "
            f"el secundario, {MOTIVADOR_INFO[secondary]['name']}."
        )

    return {
        "kind": "motivadores",
        "counts": counts,
        "primary": primary,
        "secondary": secondary,
        "fusion": fusion,
        "label": label,
        "headline": headline,
        "motivator_info": [
            {"code": m, **MOTIVADOR_INFO[m]} for m in (primary, secondary)
        ],
    }


def derive_test_extras(test_id: str, answers: Dict[str, int]) -> Dict[str, object] | None:
    """Return the test-specific structured payload (or None for tests
    that don't need extras beyond raw category scores).
    """
    if get_test_by_id(test_id) is None:
        return None
    if test_id == "mbti":
        return calculate_mbti(answers)
    if test_id == "istrong":
        return calculate_istrong(answers)
    if test_id == "vark":
        return calculate_vark(answers)
    if test_id == "motivadores":
        return calculate_motivadores(answers)
    if test_id == HABILIDADES_BLANDAS_TEST_ID:
        # El mapeo de habilidades blandas (ruta grado 10) tiene su propio módulo:
        # su lectura no es un puntaje, son tendencias con reglas de empate y de
        # respuestas incompletas. Ver `habilidades_blandas_service`.
        return calcular_habilidades_blandas(answers)
    return None
