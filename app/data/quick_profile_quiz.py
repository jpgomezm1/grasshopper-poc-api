"""Quick vocational profile quiz for lead magnet.

6 questions, ~3 minutes, generates a vocational profile type.
"""

from typing import Dict, Any, List


QUIZ_QUESTIONS = [
    {
        "id": "q1_excitement",
        "question": "¿Qué te emociona más?",
        "type": "MULTI_CHOICE",
        "max_select": 2,
        "helper": "Elige hasta 2",
        "options": [
            "Resolver problemas complejos",
            "Crear algo desde cero",
            "Ayudar a otras personas",
            "Descubrir cómo funcionan las cosas",
            "Liderar equipos o proyectos",
            "Expresarme de forma artística",
        ],
    },
    {
        "id": "q2_free_time",
        "question": "Cuando tienes tiempo libre, prefieres...",
        "type": "SINGLE_CHOICE",
        "options": [
            "Aprender algo nuevo online",
            "Hacer deporte o actividades al aire libre",
            "Crear contenido o arte",
            "Socializar y conocer gente",
            "Organizar y planificar cosas",
        ],
    },
    {
        "id": "q3_environment",
        "question": "¿Qué tipo de ambiente te atrae más?",
        "type": "SINGLE_CHOICE",
        "options": [
            "Una oficina moderna con tecnología",
            "Un estudio creativo o taller",
            "Un espacio al aire libre o en movimiento",
            "Un ambiente social con mucha gente",
            "Un laboratorio o centro de investigación",
        ],
    },
    {
        "id": "q4_master",
        "question": "Si pudieras dominar algo en 6 meses, ¿qué sería?",
        "type": "SINGLE_CHOICE",
        "options": [
            "Un idioma nuevo",
            "Programación o tecnología",
            "Diseño o artes visuales",
            "Marketing o negocios",
            "Cocina, música u otra habilidad práctica",
        ],
    },
    {
        "id": "q5_values",
        "question": "¿Qué es lo que más valoras en una experiencia educativa?",
        "type": "SINGLE_CHOICE",
        "options": [
            "Que sea práctica y aplicable",
            "Que abra puertas profesionales",
            "Que me permita conocer otra cultura",
            "Que me rete intelectualmente",
            "Que sea flexible y a mi ritmo",
        ],
    },
    {
        "id": "q6_stage",
        "question": "¿Cuál es tu situación actual?",
        "type": "SINGLE_CHOICE",
        "options": [
            "Terminando el colegio",
            "En la universidad",
            "Ya trabajando",
            "En transición o cambio de carrera",
            "Explorando opciones sin prisa",
        ],
    },
]


# 8 vocational profile types with descriptions
PROFILE_TYPES = {
    "explorer": {
        "name": "El Explorador Curioso",
        "emoji": "🌍",
        "description": "Te motiva descubrir, experimentar y conocer nuevas culturas. Aprendes mejor cuando estás inmerso en experiencias reales.",
        "traits": ["Curiosidad", "Adaptabilidad", "Mentalidad abierta"],
        "recommendation": "Un programa de inmersión cultural con idiomas o una experiencia de voluntariado internacional serían ideales para ti.",
    },
    "builder": {
        "name": "El Constructor Creativo",
        "emoji": "🛠️",
        "description": "Te apasiona crear cosas tangibles. Tienes una mente práctica y te gusta ver resultados concretos de tu trabajo.",
        "traits": ["Creatividad", "Orientación a resultados", "Pensamiento práctico"],
        "recommendation": "Programas de diseño, desarrollo web o artes aplicadas te permitirán construir un portafolio mientras aprendes.",
    },
    "leader": {
        "name": "El Líder Estratégico",
        "emoji": "🚀",
        "description": "Te atrae la gestión, la estrategia y liderar iniciativas. Piensas en grande y te motiva el impacto.",
        "traits": ["Liderazgo", "Visión estratégica", "Comunicación"],
        "recommendation": "Un programa de negocios internacionales o MBA corto te dará las herramientas para liderar con perspectiva global.",
    },
    "analyst": {
        "name": "El Analista Metódico",
        "emoji": "🔬",
        "description": "Te fascina entender cómo funcionan las cosas. Eres detallista, lógico y disfrutas resolver problemas complejos.",
        "traits": ["Pensamiento analítico", "Atención al detalle", "Lógica"],
        "recommendation": "Carreras en ciencia de datos, ingeniería o investigación te permitirán aplicar tu mente analítica.",
    },
    "connector": {
        "name": "El Conector Social",
        "emoji": "🤝",
        "description": "Te energiza estar con personas. Tienes facilidad para comunicarte y construir relaciones significativas.",
        "traits": ["Empatía", "Habilidades sociales", "Colaboración"],
        "recommendation": "Programas en comunicación, psicología, educación o trabajo social aprovechan tu talento natural con las personas.",
    },
    "innovator": {
        "name": "El Innovador Digital",
        "emoji": "💡",
        "description": "Te atrae la tecnología y la innovación. Siempre estás buscando nuevas formas de hacer las cosas.",
        "traits": ["Innovación", "Pensamiento tecnológico", "Aprendizaje continuo"],
        "recommendation": "Bootcamps de tecnología, programas de UX/UI o cursos de inteligencia artificial son tu camino.",
    },
    "artist": {
        "name": "El Artista Expresivo",
        "emoji": "🎨",
        "description": "Tu mundo es la expresión creativa. Tienes sensibilidad estética y necesitas canales para tu creatividad.",
        "traits": ["Expresión artística", "Sensibilidad", "Originalidad"],
        "recommendation": "Estudios en artes visuales, música, cine o diseño gráfico te darán el espacio para brillar.",
    },
    "pragmatic": {
        "name": "El Pragmático Flexible",
        "emoji": "⚡",
        "description": "Valoras la flexibilidad y los resultados prácticos. No te gusta perder tiempo en teoría que no aplica.",
        "traits": ["Pragmatismo", "Flexibilidad", "Eficiencia"],
        "recommendation": "Cursos cortos e intensivos con certificación rápida y aplicación directa son perfectos para tu estilo.",
    },
}


