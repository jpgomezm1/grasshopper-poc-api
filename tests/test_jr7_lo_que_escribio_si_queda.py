"""JR-7 · Lo que el estudiante escribe tiene que verse de vuelta.

Queja de la clienta en la reunión del 21-07:

    Escribió a conciencia en los textos libres y en la bitácora —su ejemplo
    textual: "capitana del equipo de vóleibol"— y siente que "nada de eso
    queda". Pidió que el sistema refleje lo que aprendió: "eso lo registro
    como liderazgo".

Al verificarlo resultó que **tenía razón de forma literal**: las actividades
extracurriculares no aparecían ni una vez en el pipeline de IA. Sólo se usaban
para el CRUD y para el PDF del CV. O sea que el ejemplo exacto que ella puso era
el caso que de verdad se perdía.

Estos tests fijan las dos mitades del arreglo:

  1. Que la actividad ENTRE al prompt del perfil consolidado.
  2. Que el perfil pueda decir de dónde sacó cada fortaleza.

El test que más importa es `test_la_capitana_del_equipo_llega_al_prompt`, porque
usa el ejemplo textual de la clienta y comprueba el prompt REAL que se le manda
al modelo — no una función intermedia.
"""
from __future__ import annotations

import uuid

import pytest


# ---------------------------------------------------------------------------
# 1 · Que lo que escribió entre al prompt
# ---------------------------------------------------------------------------


def test_formateo_de_actividades_incluye_rol_y_logros():
    from app.services.consolidation_service import _format_activities_block

    bloque = _format_activities_block(
        [
            {
                "category": "deporte",
                "name": "Equipo de vóleibol del colegio",
                "role": "Capitana",
                "hours_per_week": 6,
                "en_curso": True,
                "description": "Entreno al grupo de menores los sábados.",
                "achievements": ["Subcampeonas departamentales 2025"],
            }
        ]
    )

    # El rol es la señal de liderazgo · es lo que la clienta quería que se viera
    assert "Capitana" in bloque
    assert "Equipo de vóleibol del colegio" in bloque
    assert "Subcampeonas departamentales 2025" in bloque
    assert "Entreno al grupo de menores" in bloque
    assert "6 h/semana" in bloque


def test_sin_actividades_no_revienta_ni_inventa():
    from app.services.consolidation_service import _format_activities_block

    bloque = _format_activities_block([])
    assert "todavía no registró actividades" in bloque.lower()


def test_la_capitana_del_equipo_llega_al_prompt():
    """El camino incómodo: el prompt REAL, no una función intermedia."""
    from app.services.consolidation_service import render_consolidate_prompt

    prompt = render_consolidate_prompt(
        {
            "user_id": str(uuid.uuid4()),
            "demographic": {"name": "Susana"},
            "tests": [],
            "journey_answers": {},
            "onboarding": {},
            "activities": [
                {
                    "category": "deporte",
                    "name": "Vóleibol",
                    "role": "Capitana del equipo",
                    "hours_per_week": 4,
                    "en_curso": True,
                    "description": None,
                    "achievements": [],
                }
            ],
        }
    )

    assert "Capitana del equipo" in prompt
    # Y el prompt tiene que PEDIRLE al modelo que lo cite de vuelta
    assert "strengths_evidence" in prompt


def test_el_prompt_pide_evidencia_en_palabras_de_la_persona():
    from app.services.consolidation_service import render_consolidate_prompt

    prompt = render_consolidate_prompt(
        {
            "user_id": str(uuid.uuid4()),
            "demographic": {},
            "tests": [],
            "journey_answers": {},
            "onboarding": {},
            "activities": [],
        }
    )

    bajo = prompt.lower()
    # Un `"puntaje" in prompt` no sirve: la palabra aparece en varios sitios del
    # prompt y el test pasaría aunque se borrara la instrucción. Se busca la
    # instrucción concreta.
    assert "escribió o hizo" in bajo or "escribio o hizo" in bajo
    assert "antes que un puntaje" in bajo
    assert "no inventes" in bajo
    # Y que pida la frase en segunda persona empezando por "Porque…"
    assert 'empezando por "porque' in bajo


def test_el_bloque_de_actividades_tiene_tope_de_tamano():
    """Sin tope, veinte actividades largas inflan el prompt y su costo.

    `description` admite 4000 caracteres por actividad y no hay límite de cuántas
    puede registrar una persona. El resto del mismo prompt sí recorta (las
    respuestas de voz se cortan a 600); esto no lo hacía.
    """
    from app.services.consolidation_service import _format_activities_block

    muchas = [
        {
            "category": "deporte",
            "name": f"Actividad {i}",
            "role": "Participante",
            "hours_per_week": 3,
            "en_curso": True,
            "description": "x" * 4000,
            "achievements": [f"logro {j}" for j in range(20)],
        }
        for i in range(30)
    ]
    bloque = _format_activities_block(muchas)

    # Con 30 actividades de 4000 caracteres sin tope, esto pasaría de 120.000
    assert len(bloque) < 12000, f"el bloque creció a {len(bloque)} caracteres"
    # Y el modelo tiene que saber que hay más, no creer que son todas
    assert "más que no caben" in bloque


def test_las_actividades_cambian_el_hash_de_entrada():
    """Si no cambiaran, el perfil cacheado seguiría ignorándolas.

    Es el defecto de fondo del reclamo: la persona escribe algo, el perfil no se
    regenera, y concluye —con razón— que no sirvió de nada.
    """
    from app.services import consolidation_service as cs

    base = {
        "user_id": "u1",
        "demographic": {},
        "tests": [],
        "journey_answers": {},
        "onboarding": {},
        "activities": [],
    }
    con_actividad = {
        **base,
        "activities": [
            {
                "category": "voluntariado",
                "name": "Fundación",
                "role": "Voluntaria",
                "hours_per_week": None,
                "en_curso": True,
                "description": None,
                "achievements": [],
            }
        ],
    }

    assert cs.hash_inputs(base) != cs.hash_inputs(con_actividad)


# ---------------------------------------------------------------------------
# 2 · Que el perfil pueda decir de dónde sale cada fortaleza
# ---------------------------------------------------------------------------


def _perfil_minimo(**extra):
    base = {
        "summary_narrative": "x" * 250,
        "strengths": ["Liderazgo", "Constancia", "Empatía"],
        "interests": ["Salud", "Educación", "Deporte"],
        "values": ["Servicio"],
        "learning_style": "Práctico-experiencial",
        "work_style": "Colaborativo",
        "holland_codes": [],
        "personality_dimensions": [],
        "constraints": [],
        "suggested_career_paths": ["Fisioterapia", "Docencia", "Nutrición"],
        "tests_used": ["holland"],
    }
    base.update(extra)
    return base


def test_el_perfil_acepta_la_evidencia_por_fortaleza():
    from app.schemas.consolidated_profile import ConsolidatedProfile

    perfil = ConsolidatedProfile(
        **_perfil_minimo(
            strengths_evidence=[
                {
                    "strength": "Liderazgo",
                    "evidence": "Porque contaste que fuiste capitana del equipo de vóleibol.",
                }
            ]
        )
    )
    assert perfil.strengths_evidence[0].strength == "Liderazgo"
    assert perfil.strengths_evidence[0].evidence.startswith("Porque")


def test_los_perfiles_viejos_siguen_siendo_validos():
    """Hay perfiles generados antes de este cambio · no se pueden invalidar."""
    from app.schemas.consolidated_profile import ConsolidatedProfile

    perfil = ConsolidatedProfile(**_perfil_minimo())
    assert perfil.strengths_evidence == []