def get_questions_for_client() -> List[Dict[str, Any]]:
    """Return questions without internal scoring data."""
    return QUIZ_QUESTIONS


def calculate_profile(answers: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate vocational profile type from quiz answers.

    Uses a scoring system that maps answer combinations to profile types.
    """
    scores: Dict[str, int] = {key: 0 for key in PROFILE_TYPES}

    # Q1: What excites you (multi-choice, max 2)
    q1 = answers.get("q1_excitement", [])
    if isinstance(q1, str):
        q1 = [q1]

    excitement_map = {
        "Resolver problemas complejos": ["analyst", "innovator"],
        "Crear algo desde cero": ["builder", "artist"],
        "Ayudar a otras personas": ["connector", "explorer"],
        "Descubrir cómo funcionan las cosas": ["analyst", "explorer"],
        "Liderar equipos o proyectos": ["leader", "pragmatic"],
        "Expresarme de forma artística": ["artist", "builder"],
    }
    for choice in q1:
        for profile_type in excitement_map.get(choice, []):
            scores[profile_type] += 3

    # Q2: Free time preference
    q2 = answers.get("q2_free_time", "")
    free_time_map = {
        "Aprender algo nuevo online": ["innovator", "analyst"],
        "Hacer deporte o actividades al aire libre": ["explorer", "pragmatic"],
        "Crear contenido o arte": ["artist", "builder"],
        "Socializar y conocer gente": ["connector", "leader"],
        "Organizar y planificar cosas": ["leader", "pragmatic"],
    }
    for profile_type in free_time_map.get(q2, []):
        scores[profile_type] += 2

    # Q3: Environment preference
    q3 = answers.get("q3_environment", "")
    env_map = {
        "Una oficina moderna con tecnología": ["innovator", "leader"],
        "Un estudio creativo o taller": ["builder", "artist"],
        "Un espacio al aire libre o en movimiento": ["explorer", "pragmatic"],
        "Un ambiente social con mucha gente": ["connector", "explorer"],
        "Un laboratorio o centro de investigación": ["analyst", "innovator"],
    }
    for profile_type in env_map.get(q3, []):
        scores[profile_type] += 2

    # Q4: What to master in 6 months
    q4 = answers.get("q4_master", "")
    master_map = {
        "Un idioma nuevo": ["explorer", "connector"],
        "Programación o tecnología": ["innovator", "analyst"],
        "Diseño o artes visuales": ["artist", "builder"],
        "Marketing o negocios": ["leader", "pragmatic"],
        "Cocina, música u otra habilidad práctica": ["builder", "pragmatic"],
    }
    for profile_type in master_map.get(q4, []):
        scores[profile_type] += 2

    # Q5: Educational values
    q5 = answers.get("q5_values", "")
    values_map = {
        "Que sea práctica y aplicable": ["pragmatic", "builder"],
        "Que abra puertas profesionales": ["leader", "pragmatic"],
        "Que me permita conocer otra cultura": ["explorer", "connector"],
        "Que me rete intelectualmente": ["analyst", "innovator"],
        "Que sea flexible y a mi ritmo": ["pragmatic", "innovator"],
    }
    for profile_type in values_map.get(q5, []):
        scores[profile_type] += 2

    # Q6: Current stage (lighter weight)
    q6 = answers.get("q6_stage", "")
    stage_map = {
        "Terminando el colegio": ["explorer"],
        "En la universidad": ["analyst", "builder"],
        "Ya trabajando": ["leader", "pragmatic"],
        "En transición o cambio de carrera": ["innovator", "explorer"],
        "Explorando opciones sin prisa": ["explorer", "artist"],
    }
    for profile_type in stage_map.get(q6, []):
        scores[profile_type] += 1

    # Find the top profile type
    sorted_profiles = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_type = sorted_profiles[0][0]
    profile = PROFILE_TYPES[top_type]

    return {
        "profile_type": top_type,
        "profile_name": profile["name"],
        "emoji": profile["emoji"],
        "description": profile["description"],
        "traits": profile["traits"],
        "recommendation": profile["recommendation"],
    }
